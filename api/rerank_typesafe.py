import json

from _common import BaseHTTPRequestHandler, CORPORA, timed


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        query = body.get("query", "")
        mod = CORPORA.get(body.get("corpus", "emails"), CORPORA["emails"])
        try:
            out, status = timed(mod.rerank_typesafe, query), 200
        except Exception as e:
            out, status = {"query": query, "error": str(e)}, 500
        payload = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass
