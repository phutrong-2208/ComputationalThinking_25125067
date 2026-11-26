"""PhraseTrip: serve the travel translator on loopback."""
import argparse
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading

from googletrans import Translator

WEB = Path(__file__).resolve().parent / "web"
LANGUAGES = {"en", "vi", "ja", "ko", "fr", "es", "th", "zh-cn"}
MAX_CHARS = 1000
TRANSLATION_SLOTS = threading.BoundedSemaphore(2)


def validate(payload):
    if not isinstance(payload, dict):
        raise ValueError("Send a JSON object.")
    text = payload.get("text")
    source = payload.get("source", "auto")
    target = payload.get("target")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= MAX_CHARS:
        raise ValueError("Enter a phrase between 1 and 1,000 characters.")
    if (not isinstance(source, str) or source not in LANGUAGES | {"auto"}
            or not isinstance(target, str) or target not in LANGUAGES):
        raise ValueError("Choose a supported source and target language.")
    return text.strip(), source, target


async def translate_phrase(text, source, target):
    async with Translator(service_urls=["translate.googleapis.com"], raise_exception=True) as translator:
        return await asyncio.wait_for(translator.translate(text, src=source, dest=target), timeout=12)


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404)

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/api/translate":
            self.send_json(404, {"error": "Endpoint not found."})
            return
        expected_origin = f"http://127.0.0.1:{self.server.server_port}"
        if self.headers.get("Origin") not in (None, expected_origin):
            self.send_json(403, {"error": "Open the app at the 127.0.0.1 address shown in the terminal."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 10000:
                raise ValueError("Request is empty or too large.")
            args = validate(json.loads(self.rfile.read(length)))
        except (ValueError, UnicodeError) as error:
            message = "Send valid JSON." if isinstance(error, (json.JSONDecodeError, UnicodeError)) else str(error)
            self.send_json(400, {"error": message})
            return
        if not TRANSLATION_SLOTS.acquire(blocking=False):
            self.send_json(429, {"error": "The translator is busy. Try again in a moment."})
            return
        try:
            result = asyncio.run(translate_phrase(*args))
            if not isinstance(result.text, str) or not result.text.strip():
                raise ValueError("Empty translation")
            data = {"text": result.text, "source": result.src, "target": result.dest,
                    "provider": "googletrans (unofficial)"}
        except TimeoutError:
            self.send_json(504, {"error": "The translation service timed out. Try again in a moment."})
            return
        except Exception as error:
            self.log_error("Upstream translation failed (%s)", type(error).__name__)
            self.send_json(502, {"error": "The translation service could not respond. Check your Internet connection and try again."})
            return
        finally:
            TRANSLATION_SLOTS.release()
        self.send_json(200, data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8077)
    args = parser.parse_args()
    with ThreadingHTTPServer(("127.0.0.1", args.port), partial(Handler, directory=str(WEB))) as server:
        print(f"PhraseTrip: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
