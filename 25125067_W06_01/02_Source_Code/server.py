"""StudySpot: local website with bounded, cached OSM and Overpass integration.

Python 3.10+, standard library only. Run: python server.py
"""
import argparse
from collections import OrderedDict
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit, unquote
from urllib.request import Request, urlopen
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
MAX_RESULTS = 100
UPSTREAM_LIMIT = 300
CACHE_SECONDS = 600
MIN_INTERVAL = 5
DEFAULT_ENDPOINT = "https://overpass.private.coffee/api/interpreter"
ATTRIBUTION = "© OpenStreetMap contributors · ODbL 1.0"


class APIError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def parameters(query):
    """Validate all client values before interpolating numeric values into QL."""
    values = parse_qs(query, keep_blank_values=True)
    if set(values) != {"lat", "lon", "radius", "category"} or any(len(v) != 1 for v in values.values()):
        raise APIError(400, "Cần đúng bốn tham số: lat, lon, radius, category.")
    try:
        lat, lon, radius = (float(values[k][0]) for k in ("lat", "lon", "radius"))
    except ValueError:
        raise APIError(400, "Tọa độ và bán kính phải là số.") from None
    if not all(math.isfinite(v) for v in (lat, lon, radius)):
        raise APIError(400, "Không chấp nhận NaN hoặc vô cực.")
    if not (-90 <= lat <= 90 and -180 <= lon <= 180 and 200 <= radius <= 2000 and radius.is_integer()):
        raise APIError(400, "Tọa độ ngoài phạm vi hoặc bán kính không nguyên trong 200–2000 m.")
    category = values["category"][0]
    if category not in {"all", "cafe", "library"}:
        raise APIError(400, "Loại địa điểm không hợp lệ.")
    return round(lat, 6), round(lon, 6), int(radius), category


def build_query(lat, lon, radius, category):
    match = '"amenity"~"^(cafe|library)$"' if category == "all" else f'"amenity"="{category}"'
    return f"[out:json][timeout:25];\nnwr(around:{radius},{lat:.6f},{lon:.6f})[{match}];\nout center {UPSTREAM_LIMIT};"


def distance_m(lat1, lon1, lat2, lon2):
    phi1, phi2 = map(math.radians, (lat1, lat2))
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(min(1, max(0, a))))


def normalize(elements, lat, lon, radius):
    places, seen = [], set()
    for element in elements:
        if not isinstance(element, dict):
            continue
        tags = element.get("tags", {})
        if not isinstance(tags, dict) or tags.get("amenity") not in {"cafe", "library"}:
            continue
        kind, oid = element.get("type"), element.get("id")
        if kind not in {"node", "way", "relation"} or not isinstance(oid, int) or isinstance(oid, bool) or oid <= 0:
            continue
        key = f"{kind}/{oid}"
        center = element.get("center") or {}
        try:
            plat = float(element.get("lat", center.get("lat")))
            plon = float(element.get("lon", center.get("lon")))
        except (ValueError, TypeError, AttributeError):
            continue
        if not (math.isfinite(plat) and math.isfinite(plon) and -90 <= plat <= 90 and -180 <= plon <= 180):
            continue
        distance = distance_m(lat, lon, plat, plon)
        if distance > radius or key in seen:
            continue
        seen.add(key)
        text = lambda name: str(tags.get(name, "")).strip()[:500]
        street = " ".join(filter(None, (text("addr:housenumber"), text("addr:street"))))
        address = text("addr:full") or ", ".join(filter(None, (street, text("addr:suburb"), text("addr:city"))))
        internet = text("internet_access").lower()
        wifi = "yes" if internet == "wlan" or text("wifi").lower() == "yes" else ("no" if internet == "no" else "unknown")
        website = text("website") or text("contact:website")
        if urlsplit(website).scheme not in {"http", "https"}:
            website = ""
        places.append({
            "id": key, "name": text("name:vi") or text("name") or "Địa điểm chưa có tên",
            "category": tags["amenity"], "lat": plat, "lon": plon,
            "distance_m": round(distance), "address": address,
            "wifi": wifi, "wheelchair": text("wheelchair") or "unknown",
            "opening_hours": text("opening_hours"), "website": website,
            "osm_url": f"https://www.openstreetmap.org/{key}",
        })
    return sorted(places, key=lambda p: (p["distance_m"], p["id"]))


