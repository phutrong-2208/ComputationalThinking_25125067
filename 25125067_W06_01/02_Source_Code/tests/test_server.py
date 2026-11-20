"""Offline tests: synthetic fixtures, never sent to the real Overpass API."""
from contextlib import contextmanager
from io import BytesIO
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, parse_qs
from urllib.request import urlopen, Request

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server import APIError, PlaceService, OSMService, map_elements, parameters, normalize, distance_m, create_server

PARAMS = (10.779783, 106.699018, 1000, "all")
FIXTURE = {"osm3s": {"timestamp_osm_base": "2026-01-01T00:00:00Z"}, "elements": [
    {"type": "node", "id": 1, "lat": PARAMS[0], "lon": PARAMS[1], "tags": {"amenity": "cafe", "name": "Test café", "internet_access": "wlan"}},
    {"type": "way", "id": 2, "center": {"lat": 10.78, "lon": 106.70}, "tags": {"amenity": "library", "wheelchair": "yes"}},
]}


def response(data):
    return BytesIO(json.dumps(data).encode())


@contextmanager
def running_server(service):
    server = create_server(0, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


class ValidationTests(unittest.TestCase):
    def test_valid_and_reject_nonfinite_out_of_range_injected_and_duplicate(self):
        args = dict(zip(("lat", "lon", "radius", "category"), PARAMS))
        self.assertEqual(parameters(urlencode(args)), PARAMS)
        for key, value in [("lat", "NaN"), ("lon", "inf"), ("lat", 91), ("radius", 2001),
                           ("radius", 500.5), ("category", 'cafe"];out;')]:
            with self.subTest(key=key, value=value), self.assertRaises(APIError):
                parameters(urlencode({**args, key: value}))
        with self.assertRaises(APIError):
            parameters(urlencode(args) + "&lat=0")
        with self.assertRaises(APIError):
            parameters("lat=&lon=0&radius=1000&category=all")

    def test_distance_units_and_zero(self):
        self.assertEqual(distance_m(0, 0, 0, 0), 0)
        self.assertAlmostEqual(distance_m(0, 0, 0, 1), 111194.93, places=1)

    def test_nodes_ways_unknown_tags_duplicates_and_radius(self):
        entries = FIXTURE["elements"] + [FIXTURE["elements"][0],
            {"type": "node", "id": 3, "lat": 0, "lon": 0, "tags": {"amenity": "cafe"}},
            {"type": "way", "id": 4, "tags": {"amenity": "cafe"}},
            {"type": "node", "id": 5, "lat": 10.78, "lon": 106.70, "tags": {"amenity": "cafe", "website": "javascript:alert(1)"}},
        ]
        result = normalize(entries, *PARAMS[:3])
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]["id"], "node/1")
        way = next(p for p in result if p["id"] == "way/2")
        self.assertEqual(way["wifi"], "unknown")
        self.assertEqual(way["address"], "")
        self.assertEqual(way["wheelchair"], "yes")
        self.assertEqual(next(p for p in result if p["id"] == "node/5")["website"], "")
        self.assertEqual(normalize([{"type":"node","id":1,"lat":0,"lon":0,"tags":{"amenity":"cafe"}}],0,0,200)[0]["lat"],0)


