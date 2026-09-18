import json
from urllib.parse import urlparse, parse_qs

from _common import BaseHTTPRequestHandler, CORPORA


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        corpus = parse_qs(urlparse(self.path).query).get("corpus", ["emails"])[0]
        mod = CORPORA.get(corpus, CORPORA["emails"])
        body = json.dumps({"queries": {k: v["text"] for k, v in mod.QUERIES.items()}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass
