"""Tests facture-ocr — échantillons locaux, aucun accès réseau."""
from __future__ import annotations

import json
import sys
import zlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from facture_ocr import llm  # noqa: E402
from facture_ocr.cli import main  # noqa: E402
from facture_ocr.export import (summary_by_category, to_csv, to_json,  # noqa: E402
                                to_markdown)
from facture_ocr.extract import (categorize, clean_amount, extract,  # noqa: E402
                                 extract_locally, find_date, find_invoice_number,
                                 find_supplier, find_total, find_vat_rate, validate)
from facture_ocr.pipeline import process, process_file  # noqa: E402
from facture_ocr.web import _parse_multipart  # noqa: E402
from facture_ocr.web_assets import INDEX_HTML  # noqa: E402

FACTURE = """OVH SAS
2 rue Kellermann
59100 Roubaix

FACTURE N° FR-2026-004512
Date : 12/03/2026

Hébergement serveur VPS - mars 2026
Total HT : 41,58
TVA 20% : 8,32
Total TTC : 49,90
"""

INCOHERENTE = """Fournisseur Test
Facture n° A1
Date : 01/02/2026
Total HT : 100,00
TVA 20% : 20,00
Total TTC : 150,00
"""


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LLM_PROVIDER", "OLLAMA_MODEL"):
        monkeypatch.delenv(var, raising=False)
    yield


@pytest.fixture()
def dossier(tmp_path: Path) -> Path:
    (tmp_path / "ovh.txt").write_text(FACTURE, encoding="utf-8")
    (tmp_path / "anomalie.txt").write_text(INCOHERENTE, encoding="utf-8")
    return tmp_path


# --------------------------------------------------------------------------- #
# Extraction locale
# --------------------------------------------------------------------------- #
def test_clean_amount_formats_francais():
    assert clean_amount("1 234,56") == 1234.56
    assert clean_amount("49.90") == 49.9
    assert clean_amount("") is None
    assert clean_amount("abc") is None


def test_find_date_formats():
    assert find_date("Date : 12/03/2026") == "2026-03-12"
    assert find_date("Le 2026-03-12") == "2026-03-12"
    assert find_date("31/02/2026") is None  # date impossible
    assert find_date("aucune date") is None


def test_find_total():
    ttc, tva, ht = find_total(FACTURE)
    assert (ttc, tva, ht) == (49.9, 8.32, 41.58)


def test_find_total_complete_ttc_manquant():
    text = "Total HT : 100,00\nTVA 20% : 20,00"
    ttc, tva, ht = find_total(text)
    assert ttc == 120.0


def test_find_supplier_ignore_les_lignes_techniques():
    assert find_supplier(FACTURE) == "OVH SAS"
    assert find_supplier("FACTURE N° 12\nDate : 12/03/2026\nACME SAS") == "ACME SAS"


def test_find_invoice_number():
    assert find_invoice_number(FACTURE) == "FR-2026-004512"


def test_find_vat_rate():
    assert find_vat_rate(FACTURE) == 20.0
    assert find_vat_rate("sans taxe") is None


def test_categorize():
    assert categorize("Hébergement serveur VPS chez OVH") == "Hébergement"
    assert categorize("Restaurant déjeuner") == "Restauration"
    assert categorize("Billet de train SNCF") == "Transport"
    assert categorize("Objet inconnu") == "Divers"


def test_extract_locally_complet():
    record = extract_locally(FACTURE)
    assert record["fournisseur"] == "OVH SAS"
    assert record["date"] == "2026-03-12"
    assert record["montant_ttc"] == 49.9
    assert record["generated_by"] == "rules"


# --------------------------------------------------------------------------- #
# Contrôles
# --------------------------------------------------------------------------- #
def test_validate_ok():
    assert validate(extract_locally(FACTURE)) == []


def test_validate_incoherence():
    problems = validate(extract_locally(INCOHERENTE))
    assert any("≠ TTC" in p for p in problems)


def test_validate_champs_manquants():
    problems = validate({"montant_ttc": None, "date": None})
    assert "montant TTC manquant" in problems
    assert "date manquante" in problems


def test_validate_date_future():
    problems = validate({"montant_ttc": 10, "date": "2999-01-01"})
    assert "date dans le futur" in problems


