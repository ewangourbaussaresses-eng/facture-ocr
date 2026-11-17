"""Pipeline : dossier (ou fichier) → factures extraites → export."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .extract import extract, validate
from .pdf_text import PDFError, extract_pdf_text
from .utils import get_logger

log = get_logger("facture-ocr")

SUPPORTED = {".pdf", ".txt"}


def read_document(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        return extract_pdf_text(path)
    return path.read_text(encoding="utf-8", errors="replace")


def collect_files(target: Path) -> list[Path]:
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*") if p.suffix.lower() in SUPPORTED)


def process_file(path: Path, use_llm: bool = True) -> dict[str, Any]:
    record: dict[str, Any] = {"fichier": path.name, "source": str(path)}
    try:
        text = read_document(path)
    except (PDFError, OSError) as exc:
        record.update({"erreur": str(exc), "anomalies": [str(exc)], "generated_by": "aucun"})
        return record

    data = extract(text, use_llm=use_llm)
    record.update(data)
    record["anomalies"] = validate(record)
    record["chars"] = len(text)
    record.pop("source", None)  # chemin local inutile côté client
    return record


def process(target: str | Path, use_llm: bool = True) -> list[dict[str, Any]]:
    target = Path(target)
    files = collect_files(target)
    if not files:
        log.warning("aucun fichier .pdf ou .txt dans %s", target)
        return []
    records = []
    for path in files:
        log.info("analyse de %s", path.name)
        records.append(process_file(path, use_llm=use_llm))
    return records
