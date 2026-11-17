"""Extraction du texte d'un PDF (copie légère du module pdf-quiz)."""
from __future__ import annotations

import re
import zlib
from pathlib import Path


class PDFError(RuntimeError):
    pass


def _decode_streams(raw: bytes) -> list[str]:
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n", raw):
        start = match.end()
        end = raw.find(b"endstream", start)
        if end == -1:
            continue
        data = raw[start:end].rstrip(b"\r\n")
        try:
            chunks.append(zlib.decompress(data).decode("latin-1"))
        except zlib.error:
            chunks.append(data.decode("latin-1", errors="replace"))
    if not chunks:
        chunks.append(raw.decode("latin-1", errors="replace"))
    return chunks


def _unescape(text: str) -> str:
    for source, target in ((r"\n", "\n"), (r"\r", "\r"), (r"\t", "\t"),
                           (r"\(", "("), (r"\)", ")"), (r"\\", "\\")):
        text = text.replace(source, target)
    return re.sub(r"\\([0-7]{1,3})", lambda m: chr(int(m.group(1), 8)), text)


def _text_from_content(content: str) -> str:
    out: list[str] = []
    for match in re.finditer(r"\((?:\\.|[^\\()])*\)\s*Tj|\[(.*?)\]\s*TJ|T\*|Td|TD|ET",
                             content, re.DOTALL):
        token = match.group(0)
        if token.endswith("Tj"):
            inner = token[: token.rfind(")")]
            out.append(_unescape(inner[inner.find("(") + 1:]))
        elif token.endswith("TJ") and match.group(1):
            parts = re.findall(r"\((?:\\.|[^\\()])*\)", match.group(1))
            out.append("".join(_unescape(p[1:-1]) for p in parts))
        else:
            out.append("\n")
    text = "".join(out)
    return re.sub(r"\n{3,}", "\n\n", re.sub(r"[ \t]+", " ", text)).strip()


def extract_pdf_text(path: str | Path) -> str:
    path = Path(path)
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF"):
        raise PDFError("ce fichier n'est pas un PDF")
    text = "\n".join(t for t in (_text_from_content(c) for c in _decode_streams(raw)) if t)
    if len(text.strip()) < 15:
        raise PDFError("aucun texte extractible (facture scannée : OCR requis)")
    return text