# --------------------------------------------------------------------------- #
# Pipeline
# --------------------------------------------------------------------------- #
def test_process_dossier(dossier: Path):
    records = process(dossier)
    assert len(records) == 2
    ovh = next(r for r in records if r["fichier"] == "ovh.txt")
    assert ovh["montant_ttc"] == 49.9
    assert ovh["anomalies"] == []


def test_process_fichier_invalide(tmp_path: Path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"pas un pdf")
    record = process_file(bad)
    assert "erreur" in record
    assert record["generated_by"] == "aucun"


def test_process_pdf(tmp_path: Path):
    lines = ["ACME SAS", "FACTURE N° 42", "Date : 10/01/2026",
             "Total HT : 100,00", "TVA 20% : 20,00", "Total TTC : 120,00"]
    parts = ["BT", "/F1 11 Tf", "72 760 Td", "14 TL"]
    parts += [f"({l}) Tj T*" for l in lines] + ["ET"]
    compressed = zlib.compress("\n".join(parts).encode("latin-1"))
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
               b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
               b"<< /Length " + str(len(compressed)).encode() +
               b" /Filter /FlateDecode >>\nstream\n" + compressed + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects)+1}\n".encode() + b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    pdf = tmp_path / "facture.pdf"
    pdf.write_bytes(bytes(out))

    record = process_file(pdf)
    assert record["fournisseur"] == "ACME SAS"
    assert record["montant_ttc"] == 120.0


# --------------------------------------------------------------------------- #
# LLM simulé
# --------------------------------------------------------------------------- #
def test_extract_llm_simule(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "fournisseur": "OVH", "numero": "X1", "date": "2026-03-12",
        "montant_ttc": 49.9, "tva": 8.32, "montant_ht": 41.58,
        "taux_tva": 20.0, "categorie": "Hébergement"})
    record = extract(FACTURE)
    assert record["generated_by"] == "llm"
    assert record["categorie"] == "Hébergement"


def test_extract_llm_champs_vides_combles(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: {
        "fournisseur": None, "numero": None, "date": None, "montant_ttc": None,
        "tva": None, "montant_ht": None, "taux_tva": None, "categorie": "Télécoms"})
    record = extract(FACTURE)
    assert record["fournisseur"] == "OVH SAS"   # comblé par les règles
    assert record["montant_ttc"] == 49.9


def test_extract_repli_si_llm_none(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setattr(llm, "ask_json", lambda *a, **k: None)
    assert extract(FACTURE)["generated_by"] == "rules"


# --------------------------------------------------------------------------- #
# Export
# --------------------------------------------------------------------------- #
def test_csv_contient_les_colonnes(dossier: Path):
    records = process(dossier)
    csv_text = to_csv(records)
    assert csv_text.splitlines()[0].startswith("fichier,fournisseur")
    assert "49.9" in csv_text


def test_json_export(dossier: Path):
    records = process(dossier)
    assert json.loads(to_json(records))[0]["fichier"]


def test_markdown_export(dossier: Path):
    text = to_markdown(process(dossier))
    assert "Total TTC" in text


def test_summary_par_categorie(dossier: Path):
    summary = summary_by_category(process(dossier))
    assert sum(count for _, count, _ in summary) == 2


# --------------------------------------------------------------------------- #
# CLI et web
# --------------------------------------------------------------------------- #
def test_cli_csv(dossier: Path, tmp_path: Path, capsys):
    out = tmp_path / "out.csv"
    assert main(["scan", str(dossier), "--format", "csv", "--out", str(out)]) == 0
    assert out.exists()


def test_cli_aucun_fichier(tmp_path: Path, capsys):
    assert main(["scan", str(tmp_path)]) == 1


def test_cli_llm(capsys):
    assert main(["llm"]) == 0
    assert "Fournisseur" in capsys.readouterr().out


def test_parse_multipart_facture():
    boundary = b"B"
    body = (b"--B\r\nContent-Disposition: form-data; name=\"files\"; filename=\"f.pdf\"\r\n"
            b"Content-Type: application/pdf\r\n\r\n%PDF-1.4\r\n--B--\r\n")
    fields = _parse_multipart(body, boundary)
    assert fields["files"][0][0] == "f.pdf"


def test_index_html():
    for marker in ("Déposez des factures", "api/extract", "Télécharger le CSV"):
        assert marker in INDEX_HTML
