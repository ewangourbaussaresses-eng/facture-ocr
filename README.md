# 🧾 facture-ocr

**Déposez vos factures, récupérez un CSV propre.**

Extrait automatiquement le **fournisseur**, le **numéro**, la **date**, les **montants
(HT / TVA / TTC)**, le **taux de TVA** et la **catégorie** de chaque facture PDF ou
fichier texte, contrôle la cohérence comptable, puis exporte en CSV (compatible Excel et
LibreOffice), JSON ou Markdown.

Interface web (glisser-déposer) **et** ligne de commande. Aucune dépendance obligatoire,
les fichiers restent sur votre machine.

---

## Fonctionnalités

- lecture de PDF texte et de fichiers `.txt` sans dépendance externe ;
- extraction par **règles locales** (hors ligne) ou par **IA** (Claude, OpenAI, Ollama) ;
- **contrôles de cohérence** : HT + TVA = TTC, date valide, date dans le futur ;
- **catégorisation** automatique (hébergement, télécoms, transport, restauration, …) ;
- totaux par catégorie et total TTC ;
- export **CSV**, **JSON**, **Markdown** ;
- interface web : tableau, KPI par catégorie, téléchargement du CSV.

## Installation

```bash
git clone <url-du-depot>
cd facture-ocr
python -m venv .venv && source .venv/bin/activate
pip install -e .
```

Python 3.9+, aucune dépendance.

## Utilisation

### Interface web

```bash
facture-ocr serve          # http://127.0.0.1:8780
```

Glissez plusieurs factures, cliquez sur **Extraire**, puis **Télécharger le CSV**.

### Ligne de commande

```bash
# analyser un dossier entier et afficher le résumé
facture-ocr scan ./factures

# export CSV (séparateur virgule, prêt pour Excel)
facture-ocr scan ./factures --format csv --out factures.csv

# export JSON / Markdown
facture-ocr scan ./factures --format json
facture-ocr scan ./factures --format markdown --out recap.md

# sans IA
facture-ocr scan ./factures --no-llm
```

Exemple de sortie :

```
✔ 3 facture(s) → factures.csv

Total TTC : 196.60 €
  Hébergement        1 facture(s)        49.90 €
  Restauration       1 facture(s)        64.20 €
  Transport          1 facture(s)        82.50 €
```

Un jeu d'exemples est fourni dans `samples/`.

## Brancher une IA

```bash
export ANTHROPIC_API_KEY="sk-ant-..."   # Claude (recommandé)
# ou
export OPENAI_API_KEY="sk-..."
# ou, 100 % local :
export OLLAMA_MODEL="llama3.2"          # ollama serve doit tourner
```

`facture-ocr llm` affiche le fournisseur détecté. Sans clé, l'outil fonctionne quand
même : les règles locales comblent les champs, et si l'appel IA échoue les règles
prennent le relais.

## Limites (à lire avant de promettre monts et merveilles)

- **Les factures scannées** (photo, PDF image) ne sont **pas** lues : il n'y a pas d'OCR
  dans ce dépôt. Passez-les d'abord par `ocrmypdf facture.pdf facture-ocr.pdf`, puis
  donnez le PDF résultant à `facture-ocr`. L'outil signale explicitement ce cas.
- L'extraction par règles est fiable sur des factures **structurées** (« Total HT »,
  « TVA 20% », « Total TTC ») ; les mises en page exotiques demandent le mode IA.
- Les montants sont en euros ; les devises multiples ne sont pas gérées.
- Ne pas utiliser ce CSV comme comptabilité légale sans relecture humaine.

## Tests

```bash
python -m pytest -q     # 28 tests, aucun accès réseau
```

## Licence

MIT — voir [LICENSE](LICENSE).
