"""Export CSV / JSON / Markdown des factures extraites."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

COLUMNS = ["fichier", "fournisseur", "numero", "date", "montant_ht", "tva",
           "montant_ttc", "taux_tva", "categorie", "anomalies", "moteur"]


def normalize(record: dict[str, Any], filename: str = "") -> dict[str, Any]:
    row = {column: record.get(column) for column in COLUMNS}
    row["fichier"] = filename or record.get("fichier", "")
    row["anomalies"] = "; ".join(record.get("anomalies") or [])
    row["moteur"] = record.get("generated_by", "")
    return row


def to_csv(records: list[dict[str, Any]], delimiter: str = ",") -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=COLUMNS, delimiter=delimiter,
                            lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    for record in records:
        row = normalize(record, record.get("fichier", ""))
        if delimiter == ";":
            row = {k: (str(v).replace(".", ",") if isinstance(v, float) else v)
                   for k, v in row.items()}
        writer.writerow(row)
    return buffer.getvalue()


def to_json(records: list[dict[str, Any]]) -> str:
    return json.dumps(records, ensure_ascii=False, indent=2)


def to_markdown(records: list[dict[str, Any]]) -> str:
    lines = ["| " + " | ".join(COLUMNS[:9]) + " |",
             "|" + "|".join(["---"] * 9) + "|"]
    for record in records:
        values = []
        for column in COLUMNS[:9]:
            value = record.get(column)
            if isinstance(value, float):
                value = f"{value:.2f}"
            values.append("" if value is None else str(value))
        lines.append("| " + " | ".join(values) + " |")
    total = sum(r.get("montant_ttc") or 0 for r in records)
    lines += ["", f"**Total TTC : {total:.2f} €** — {len(records)} facture(s)"]
    return "\n".join(lines)


def write_output(records: list[dict[str, Any]], path: str | Path, fmt: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = {"csv": to_csv, "json": to_json, "markdown": to_markdown}[fmt](records)
    path.write_text(content, encoding="utf-8")
    return path


def summary_by_category(records: list[dict[str, Any]]) -> list[tuple[str, int, float]]:
    totals: dict[str, list[float]] = {}
    for record in records:
        category = record.get("categorie") or "Divers"
        entry = totals.setdefault(category, [0, 0.0])
        entry[0] += 1
        entry[1] += record.get("montant_ttc") or 0
    return sorted(((c, int(v[0]), round(v[1], 2)) for c, v in totals.items()),
                  key=lambda item: -item[2])
