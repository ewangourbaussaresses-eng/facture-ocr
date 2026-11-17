"""Extraction des champs d'une facture : règles locales + option LLM."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from . import llm

SYSTEM = (
    "Tu es un assistant comptable. Tu extrais les données d'une facture française "
    "sans rien inventer : si une information est absente, mets null. Tu réponds "
    "UNIQUEMENT en JSON."
)

AMOUNT = r"(\d{1,3}(?:[ .]\d{3})*(?:[.,]\d{2})|\d+[.,]\d{2})"

DATE_PATTERNS = [
    r"\b(\d{2})[/.-](\d{2})[/.-](\d{4})\b",
    r"\b(\d{4})-(\d{2})-(\d{2})\b",
]

CATEGORY_RULES: list[tuple[str, str]] = [
    ("Hébergement", r"h[ée]bergement|serveur|vps|aws|amazon web|google cloud|azure|heroku|"
                    r"cloudflare|hosting|ovh|scaleway"),
    ("Télécoms", r"orange|sfr|bouygues|free|telecom|internet|mobile|forfait|fibre"),
    ("Transport", r"sncf|air france|uber|taxi|essence|totalenergies|carburant|train|avion"),
    ("Fournitures", r"bureau|papeterie|amazon|fourniture|cartouche|imprimante"),
    ("Restauration", r"restaurant|café|cafe|traiteur|déjeuner|repas"),
    ("Loyer", r"loyer|bail|immobilier|charges locatives"),
    ("Assurance", r"assurance|mutuelle|axa|maif|allianz|macif"),
    ("Comptabilité", r"comptable|expert-comptable|sage|cabinet"),
    ("Marketing", r"publicité|ads|google ads|meta|linkedin ads|seo|communication"),
    ("Formation", r"formation|cours|séminaire|udemy|coursera"),
    ("Énergie", r"edf|engie|électricité|electricite|gaz|eau"),
]

SUPPLIER_STOPWORDS = {"facture", "invoice", "total", "tva", "date", "client", "siret"}


def clean_amount(value: str) -> float | None:
    if not value:
        return None
    text = value.replace(" ", "").replace("\u00a0", "").replace(",", ".")
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def find_date(text: str) -> str | None:
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text):
            groups = match.groups()
            try:
                if len(groups[0]) == 4:
                    year, month, day = (int(g) for g in groups)
                else:
                    day, month, year = (int(g) for g in groups)
                return date(year, month, day).isoformat()
            except ValueError:
                continue
    return None


def find_total(text: str) -> tuple[float | None, float | None, float | None]:
    """(montant TTC, TVA, HT)."""
    ttc = tva = ht = None
    patterns = [
        (r"total\s*(?:ttc|g[ée]n[ée]ral|à payer)?\s*[:=]?\s*" + AMOUNT, "ttc"),
        (r"montant\s*total\s*[:=]?\s*" + AMOUNT, "ttc"),
        (r"(?:tva|t\.v\.a)\s*(?:\(?\d{1,2}(?:[.,]\d+)?\s*%?\)?)?\s*[:=]?\s*" + AMOUNT, "tva"),
        (r"(?:total\s*)?ht\s*[:=]?\s*" + AMOUNT, "ht"),
        (r"sous[- ]total\s*[:=]?\s*" + AMOUNT, "ht"),
    ]
    for pattern, kind in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            amount = clean_amount(match.group(1))
            if amount is None:
                continue
            if kind == "ttc" and ttc is None:
                ttc = amount
            elif kind == "tva" and tva is None:
                tva = amount
            elif kind == "ht" and ht is None:
                ht = amount
    if ttc is None and ht is not None and tva is not None:
        ttc = round(ht + tva, 2)
    if ht is None and ttc is not None and tva is not None:
        ht = round(ttc - tva, 2)
    return ttc, tva, ht


def find_supplier(text: str) -> str | None:
    for line in text.splitlines()[:12]:
        clean = line.strip()
        if len(clean) < 3 or len(clean) > 60:
            continue
        if clean.lower() in SUPPLIER_STOPWORDS:
            continue
        if re.search(r"\d{2}[/.-]\d{2}[/.-]\d{4}|facture\s*n|siret|tva", clean, re.IGNORECASE):
            continue
        if re.match(r"^[A-ZÀ-Ÿ0-9][\w\s&'.,\-]+$", clean):
            return clean
    return None


def find_invoice_number(text: str) -> str | None:
    match = re.search(r"(?:facture|invoice|n[°o])\s*(?:n[°o]\s*)?[:#]?\s*([A-Z0-9][A-Z0-9\-/]{2,20})",
                      text, re.IGNORECASE)
    return match.group(1).strip() if match else None


def find_vat_rate(text: str) -> float | None:
    match = re.search(r"tva\s*(?:à|a)?\s*(\d{1,2}(?:[.,]\d+)?)\s*%", text, re.IGNORECASE)
    return clean_amount(match.group(1)) if match else None


def categorize(text: str) -> str:
    lowered = text.lower()
    for category, pattern in CATEGORY_RULES:
        if re.search(pattern, lowered):
            return category
    return "Divers"


def extract_locally(text: str) -> dict[str, Any]:
    ttc, tva, ht = find_total(text)
    return {
        "fournisseur": find_supplier(text),
        "numero": find_invoice_number(text),
        "date": find_date(text),
        "montant_ttc": ttc,
        "tva": tva,
        "montant_ht": ht,
        "taux_tva": find_vat_rate(text),
        "categorie": categorize(text),
        "generated_by": "rules",
    }


def extract_with_llm(text: str) -> dict[str, Any] | None:
    categories = [c for c, _ in CATEGORY_RULES] + ["Divers"]
    prompt = f"""Extrais les données de cette facture.

