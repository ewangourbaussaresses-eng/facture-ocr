"""Interface web (stdlib) : glisser-déposer des factures, tableau, export CSV."""
from __future__ import annotations

import json
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from . import llm
from .export import to_csv, summary_by_category
from .pipeline import process_file
from .web_assets import INDEX_HTML

MAX_UPLOAD = 20 * 1024 * 1024


def _parse_multipart(body: bytes, boundary: bytes) -> dict[str, list[tuple[str, bytes]]]:
    fields: dict[str, list[tuple[str, bytes]]] = {}
    for part in body.split(b"--" + boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, data = part.split(b"\r\n\r\n", 1)
        data = data.rstrip(b"\r\n-")
        import re
        name_match = re.search(rb'name="([^"]+)"', head)
        if not name_match:
            continue
        name = name_match.group(1).decode()
        filename_match = re.search(rb'filename="([^"]*)"', head)
        filename = filename_match.group(1).decode() if filename_match else ""
        fields.setdefault(name, []).append((filename, data))
    return fields


def create_handler() -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "facture-ocr/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            return

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: Any) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode(),
                       "application/json")

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, INDEX_HTML.encode(), "text/html; charset=utf-8")
            elif path == "/api/status":
                self._json(200, llm.status())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path != "/api/extract":
                self._json(404, {"error": "not found"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_UPLOAD:
                self._json(413, {"error": "envoi trop volumineux (20 Mo max)"})
                return
            content_type = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in content_type:
                self._json(400, {"error": "multipart/form-data attendu"})
                return
            boundary = content_type.split("boundary=", 1)[-1].encode()
            fields = _parse_multipart(self.rfile.read(length), boundary)
            uploads = fields.get("files") or []
            if not uploads:
                self._json(400, {"error": "aucun fichier reçu"})
                return

            records = []
            for filename, data in uploads:
                suffix = Path(filename).suffix.lower() or ".pdf"
                tmp = Path(tempfile.gettempdir()) / f"facture-{abs(hash(filename))}{suffix}"
                tmp.write_bytes(data)
                try:
                    records.append(process_file(tmp))
                finally:
                    tmp.unlink(missing_ok=True)
                records[-1]["fichier"] = filename

            self._json(200, {
                "records": records,
                "csv": to_csv(records),
                "totaux": summary_by_category(records),
                "total_ttc": round(sum(r.get("montant_ttc") or 0 for r in records), 2),
            })

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8780) -> None:
    server = ThreadingHTTPServer((host, port), create_handler())
    print(f"facture-ocr → http://{host}:{port}  (Ctrl+C pour arrêter)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()
