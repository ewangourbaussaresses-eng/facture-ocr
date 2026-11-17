"""HTML de l'interface facture-ocr (séparé pour rester lisible)."""

INDEX_HTML = """<!doctype html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Factures — extraction automatique</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#262b36; --text:#e6e8ee;
          --muted:#98a0b3; --accent:#6ea8fe; --ok:#3fb950; --bad:#f85149; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.55 -apple-system,"Segoe UI",Roboto,sans-serif;
         background:var(--bg); color:var(--text); }
  header { max-width:1080px; margin:0 auto; padding:28px 24px 8px; }
  h1 { font-size:24px; margin:0 0 6px; letter-spacing:-.02em; }
  .sub { color:var(--muted); font-size:14px; }
  main { max-width:1080px; margin:0 auto; padding:12px 24px 64px; }
  .panel { background:var(--panel); border:1px solid var(--line); border-radius:12px;
           padding:18px; margin-bottom:18px; }
  .drop { border:2px dashed var(--line); border-radius:12px; padding:30px;
          text-align:center; color:var(--muted); cursor:pointer; transition:.15s; }
  .drop.over { border-color:var(--accent); background:#1b2130; color:var(--text); }
  .row { display:flex; gap:12px; flex-wrap:wrap; align-items:center; margin-top:14px; }
  button { background:var(--accent); color:#07101f; border:0; border-radius:8px;
           padding:9px 16px; font-weight:600; cursor:pointer; }
  button.ghost { background:transparent; color:var(--text); border:1px solid var(--line); }
  button:disabled { opacity:.5; cursor:progress; }
  .badge { font-size:12px; color:var(--muted); border:1px solid var(--line);
           border-radius:999px; padding:3px 10px; }
  table { width:100%; border-collapse:collapse; font-size:13.5px; }
  th,td { text-align:left; padding:9px 10px; border-bottom:1px solid var(--line); }
  th { color:var(--muted); font-weight:600; font-size:12px; text-transform:uppercase;
       letter-spacing:.04em; }
  td.num { text-align:right; font-variant-numeric:tabular-nums; }
  tr:hover td { background:#12151c; }
  .warn { color:#d29922; font-size:12px; }
  .err { color:var(--bad); }
  .kpis { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
  .kpi { background:#12151c; border:1px solid var(--line); border-radius:10px; padding:14px; }
  .kpi .v { font-size:22px; font-weight:700; letter-spacing:-.02em; }
  .kpi .l { color:var(--muted); font-size:12px; }
  footer { color:var(--muted); font-size:12px; text-align:center; padding:24px; }
</style>
</head>
<body>
<header>
  <h1>Factures — extraction automatique</h1>
  <div class="sub">Déposez vos factures PDF ou vos tickets en texte : fournisseur, montants,
    TVA, date et catégorie sont extraits, puis exportés en CSV.</div>
</header>
<main>
  <div class="panel">
    <div class="drop" id="drop">
      <strong>Déposez des factures ici</strong><br>
      PDF ou .txt — plusieurs fichiers acceptés
      <input type="file" id="file" accept=".pdf,.txt" multiple hidden>
    </div>
    <div class="row">
      <button id="go" disabled>Extraire</button>
      <button class="ghost" id="csv" disabled>Télécharger le CSV</button>
      <span class="badge" id="engine">moteur : —</span>
      <span class="badge" id="count">0 facture</span>
    </div>
    <div id="status" class="sub" style="margin-top:12px"></div>
  </div>
  <div class="kpis" id="kpis"></div>
  <div class="panel" id="tableWrap" hidden>
    <table>
      <thead><tr>
        <th>Fichier</th><th>Fournisseur</th><th>N°</th><th>Date</th>
        <th>HT</th><th>TVA</th><th>TTC</th><th>Catégorie</th><th>Contrôles</th>
      </tr></thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
</main>
<footer>facture-ocr · les fichiers restent sur votre machine</footer>
<script>
const drop = document.getElementById('drop');
const fileInput = document.getElementById('file');
const go = document.getElementById('go');
const csvBtn = document.getElementById('csv');
const statusEl = document.getElementById('status');
const rowsEl = document.getElementById('rows');
const kpisEl = document.getElementById('kpis');
const engineEl = document.getElementById('engine');
const countEl = document.getElementById('count');
let csvData = '', total = 0;

fetch('/api/status').then(r => r.json()).then(s => {
  engineEl.textContent = 'moteur : ' + (s.available ? s.provider : 'règles locales');
});

function filesPicked() {
  const n = fileInput.files.length;
  go.disabled = n === 0;
  countEl.textContent = n + ' fichier' + (n > 1 ? 's' : '');
  statusEl.textContent = n ? 'prêt à extraire' : '';
}

drop.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', filesPicked);
['dragenter','dragover'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.add('over');
}));
['dragleave','drop'].forEach(ev => drop.addEventListener(ev, e => {
  e.preventDefault(); drop.classList.remove('over');
}));
drop.addEventListener('drop', e => { fileInput.files = e.dataTransfer.files; filesPicked(); });

go.addEventListener('click', async () => {
  go.disabled = true;
  statusEl.textContent = 'extraction en cours…';
  const form = new FormData();
  [...fileInput.files].forEach(f => form.append('files', f));
  try {
    const res = await fetch('/api/extract', { method: 'POST', body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'erreur serveur');
    csvData = data.csv;
    render(data);
    csvBtn.disabled = false;
    countEl.textContent = data.records.length + ' facture' + (data.records.length > 1 ? 's' : '');
    statusEl.textContent = 'extraction terminée';
  } catch (err) {
    statusEl.innerHTML = '<span class="err">' + err.message + '</span>';
  } finally {
    go.disabled = false;
  }
});

function money(v) {
  return (v === null || v === undefined || v === '') ? '—'
    : Number(v).toLocaleString('fr-FR', { minimumFractionDigits: 2 }) + ' €';
}
function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

function render(data) {
  rowsEl.innerHTML = '';
  data.records.forEach(r => {
    const tr = document.createElement('tr');
    const flags = (r.anomalies || []).length
      ? '<span class="warn">' + esc(r.anomalies.join(' ; ')) + '</span>'
      : (r.erreur ? '<span class="err">' + esc(r.erreur) + '</span>' : '✓');
    tr.innerHTML =
      '<td>' + esc(r.fichier) + '</td>' +
      '<td>' + esc(r.fournisseur || '—') + '</td>' +
      '<td>' + esc(r.numero || '—') + '</td>' +
      '<td>' + esc(r.date || '—') + '</td>' +
      '<td class="num">' + money(r.montant_ht) + '</td>' +
      '<td class="num">' + money(r.tva) + '</td>' +
      '<td class="num">' + money(r.montant_ttc) + '</td>' +
      '<td>' + esc(r.categorie || '—') + '</td>' +
      '<td>' + flags + '</td>';
    rowsEl.appendChild(tr);
  });
  document.getElementById('tableWrap').hidden = false;

  kpisEl.innerHTML = '';
  const totalKpi = document.createElement('div');
  totalKpi.className = 'kpi';
  totalKpi.innerHTML = '<div class="v">' + money(data.total_ttc) +
                       '</div><div class="l">Total TTC</div>';
  kpisEl.appendChild(totalKpi);
  data.totaux.forEach(([cat, n, sum]) => {
    const el = document.createElement('div');
    el.className = 'kpi';
    el.innerHTML = '<div class="v">' + money(sum) + '</div><div class="l">' +
                   esc(cat) + ' · ' + n + ' facture(s)</div>';
    kpisEl.appendChild(el);
  });
}

csvBtn.addEventListener('click', () => {
  if (!csvData) return;
  const blob = new Blob(['\\ufeff' + csvData], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'factures.csv'; a.click();
  URL.revokeObjectURL(url);
});
</script>
</body>
</html>
"""
