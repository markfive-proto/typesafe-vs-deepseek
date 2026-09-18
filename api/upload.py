import json

from _common import BaseHTTPRequestHandler, save_doc_upload


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        try:
            saved = save_doc_upload(body.get("filename", ""), body.get("data", ""))
            out, status = {"ok": True, "file": saved}, 200
        except Exception as e:
            out, status = {"ok": False, "error": str(e)}, 400
        payload = json.dumps(out).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass
