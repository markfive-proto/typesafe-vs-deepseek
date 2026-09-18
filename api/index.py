"""Vercel Python function: handles all /api/* routes (see vercel.json rewrite).
Same routing as server.py (local dev), adapted for a stateless serverless runtime:
- env vars come from the Vercel project settings, not a local .env file.
- file upload is disabled here — the deployed filesystem is read-only.
"""
import base64
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline as P
import email_pipeline as E
import doc_pipeline as D
import retrieval_pipeline as R

P.load_env()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "invoice_docs"
EMAILS = ROOT / "emails_samples"
DOC_EXTS = (".pdf", ".xlsx")


def list_docs():
    return sorted(p.name for p in DOCS.glob("*") if p.suffix.lower() in DOC_EXTS)


def list_emails():
    return sorted(p.name for p in EMAILS.glob("*.md"))


def safe_filename(name: str) -> str:
    name = Path(name).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return name or "upload"


def save_doc_upload(filename: str, b64data: str) -> str:
    if os.environ.get("VERCEL"):
        raise ValueError("uploads aren't supported on this deployed demo (read-only serverless filesystem) — run it locally to try uploads")
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


class handler(BaseHTTPRequestHandler):
    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, ctype: str):
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _route(self):
        """vercel.json rewrites /api/<x> to /api/index?route=<x> (the rewrite collapses the
        real path), so recover the intended route from that query param."""
        parsed = urlparse(self.path)
        route = parse_qs(parsed.query).get("route", [""])[0]
        return f"/api/{route}" if route else parsed.path

    def do_GET(self):
        route = self._route()
        if route == "/api/documents":
            return self._json({"files": list_docs()})
        if route == "/api/emails":
            return self._json({"files": list_emails()})
        if route == "/api/queries":
            return self._json({"queries": {k: v["text"] for k, v in R.QUERIES.items()}})
        self._json({"error": "not found"}, 404)

    def do_POST(self):
        route = self._route()
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        name = body.get("file", "")

        routes = {
            "/api/process_document": (D.classify, name),
            "/api/process_document_deepseek": (D.classify_via_deepseek, name),
            "/api/classify_email": (E.classify, name),
            "/api/classify_email_deepseek": (E.classify_via_deepseek, name),
        }
        if route in routes:
            fn, arg = routes[route]
            try:
                return self._json(timed(fn, arg))
            except Exception as e:
                return self._json({"file": name, "error": str(e)}, 500)

        if route == "/api/upload":
            try:
                saved = save_doc_upload(body.get("filename", ""), body.get("data", ""))
                return self._json({"ok": True, "file": saved})
            except Exception as e:
                return self._json({"ok": False, "error": str(e)}, 400)

        if route in ("/api/rerank_typesafe", "/api/rerank_deepseek"):
            query = body.get("query", "")
            fn = R.rerank_typesafe if route.endswith("typesafe") else R.rerank_deepseek
            try:
                return self._json(timed(fn, query))
            except Exception as e:
                return self._json({"query": query, "error": str(e)}, 500)

        self._json({"error": "not found"}, 404)

    def log_message(self, fmt, *args):
        pass