Texte de la facture :
\"\"\"{text[:6000]}\"\"\"

Catégories autorisées : {', '.join(categories)}.

Réponds uniquement avec ce JSON :
{{"fournisseur": "nom ou null", "numero": "numéro ou null",
  "date": "AAAA-MM-JJ ou null", "montant_ttc": 0.0, "tva": 0.0,
  "montant_ht": 0.0, "taux_tva": 20.0, "categorie": "une des catégories"}}"""

    data = llm.ask_json(prompt, system=SYSTEM, max_tokens=600, temperature=0.1)
    if not isinstance(data, dict):
        return None
    for key in ("montant_ttc", "tva", "montant_ht"):
        data[key] = clean_amount(str(data.get(key))) if data.get(key) is not None else None
    data["categorie"] = data.get("categorie") if data.get("categorie") in categories else "Divers"
    data["generated_by"] = "llm"
    return data


def extract(text: str, use_llm: bool = True) -> dict[str, Any]:
    """Extraction complète : LLM si disponible, sinon règles. Fusion prudente."""
    local = extract_locally(text)
    if use_llm and llm.is_available():
        remote = extract_with_llm(text)
        if remote:
            # les règles comblent les champs que le modèle a laissés vides
            for key, value in local.items():
                if key in ("generated_by",):
                    continue
                if remote.get(key) in (None, "", "null"):
                    remote[key] = value
            return remote
    return local


def validate(record: dict[str, Any]) -> list[str]:
    """Contrôles de cohérence comptable."""
    problems: list[str] = []
    ttc, ht, tva = record.get("montant_ttc"), record.get("montant_ht"), record.get("tva")
    if ttc is None:
        problems.append("montant TTC manquant")
    if record.get("date") is None:
        problems.append("date manquante")
    if ttc is not None and ht is not None and tva is not None:
        if abs((ht + tva) - ttc) > 0.02:
            problems.append(f"HT + TVA ({ht + tva:.2f}) ≠ TTC ({ttc:.2f})")
    if record.get("date"):
        try:
            if datetime.fromisoformat(record["date"]).date() > date.today():
                problems.append("date dans le futur")
        except ValueError:
            problems.append("date invalide")
    return problems