class PlaceService:
    provider = "overpass"
    max_radius = 2000
    def __init__(self, endpoint=None, opener=urlopen, clock=time.monotonic):
        self.endpoint = endpoint or os.getenv("OVERPASS_URL", DEFAULT_ENDPOINT)
        if urlsplit(self.endpoint).scheme != "https":
            raise ValueError("OVERPASS_URL must use HTTPS")
        self.opener, self.clock = opener, clock
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.last_request = float("-inf")

    def search(self, params):
        with self.lock:  # One upstream request at a time, shared by all local clients.
            now = self.clock()
            cached = self.cache.get(params)
            if cached and now - cached[0] < CACHE_SECONDS:
                self.cache.move_to_end(params)
                return {**cached[1], "meta": {**cached[1]["meta"], "cached": True}}
            if now - self.last_request < MIN_INTERVAL:
                raise APIError(429, "Vui lòng chờ 5 giây giữa hai truy vấn mới.")
            self.last_request = now
            lat, lon, radius, category = params
            query = build_query(*params)
            request = Request(self.endpoint, data=urlencode({"data": query}).encode(), headers={
                "User-Agent": "StudySpot-Lab06-25125067/1.0 (local educational project)",
                "Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded",
            })
            try:
                with self.opener(request, timeout=40) as response:
                    raw = response.read(4_000_001)
                if len(raw) > 4_000_000:
                    raise APIError(502, "Phản hồi quá lớn; hãy giảm bán kính.")
                data = json.loads(raw)
            except HTTPError as error:
                code = 503 if error.code in (429, 502, 503, 504) else 502
                raise APIError(code, "Máy chủ OpenStreetMap/Overpass đang bận. Hãy thử lại sau.") from None
            except (URLError, TimeoutError, OSError):
                raise APIError(503, "Không kết nối được Overpass. Kiểm tra Internet và thử lại.") from None
            except (ValueError, UnicodeError):
                raise APIError(502, "Overpass trả dữ liệu không hợp lệ.") from None
            if not isinstance(data, dict) or not isinstance(data.get("elements"), list) or data.get("remark"):
                raise APIError(502, "Truy vấn Overpass chưa hoàn tất; hãy giảm bán kính và thử lại.")
            places = normalize(data["elements"], lat, lon, radius)
            result = {"places": places[:MAX_RESULTS], "meta": {
                "source": "OpenStreetMap via Overpass API", "endpoint": self.endpoint,
                "attribution": ATTRIBUTION, "license_url": "https://www.openstreetmap.org/copyright",
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "osm_base": data.get("osm3s", {}).get("timestamp_osm_base"),
                "cached": False, "query": query, "center": {"lat": lat, "lon": lon},
                "radius_m": radius, "category": category, "upstream_count": len(data["elements"]),
                "returned_count": min(len(places), MAX_RESULTS), "limit": MAX_RESULTS,
                "truncated": len(places) > MAX_RESULTS or len(data["elements"]) >= UPSTREAM_LIMIT,
            }}
            self.cache[params] = (self.clock(), result)
            self.cache.move_to_end(params)
            while len(self.cache) > 64:
                self.cache.popitem(last=False)
            return result


def map_elements(raw):
    """Convert OSM XML nodes/ways/relations to the common display model.

    For areas, use the bounding-box center of referenced coordinates. This is
    an approximate representative point, not an entrance or routing position.
    """
    root = ET.fromstring(raw)
    if root.tag != "osm":
        raise ValueError("Not an OSM document")
    nodes = {e.get("id"): (float(e.attrib["lat"]), float(e.attrib["lon"]))
             for e in root.findall("node")}
    ways = {e.get("id"): [nodes[n.get("ref")] for n in e.findall("nd") if n.get("ref") in nodes]
            for e in root.findall("way")}
    result = []
    for element in root:
        if element.tag not in {"node", "way", "relation"}:
            continue
        tags = {t.get("k"): t.get("v", "") for t in element.findall("tag")}
        if tags.get("amenity") not in {"cafe", "library"}:
            continue
        oid = element.get("id")
        item = {"type": element.tag, "id": int(oid), "tags": tags}
        points = []
        if element.tag == "node":
            item["lat"], item["lon"] = nodes[oid]
        elif element.tag == "way":
            points = ways[oid]
        else:
            for member in element.findall("member"):
                if member.get("type") == "node" and member.get("ref") in nodes:
                    points.append(nodes[member.get("ref")])
                elif member.get("type") == "way":
                    points.extend(ways.get(member.get("ref"), []))
        if points:
            item["center"] = {"lat": (min(p[0] for p in points)+max(p[0] for p in points))/2,
                              "lon": (min(p[1] for p in points)+max(p[1] for p in points))/2}
        result.append(item)
    return result