class ServiceTests(unittest.TestCase):
    def test_cache_rate_limit_and_expiry(self):
        now = [100.0]
        calls = []
        def opener(request, timeout):
            calls.append(request)
            self.assertEqual(timeout,40)
            self.assertIn('nwr(around:',parse_qs(request.data.decode())["data"][0])
            return response(FIXTURE)
        service = PlaceService(opener=opener, clock=lambda: now[0])
        first = service.search(PARAMS)
        second = service.search(PARAMS)
        self.assertFalse(first["meta"]["cached"])
        self.assertTrue(second["meta"]["cached"])
        self.assertEqual(len(calls),1)
        with self.assertRaises(APIError) as error:
            service.search((*PARAMS[:2],500,"all"))
        self.assertEqual(error.exception.status,429)
        now[0] += 601
        self.assertFalse(service.search(PARAMS)["meta"]["cached"])
        self.assertEqual(len(calls),2)

    def test_concurrent_duplicate_requests_share_cache(self):
        calls = []
        def opener(request, timeout):
            calls.append(1)
            return response(FIXTURE)
        service = PlaceService(opener=opener)
        results = []
        threads = [threading.Thread(target=lambda: results.append(service.search(PARAMS))) for _ in range(6)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertEqual(len(results),6)
        self.assertEqual(len(calls),1)

    def test_upstream_network_http_invalid_and_partial_responses(self):
        def offline(*args,**kwargs): raise URLError("offline")
        def busy(*args,**kwargs): raise HTTPError("https://test.invalid",429,"busy",{},None)
        for opener, status in [(offline,503),(busy,503),(lambda *a,**k:BytesIO(b"not json"),502),
                               (lambda *a,**k:response({"elements":[],"remark":"timeout"}),502),
                               (lambda *a,**k:response([]),502),
                               (lambda *a,**k:BytesIO(b"x"*4_000_001),502)]:
            with self.subTest(status=status), self.assertRaises(APIError) as error:
                PlaceService(opener=opener).search(PARAMS)
            self.assertEqual(error.exception.status,status)

    def test_results_are_bounded_and_empty_is_success(self):
        elements=[{**FIXTURE["elements"][0],"id":i+1} for i in range(160)]
        service=PlaceService(opener=lambda *a,**k:response({"elements":elements}))
        result=service.search(PARAMS)
        self.assertEqual(len(result["places"]),100)
        self.assertTrue(result["meta"]["truncated"])
        empty=PlaceService(opener=lambda *a,**k:response({"elements":[]})).search(PARAMS)
        self.assertEqual(empty["places"],[])


class HTTPTests(unittest.TestCase):
    def test_website_api_errors_and_path_isolation(self):
        service=PlaceService(opener=lambda *a,**k:response(FIXTURE))
        with running_server(service) as base:
            with urlopen(base) as r:
                self.assertIn("StudySpot",r.read().decode())
                self.assertIn("frame-ancestors 'none'",r.headers["Content-Security-Policy"])
            with urlopen(base+"/api/places?"+urlencode(dict(zip(("lat","lon","radius","category"),PARAMS)))) as r:
                self.assertEqual(len(json.load(r)["places"]),2)
            for path,code in [("/api/places?lat=NaN",400),("/api/nope",404),("/../server.py",404),
                              ("/%2e%2e/server.py",404),("/vendor/",404)]:
                with self.subTest(path=path), self.assertRaises(HTTPError) as error:
                    urlopen(base+path)
                self.assertEqual(error.exception.code,code)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(base+"/api/places",data=b"{}"))
            self.assertEqual(error.exception.code,405)


XML_FIXTURE = b'''<osm version="0.6">
<node id="1" lat="10.779783" lon="106.699018"><tag k="amenity" v="cafe"/><tag k="name" v="Synthetic cafe"/></node>
<node id="2" lat="10.78" lon="106.70"/><node id="3" lat="10.7802" lon="106.7002"/>
<way id="4"><nd ref="2"/><nd ref="3"/><tag k="amenity" v="library"/></way>
<relation id="5"><member type="way" ref="4"/><tag k="amenity" v="library"/></relation>
</osm>'''


class DirectOSMTests(unittest.TestCase):
    def test_xml_nodes_ways_relations_and_centers(self):
        elements=map_elements(XML_FIXTURE)
        self.assertEqual(len(elements),3)
        self.assertEqual(elements[0]["type"],"node")
        self.assertAlmostEqual(elements[1]["center"]["lat"],10.7801)
        self.assertEqual(elements[1]["center"],elements[2]["center"])

    def test_category_reuses_map_cache_and_large_queries_are_rejected(self):
        calls=[]
        def opener(request,timeout):
            calls.append(request)
            self.assertEqual(request.get_method(),"GET")
            self.assertIn("bbox=",request.full_url)
            return BytesIO(XML_FIXTURE)
        service=OSMService(opener=opener)
        result=service.search((*PARAMS[:2],300,"all"))
        libraries=service.search((*PARAMS[:2],300,"library"))
        self.assertEqual(len(result["places"]),3)
        self.assertEqual(len(libraries["places"]),2)
        self.assertTrue(libraries["meta"]["cached"])
        self.assertEqual(len(calls),1)
        for params in [(*PARAMS[:2],1000,"all"),(89,106,300,"all"),(0,180,300,"all")]:
            with self.subTest(params=params),self.assertRaises(APIError): service.search(params)

    def test_malformed_xml_and_upstream_failure(self):
        for opener in [lambda *a,**k:BytesIO(b"<not-xml"),lambda *a,**k:BytesIO(b"<html/>")]:
            with self.assertRaises(APIError) as error:
                OSMService(opener=opener).search((*PARAMS[:2],300,"all"))
            self.assertEqual(error.exception.status,502)
        def offline(*a,**k): raise URLError("offline")
        with self.assertRaises(APIError) as error:
            OSMService(opener=offline).search((*PARAMS[:2],300,"all"))
        self.assertEqual(error.exception.status,503)


if __name__ == "__main__":
    unittest.main(verbosity=2)
