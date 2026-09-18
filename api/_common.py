"""Shared logic for the per-route api/*.py handlers (Vercel maps each file to its own path)."""
import base64
import json
import os
import re
import sys
import time
from http.server import BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pipeline as P
import email_pipeline as E
import doc_pipeline as D
import retrieval_pipeline as R
import kb_pipeline as K
import design_pipeline as G

CORPORA = {"emails": R, "kb": K}

P.load_env()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "invoice_docs"
EMAILS = ROOT / "emails_samples"
DOC_EXTS = (".pdf", ".xlsx")


def list_docs():
    return sorted(p.name for p in DOCS.glob("*") if p.suffix.lower() in DOC_EXTS)


def list_emails():
    return sorted(p.name for p in EMAILS.glob("*.md"))


def list_design_screens():
    return G.list_screens()


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


class JsonHandler(BaseHTTPRequestHandler):
    """Base class: subclasses set GET_FN (no-arg) or POST_FN (arg-extractor, worker)."""
    GET_FN = None
    POST_FN = None  # (extract_arg(body) -> arg, worker_fn, error_key)

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        try:
            return self._json(self.GET_FN())
        except Exception as e:
            return self._json({"error": str(e)}, 500)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
        extract_arg, worker, error_key = self.POST_FN
        arg = extract_arg(body)
        try:
            return self._json(timed(worker, arg))
        except Exception as e:
            return self._json({error_key: arg, "error": str(e)}, 500)

    def log_message(self, fmt, *args):
        pass