class OSMService(PlaceService):
    """Small read-only map requests; the default mode for this local lab."""
    provider = "osm"
    max_radius = 500

    def __init__(self, opener=urlopen, clock=time.monotonic):
        super().__init__(endpoint="https://api.openstreetmap.org/api/0.6/map", opener=opener, clock=clock)

    def search(self, params):
        lat, lon, radius, category = params
        if radius > self.max_radius or abs(lat) > 85:
            raise APIError(400, "Chế độ OSM trực tiếp hỗ trợ bán kính 200–500 m và vĩ độ trong ±85°.")
        # circumscribed bounding box; final distance filtering uses Haversine.
        dlat = math.degrees(radius / 6371000)
        dlon = math.degrees(radius / (6371000 * math.cos(math.radians(lat))))
        if lon-dlon < -180 or lon+dlon > 180:
            raise APIError(400, "Vùng tìm kiếm cắt kinh tuyến 180°. Hãy chọn tâm khác.")
        bbox = f"{lon-dlon:.7f},{lat-dlat:.7f},{lon+dlon:.7f},{lat+dlat:.7f}"
        key = (lat, lon, radius)  # Category filtering reuses the same map extract.
        with self.lock:
            now = self.clock()
            cached = self.cache.get(key)
            cache_hit = bool(cached and now-cached[0] < CACHE_SECONDS)
            if cache_hit:
                elements, fetched_at = cached[1]
                self.cache.move_to_end(key)
            else:
                if now-self.last_request < MIN_INTERVAL:
                    raise APIError(429, "Vui lòng chờ 5 giây giữa hai truy vấn mới.")
                self.last_request = now
                request = Request(self.endpoint+"?"+urlencode({"bbox": bbox}), headers={
                    "User-Agent": "StudySpot-Lab06-25125067/1.0 (local educational project)",
                    "Accept": "application/xml",
                })
                try:
                    with self.opener(request, timeout=40) as response:
                        raw = response.read(8_000_001)
                    if len(raw) > 8_000_000:
                        raise APIError(502, "Vùng bản đồ quá nhiều dữ liệu. Hãy giảm bán kính.")
                    elements = map_elements(raw)
                except HTTPError as error:
                    raise APIError(503 if error.code in (429, 502, 503, 504, 509) else 502,
                                   "OpenStreetMap chưa đáp ứng được truy vấn. Hãy giảm bán kính hoặc thử lại sau.") from None
                except (URLError, TimeoutError, OSError):
                    raise APIError(503, "Không kết nối được OpenStreetMap. Kiểm tra Internet và thử lại.") from None
                except (ET.ParseError, ValueError, KeyError, TypeError):
                    raise APIError(502, "API bản đồ trả dữ liệu không hợp lệ.") from None
                fetched_at = datetime.now(timezone.utc).isoformat()
                self.cache[key] = (self.clock(), (elements, fetched_at))
                while len(self.cache) > 64:
                    self.cache.popitem(last=False)
            filtered = [e for e in elements if category == "all" or e["tags"]["amenity"] == category]
            places = normalize(filtered, lat, lon, radius)
            return {"places": places[:MAX_RESULTS], "meta": {
                "source": "OpenStreetMap API v0.6 (read-only map)", "endpoint": self.endpoint,
                "attribution": ATTRIBUTION, "license_url": "https://www.openstreetmap.org/copyright",
                "fetched_at": fetched_at, "osm_base": None, "cached": cache_hit,
                "query": f"GET /api/0.6/map?bbox={bbox}; local amenity filter={category}",
                "center": {"lat": lat, "lon": lon}, "radius_m": radius, "category": category,
                "upstream_count": len(elements), "returned_count": min(len(places), MAX_RESULTS),
                "limit": MAX_RESULTS, "truncated": len(places) > MAX_RESULTS,
            }}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, service, **kwargs):
        self.service = service
        super().__init__(*args, directory=str(WEB), **kwargs)

    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        super().end_headers()

    def json_response(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if status == 429:
            self.send_header("Retry-After", str(MIN_INTERVAL))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path == "/api/health":
            return self.json_response(200, {"status": "ok", "app": "StudySpot", "version": "1.0"})
        if parts.path == "/api/config":
            return self.json_response(200, {"tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
                                           "provider": self.service.provider, "max_radius": self.service.max_radius})
        if parts.path == "/api/places":
            try:
                return self.json_response(200, self.service.search(parameters(parts.query)))
            except APIError as error:
                return self.json_response(error.status, {"error": str(error)})
        if parts.path.startswith("/api/"):
            return self.json_response(404, {"error": "API không tồn tại."})
        resolved = (WEB / unquote(parts.path).lstrip("/")).resolve()
        if not resolved.is_relative_to(WEB) or (resolved != WEB and resolved.is_dir()):
            return self.send_error(404)
        return super().do_GET()

    def do_POST(self):
        self.json_response(405, {"error": "Website chỉ hỗ trợ GET."})

    def list_directory(self, path):
        self.send_error(404)


def create_server(port=8086, service=None):
    return ThreadingHTTPServer(("127.0.0.1", port), partial(Handler, service=service or OSMService()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8086)
    parser.add_argument("--provider", choices=["osm", "overpass"], default="osm")
    args = parser.parse_args()
    try:
        server = create_server(args.port, OSMService() if args.provider == "osm" else PlaceService())
    except OSError:
        raise SystemExit("Cổng đang bận. Thử: python server.py --port 8087") from None
    print(f"StudySpot: http://127.0.0.1:{server.server_port}", flush=True)
    print("Press Ctrl+C to stop. No API key is needed.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
