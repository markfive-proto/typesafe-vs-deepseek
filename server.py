"""Local dev server: serves index.html, lists sample docs/emails, runs TypeSafe vs DeepSeek vs
OpenAI pipelines per-file with timing/token/cost/hallucination capture. Mirrors api/*.py (the
Vercel deployment), just as one process instead of one file per route.
"""
import base64
import json
import mimetypes
import os
import re
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import pipeline as P
import email_pipeline as E
import doc_pipeline as D
import retrieval_pipeline as R
import kb_pipeline as K

P.load_env()

ROOT = Path(__file__).parent
DOCS = ROOT / "invoice_docs"
EMAILS = ROOT / "emails_samples"
PORT = int(os.environ.get("PORT", 8420))
DOC_EXTS = (".pdf", ".xlsx")
CORPORA = {"emails": R, "kb": K}


def list_docs():
    return sorted(p.name for p in DOCS.glob("*") if p.suffix.lower() in DOC_EXTS)


def list_emails():
    return sorted(p.name for p in EMAILS.glob("*.md"))


def safe_filename(name: str) -> str:
    name = Path(name).name  # strip any path components
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name or "upload"


def save_doc_upload(filename: str, b64data: str) -> str:
    name = safe_filename(filename)
    if Path(name).suffix.lower() not in DOC_EXTS:
        raise ValueError(f"unsupported file type: {name} (want .pdf or .xlsx)")
    dest = DOCS / name
    stem, suffix = dest.stem, dest.suffix
    n = 1
    while dest.exists():
        dest = DOCS / f"{stem}_{n}{suffix}"
        n += 1
    dest.write_bytes(base64.b64decode(b64data))
    return dest.name


def timed(fn, *args):
    t0 = time.perf_counter()
    result = fn(*args)
    t1 = time.perf_counter()
    result["timing_ms"] = {"total": round((t1 - t0) * 1000, 1)}
    return result


class Handler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            return self._file(ROOT / "index.html", "text/html")
        if parsed.path == "/api/documents":
            return self._json({"files": list_docs()})
        if parsed.path == "/api/emails":
            return self._json({"files": list_emails()})
        if parsed.path == "/api/queries":
            corpus = parse_qs(parsed.query).get("corpus", ["emails"])[0]
            mod = CORPORA.get(corpus, CORPORA["emails"])
            return self._json({"queries": {k: v["text"] for k, v in mod.QUERIES.items()}})
        if parsed.path.startswith("/emails_samples/"):
            fname = parsed.path.removeprefix("/emails_samples/")
            fpath = EMAILS / fname
            if fpath.is_file() and fpath.resolve().parent == EMAILS.resolve():
                return self._file(fpath, "text/plain; charset=utf-8")
            return self._json({"error": "not found"}, 404)
        self._json({"error": "not found"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        name = body.get("file", "")

        routes = {
            "/api/process_document": (D.classify, name),
            "/api/process_document_deepseek": (D.classify_via_deepseek, name),
            "/api/process_document_openai": (D.classify_via_openai, name),
            "/api/classify_email": (E.classify, name),
            "/api/classify_email_deepseek": (E.classify_via_deepseek, name),
            "/api/classify_email_openai": (E.classify_via_openai, name),
            "/api/draft_reply": (E.draft_reply, name),
        }
        if parsed.path in routes:
            fn, arg = routes[parsed.path]
            try:
                return self._json(timed(fn, arg))
            except Exception as e:
                return self._json({"file": name, "error": str(e)}, 500)

        if parsed.path == "/api/upload":
            try:
                saved = save_doc_upload(body["filename"], body["data"])
                return self._json({"ok": True, "file": saved})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 400)

        if parsed.path in ("/api/rerank_typesafe", "/api/rerank_deepseek", "/api/rerank_openai"):
            query = body.get("query", "")
            mod = CORPORA.get(body.get("corpus", "emails"), CORPORA["emails"])
            fn = {"typesafe": mod.rerank_typesafe, "deepseek": mod.rerank_deepseek, "openai": mod.rerank_openai}[parsed.path.rsplit("_", 1)[-1]]
            try:
                return self._json(timed(fn, query))
            except Exception as e:
                return self._json({"query": query, "error": str(e)}, 500)

        self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"serving on http://127.0.0.1:{PORT}")
    httpd.serve_forever()
