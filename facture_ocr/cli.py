"""CLI facture-ocr."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, llm
from .export import summary_by_category, write_output
from .pipeline import process
from .web import serve


def command_scan(args: argparse.Namespace) -> int:
    records = process(args.target, use_llm=not args.no_llm)
    if not records:
        print("✖ aucune facture trouvée", file=sys.stderr)
        return 1

    if args.format == "json" and not args.out:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        fmt = args.format if args.format != "text" else "csv"
        out = args.out or f"factures.{ 'csv' if fmt == 'csv' else ('json' if fmt == 'json' else 'md') }"
        path = write_output(records, out, fmt)
        print(f"✔ {len(records)} facture(s) → {path}")

    if not args.quiet:
        print("\nTotal TTC : "
              f"{sum(r.get('montant_ttc') or 0 for r in records):.2f} €")
        for category, count, total in summary_by_category(records):
            print(f"  {category:<16} {count:>3} facture(s)   {total:>10.2f} €")
        anomalies = [r for r in records if r.get("anomalies")]
        if anomalies:
            print(f"\n⚠ {len(anomalies)} facture(s) à vérifier :")
            for record in anomalies:
                print(f"  - {record['fichier']} : {'; '.join(record['anomalies'])}")
    return 0


def command_serve(args: argparse.Namespace) -> int:
    serve(host=args.host, port=args.port)
    return 0


def command_llm(args: argparse.Namespace) -> int:
    info = llm.status()
    if args.json:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    print(f"Fournisseur : {info['provider']} "
          f"({'connecté' if info['available'] else 'non configuré'})")
    if info["model"]:
        print(f"Modèle      : {info['model']}")
    if not info["available"]:
        print("→ Sans clé, l'extraction utilise les règles locales (hors ligne).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="facture-ocr",
        description="Extrait les données de factures PDF/txt et les exporte en CSV.")
    parser.add_argument("--version", action="version", version=f"facture-ocr {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="analyser un fichier ou un dossier")
    scan.add_argument("target", help="fichier ou dossier de factures")
    scan.add_argument("--format", choices=["text", "csv", "json", "markdown"], default="text")
    scan.add_argument("--out", help="fichier de sortie")
    scan.add_argument("--no-llm", action="store_true", help="forcer les règles locales")
    scan.add_argument("--quiet", action="store_true", help="pas de résumé")
    scan.set_defaults(func=command_scan)

    web = sub.add_parser("serve", help="lancer l'interface web")
    web.add_argument("--port", type=int, default=8780)
    web.add_argument("--host", default="127.0.0.1")
    web.set_defaults(func=command_serve)

    llm_cmd = sub.add_parser("llm", help="état du connecteur IA")
    llm_cmd.add_argument("--json", action="store_true")
    llm_cmd.set_defaults(func=command_llm)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
