#!/usr/bin/env python3
"""IL REFERTO ANAGRAFICO — una diagnosi sul vivaio di un club, in una pagina.

    python3 referto_anagrafico.py --csv rosa.csv --societa "AC Esempio"

Gli dai la cosa meno sensibile che un club possieda — nomi e date di nascita
del settore giovanile — e restituisce una pagina HTML autonoma (si apre con
doppio clic, funziona senza rete) che mostra QUANTO IL LORO STESSO PROCESSO
DI SELEZIONE sia sbilanciato sul mese di nascita, e quali dei loro ragazzi
sono passati dal filtro piu' stretto.

PERCHE' ESISTE QUESTO FILE. E' l'unica parte del sistema che non ha il
problema di copertura di tutto il resto: sul feed di produzione solo il 4.5%
dei candidati ha piu' del dato anagrafico, e la validazione va dal 68% in
Segunda allo 0% in Serie C. La data di nascita invece ce l'hanno TUTTI,
sempre, in ogni database che possiedono. Copertura 100%, nessuna API,
nessuna chiave, nessun accordo da firmare.

REGOLA DI SCRITTURA, non negoziabile: nel referto NON compare una sola
parola che richieda una spiegazione. Niente "chi-quadro", niente "p-value",
niente "effetto eta' relativa". Il chi-quadro c'e' ed e' calcolato con lo
stesso codice del radar (misura_coorte_anagrafica) - ma al lettore arriva
come "la probabilita' che sia un caso e' meno di 1 su 1000". Se serve un
glossario per leggerlo, il referto ha fallito.

ONESTA' OBBLIGATORIA (vedi _VERDETTI e la sezione "cosa NON dice"): lo
sbilanciamento della selezione e' un fatto misurabile sui loro dati.
L'inversione - che i nati tardi sopravvissuti rendano MEGLIO dopo - e'
documentata ma dibattuta, e nel referto e' presentata come ipotesi da
verificare con l'occhio. Venderla come acquisita significa perdere la
stanza davanti al primo analista che conosce la letteratura.
"""
import argparse
import csv
import re
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment

sys.path.insert(0, str(Path(__file__).resolve().parent))
from discovery_engine import _conta_trimestri, _statistiche_coorte, load_config

# Sotto questa soglia non si dice NIENTE: su venti ragazzi qualunque
# sbilanciamento e' compatibile col caso, e un referto che parlasse comunque
# sarebbe esattamente il tipo di numero gonfiato che questo progetto rifiuta.
MINIMO_PER_PARLARE = 25

TRIMESTRI = {
    1: ("gennaio – marzo", "i piu' grandi della loro annata"),
    2: ("aprile – giugno", ""),
    3: ("luglio – settembre", ""),
    4: ("ottobre – dicembre", "i piu' piccoli della loro annata"),
}

# Il chi-quadro tradotto. Soglie standard con 3 gradi di liberta'.
_VERDETTI = [
    (16.27, "meno di 1 su 1000", "forte"),
    (11.34, "meno di 1 su 100", "chiaro"),
    (7.81, "meno di 1 su 20", "probabile"),
]

COLONNE_NOME = ("nome", "name", "giocatore", "player", "cognome", "atleta", "nominativo")
COLONNE_DATA = ("data_nascita", "data di nascita", "datanascita", "nascita", "dob",
                "birthdate", "birth_date", "nato", "nato il", "data")


def _norm(s: str) -> str:
    return re.sub(r"[^a-z ]", "_", (s or "").strip().lower()).replace("__", "_").strip("_ ")


def _trova_colonne(intestazioni: list[str]) -> tuple[str | None, str | None]:
    """Riconosce le colonne comunque il club abbia chiamato il suo file. Un
    referto che pretende un formato esatto non lo apre nessuno."""
    col_nome = col_data = None
    for h in intestazioni:
        n = _norm(h)
        if col_nome is None and any(k in n for k in COLONNE_NOME):
            col_nome = h
        if col_data is None and any(k in n for k in COLONNE_DATA):
            col_data = h
    return col_nome, col_data


_FORMATI = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%y")


def _parse_data(valore: str) -> str | None:
    """-> 'YYYY-MM-DD', oppure None. Mai una data indovinata: una riga con la
    data illeggibile viene contata fra gli scarti e dichiarata nel referto,
    non silenziosamente buttata."""
    v = (valore or "").strip()
    if not v:
        return None
    for f in _FORMATI:
        try:
            d = datetime.strptime(v[:10] if len(v) > 10 and f == "%Y-%m-%d" else v, f)
            if d.year < 1900 or d > datetime.now():
                return None
            return d.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def leggi_csv(percorso: Path) -> tuple[list[dict], list[str]]:
    """Legge il file del club. Restituisce (righe valide, problemi da dichiarare)."""
    testo = percorso.read_text(encoding="utf-8-sig", errors="replace")
    # il separatore lo decide il file, non noi: molti export italiani usano ';'
    try:
        dialetto = csv.Sniffer().sniff(testo[:4096], delimiters=",;\t")
    except csv.Error:
        dialetto = csv.excel
    righe = list(csv.DictReader(testo.splitlines(), dialect=dialetto))
    if not righe:
        raise SystemExit(f"Il file {percorso} sembra vuoto.")

    col_nome, col_data = _trova_colonne(list(righe[0].keys()))
    if col_data is None:
        raise SystemExit(
            f"Non trovo una colonna con la data di nascita in {percorso}.\n"
            f"Colonne presenti: {', '.join(righe[0].keys())}\n"
            f"Rinominane una in 'data_nascita' (o 'nato', 'dob') e riprova.")

    validi, problemi = [], []
    for i, r in enumerate(righe, 2):
        dob = _parse_data(r.get(col_data, ""))
        nome = (r.get(col_nome) or "").strip() if col_nome else ""
        if not dob:
            problemi.append(f"riga {i}: data non leggibile ('{r.get(col_data, '')}')")
            continue
        validi.append({"nome": nome or f"(senza nome, riga {i})", "dob": dob,
                       "extra": {k: v for k, v in r.items() if k not in (col_nome, col_data)}})
    return validi, problemi


def costruisci_referto(giocatori: list[dict], societa: str, cfg: dict) -> dict:
    """Il calcolo. Stessa funzione del radar (_conta_trimestri /
    _statistiche_coorte): i numeri del referto e quelli del sistema non
    possono divergere, altrimenti un giorno qualcuno se ne accorge davanti
    a un cliente."""
    taglio = cfg["kenobi"]["effetto_eta"]["mese_taglio"]
    conteggi = _conta_trimestri(giocatori, taglio)
    stat = _statistiche_coorte(conteggi, MINIMO_PER_PARLARE)
    n = stat["n"]

    if not stat["calibrata"]:
        return {"societa": societa, "n": n, "abbastanza": False,
                "messaggio": (f"Il gruppo e' di {n} ragazzi: troppo pochi perche' un numero "
                              f"del genere voglia dire qualcosa. Servono almeno "
                              f"{MINIMO_PER_PARLARE} date di nascita.")}

    chi2 = stat["chi_quadro"]
    probabilita, forza = "piu' di 1 su 20", None
    for soglia, testo, f in _VERDETTI:
        if chi2 >= soglia:
            probabilita, forza = testo, f
            break

    barre = []
    for t in (1, 2, 3, 4):
        etichetta, nota = TRIMESTRI[t]
        barre.append({"trimestre": t, "etichetta": etichetta, "nota": nota,
                      "n": conteggi[t], "quota": stat["quote"][t],
                      "rarita": stat["rarita"][t]})

    q1, q4 = conteggi[1], conteggi[4]
    rapporto = (q1 / q4) if q4 else None

    # I ragazzi nati negli ultimi mesi: sono LORO il contenuto del referto.
    # Ordinati per data DECRESCENTE - i nati piu' vicini a fine anno per primi,
    # cioe' quelli che hanno passato il filtro piu' stretto.
    def _tri(g):
        m = int(g["dob"][5:7])
        return (m - taglio) % 12 // 3 + 1

    tardivi = sorted([g for g in giocatori if _tri(g) == 4],
                     key=lambda g: g["dob"][5:], reverse=True)
    for g in tardivi:
        d = datetime.strptime(g["dob"], "%Y-%m-%d")
        g["nato_il"] = d.strftime("%d/%m/%Y")
        g["eta"] = round((datetime.now() - d).days / 365.25, 1)

    return {
        "societa": societa, "n": n, "abbastanza": True, "barre": barre,
        "probabilita": probabilita, "forza": forza,
        "sbilanciato": forza is not None,
        "rapporto": round(rapporto, 1) if rapporto else None,
        "q1": q1, "q4": q4,
        "quota_q1": stat["quote"][1], "quota_q4": stat["quote"][4],
        "rarita_q4": stat["rarita"][4],
        "tardivi": tardivi,
        "chi2": chi2,  # resta nel metodo in fondo, non nel corpo del referto
    }


TEMPLATE = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Referto anagrafico{% if r.societa %} • {{ r.societa }}{% endif %}</title>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
 --bg-primary:#0f1117;--bg-card:#1a1d28;--bg-elevated:#242736;
 --text-primary:#e8e8ed;--text-secondary:#9a9ab0;--text-muted:#6b6b80;
 --accent:#667eea;--success:#34d399;--warning:#fbbf24;--danger:#f87171;
 --border:#2a2d3a;
 --space-xs:4px;--space-sm:8px;--space-md:16px;--space-lg:24px;--space-xl:32px;
 --font:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
 --font-mono:'SF Mono','Fira Code',monospace;
 --text-sm:13px;--text-base:15px;--text-lg:18px;--text-xl:24px;--text-2xl:32px;
 --radius:8px;--radius-lg:12px;--max-width:860px;
}
body{font-family:var(--font);background:var(--bg-primary);color:var(--text-primary);
 font-size:var(--text-base);line-height:1.6;min-height:100vh;-webkit-font-smoothing:antialiased}
.container{max-width:var(--max-width);margin:0 auto;padding:var(--space-md)}
.header{background:var(--bg-card);padding:var(--space-md);border-bottom:1px solid var(--border)}
.header-content{display:flex;justify-content:space-between;align-items:center;
 max-width:var(--max-width);margin:0 auto;gap:var(--space-md);flex-wrap:wrap}
.logo{font-size:var(--text-xl);font-weight:800;
 background:linear-gradient(135deg,var(--accent),#a78bfa);
 -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.card{background:var(--bg-card);border:1px solid var(--border);border-radius:var(--radius-lg);
 padding:var(--space-lg);margin-bottom:var(--space-md)}
.card-title{font-size:var(--text-lg);font-weight:700;margin-bottom:var(--space-sm)}
.verdetto{font-size:var(--text-xl);line-height:1.35;font-weight:700;margin-bottom:var(--space-md)}
.verdetto .big{font-size:var(--text-2xl);color:var(--accent)}
.barra-riga{display:flex;align-items:center;gap:var(--space-md);margin-bottom:var(--space-sm)}
.barra-et{width:150px;font-size:var(--text-sm);color:var(--text-secondary);flex-shrink:0}
.barra-tr{flex:1;background:var(--bg-elevated);border-radius:4px;height:26px;overflow:hidden}
.barra-fill{height:100%;border-radius:4px;background:var(--accent)}
.barra-fill.alto{background:var(--warning)}
.barra-fill.basso{background:var(--success)}
.barra-n{width:96px;text-align:right;font-family:var(--font-mono);font-size:var(--text-sm);
 font-weight:700;flex-shrink:0}
.nota-tri{font-size:12px;color:var(--text-muted);margin:-4px 0 var(--space-md) 166px}
.table-wrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
table{width:100%;border-collapse:collapse;font-size:var(--text-sm)}
th{text-align:left;padding:var(--space-sm) var(--space-md);font-weight:600;
 color:var(--text-muted);border-bottom:2px solid var(--border);white-space:nowrap}
td{padding:var(--space-sm) var(--space-md);border-bottom:1px solid var(--border)}
tr:hover td{background:var(--bg-elevated)}
.onesta{border-left:3px solid var(--warning);background:rgba(251,191,36,.08);
 padding:var(--space-md) var(--space-lg);border-radius:var(--radius);margin-bottom:var(--space-md)}
.onesta .card-title{color:var(--warning)}
.metodo{font-size:12px;color:var(--text-muted);line-height:1.7;
 border-top:1px solid var(--border);padding-top:var(--space-md);margin-top:var(--space-lg)}
.text-muted{color:var(--text-muted)}
.font-mono{font-family:var(--font-mono)}
@media(max-width:768px){
 :root{--text-base:14px;--text-xl:20px;--text-2xl:26px;--space-lg:16px}
 .barra-et{width:104px}.barra-n{width:74px}.nota-tri{margin-left:120px}
}
@media print{
 body{background:#fff;color:#111}.card,.onesta{border:1px solid #ddd;break-inside:avoid}
 .logo{-webkit-text-fill-color:#333}
}
</style>
</head>
<body>
<div class="header"><div class="header-content">
  <div class="logo">OB1</div>
  <div class="text-muted" style="font-size:12px">Referto anagrafico · {{ generated_at }}</div>
</div></div>

<div class="container">

{% if not r.abbastanza %}
  <div class="card">
    <div class="card-title">Non abbastanza ragazzi per dire qualcosa</div>
    <p class="text-muted">{{ r.messaggio }}</p>
  </div>
{% else %}

  <div class="card">
    <p class="text-muted" style="font-size:var(--text-sm);margin-bottom:var(--space-sm)">
      {% if r.societa %}{{ r.societa }} · {% endif %}{{ r.n }} ragazzi analizzati
    </p>
    {% if r.sbilanciato %}
      <p class="verdetto">
        Nel vostro gruppo <span class="big">{{ r.quota_q1 }}%</span> dei ragazzi è nato
        nei primi tre mesi dell'anno.<br>
        Negli ultimi tre mesi, solo <span class="big">{{ r.quota_q4 }}%</span>.
      </p>
      <p>
        Sono {{ r.q1 }} contro {{ r.q4 }}{% if r.rapporto %}: <strong>{{ r.rapporto }} volte
        tanti</strong>{% endif %}. La probabilità che sia un caso è
        <strong>{{ r.probabilita }}</strong>.
      </p>
    {% else %}
      <p class="verdetto">Il vostro gruppo è <span class="big">in equilibrio</span>.</p>
      <p>I mesi di nascita sono distribuiti in modo compatibile con il caso. È una cosa
      rara: nella maggior parte dei settori giovanili non succede.</p>
    {% endif %}
  </div>

  <div class="card">
    <div class="card-title">Come sono distribuiti</div>
    {% for b in r.barre %}
      <div class="barra-riga">
        <span class="barra-et">{{ b.etichetta }}</span>
        <div class="barra-tr">
          <div class="barra-fill {% if b.trimestre == 1 %}alto{% elif b.trimestre == 4 %}basso{% endif %}"
               style="width:{{ (b.quota / 50 * 100) if b.quota < 50 else 100 }}%"></div>
        </div>
        <span class="barra-n">{{ b.n }} · {{ b.quota }}%</span>
      </div>
      {% if b.nota %}<div class="nota-tri">{{ b.nota }}</div>{% endif %}
    {% endfor %}
    <p class="text-muted" style="font-size:12px;margin-top:var(--space-md)">
      Se il mese di nascita non contasse, ogni riga sarebbe intorno al 25%.
    </p>
  </div>

  {% if r.sbilanciato %}
  <div class="card">
    <div class="card-title">Cosa vuol dire</div>
    <p>Non è un vostro difetto: succede in quasi tutti i settori giovanili del mondo,
    da decenni.</p>
    <p class="mt-md" style="margin-top:var(--space-md)">A 13 anni un ragazzo nato a gennaio
    ha quasi un anno di sviluppo in più di uno nato a dicembre. È più alto, più forte, più
    veloce. Viene scelto più spesso, gioca di più, si allena di più — e quel vantaggio si
    accumula. Ma è un vantaggio <strong>di calendario, non di talento</strong>, e verso i
    20 anni si esaurisce.</p>
    <p style="margin-top:var(--space-md)">Il punto è che a quel momento la selezione è già
    avvenuta.</p>
  </div>

  {% if r.tardivi %}
  <div class="card">
    <div class="card-title">I vostri {{ r.tardivi|length }} nati negli ultimi mesi dell'anno</div>
    <p class="text-muted" style="font-size:var(--text-sm);margin-bottom:var(--space-md)">
      Sono arrivati dove sono passando da un filtro
      {% if r.rarita_q4 and r.rarita_q4 > 1 %}circa {{ r.rarita_q4 }} volte{% endif %}
      più stretto degli altri. A parità di livello raggiunto, hanno dovuto essere più bravi
      per restare.
    </p>
    <div class="table-wrap"><table>
      <thead><tr><th>Nome</th><th>Nato il</th><th>Età</th></tr></thead>
      <tbody>
      {% for g in r.tardivi %}
        <tr><td>{{ g.nome }}</td><td class="font-mono">{{ g.nato_il }}</td>
            <td class="font-mono">{{ g.eta }}</td></tr>
      {% endfor %}
      </tbody>
    </table></div>
  </div>
  {% endif %}

  <div class="onesta">
    <div class="card-title">Cosa questo referto NON dice</div>
    <p><strong>Non dice che quei ragazzi siano più forti.</strong> Dice che hanno superato
    una selezione più dura a parità di risultato raggiunto.</p>
    <p style="margin-top:var(--space-sm)">Che questo li renda mediamente migliori da adulti
    è un'ipotesi ragionevole e discussa, <strong>non un fatto dimostrato</strong>. Chi vi
    dicesse il contrario vi starebbe vendendo qualcosa.</p>
    <p style="margin-top:var(--space-sm)">Serve a una cosa sola: dirvi <em>su chi vale la
    pena rimettere l'occhio</em>, sapendo che il calendario ha remato contro.</p>
  </div>
  {% endif %}

{% endif %}

  <div class="metodo">
    <strong>Metodo.</strong> Si contano i ragazzi per trimestre di nascita e si confronta
    con la distribuzione attesa se il mese non contasse (25% per trimestre). Il test è un
    chi-quadro a 3 gradi di libertà; il valore misurato qui è
    <span class="font-mono">{{ r.chi2 if r.chi2 is defined else '–' }}</span>, tradotto nel
    testo come probabilità che lo sbilanciamento sia dovuto al caso.
    {% if problemi %}<br><br><strong>Righe scartate:</strong> {{ problemi|length }} —
    {{ problemi[:3]|join('; ') }}{% if problemi|length > 3 %}; …{% endif %}.
    Nessuna data è stata indovinata.{% endif %}
    <br><br>Generato da OB1 {{ version }} il {{ generated_at }}. Nessun dato è stato
    inviato a terzi: il calcolo è avvenuto sul file che avete fornito.
  </div>
</div>
</body>
</html>
"""


def genera_html(r: dict, problemi: list[str], version: str) -> str:
    env = Environment(autoescape=True)  # i nomi vengono da un CSV altrui: si scappa sempre
    return env.from_string(TEMPLATE).render(
        r=r, problemi=problemi, version=version,
        generated_at=datetime.now().strftime("%d/%m/%Y %H:%M"))


def main():
    ap = argparse.ArgumentParser(
        description="Referto anagrafico: la diagnosi sul vivaio di un club, in una pagina.")
    ap.add_argument("--csv", required=True, help="file con nomi e date di nascita")
    ap.add_argument("--societa", default="", help="nome del club, per l'intestazione")
    ap.add_argument("--out", default=None, help="file HTML di destinazione")
    args = ap.parse_args()

    percorso = Path(args.csv)
    if not percorso.exists():
        raise SystemExit(f"File non trovato: {percorso}")

    giocatori, problemi = leggi_csv(percorso)
    cfg = load_config()
    r = costruisci_referto(giocatori, args.societa, cfg)

    try:
        version = (Path(__file__).resolve().parent / "VERSION").read_text().strip()
    except Exception:
        version = ""

    out = Path(args.out) if args.out else Path(
        f"referto_{(args.societa or 'vivaio').lower().replace(' ', '_')}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(genera_html(r, problemi, version), encoding="utf-8")

    print(f"Referto scritto in {out}")
    print(f"  {r['n']} ragazzi letti" + (f", {len(problemi)} righe scartate" if problemi else ""))
    if r["abbastanza"]:
        if r["sbilanciato"]:
            # nessun nato nell'ultimo trimestre -> il rapporto non esiste, non
            # e' "zero": si tace invece di stampare un None travestito da numero
            volte = f" ({r['rapporto']}x)" if r["rapporto"] else ""
            print(f"  nati gen-mar {r['quota_q1']}% vs ott-dic {r['quota_q4']}%{volte}"
                  f" — caso improbabile: {r['probabilita']}")
            print(f"  {len(r['tardivi'])} ragazzi nati negli ultimi mesi dell'anno")
        else:
            print("  distribuzione in equilibrio: niente da segnalare")
    else:
        print(f"  {r['messaggio']}")


if __name__ == "__main__":
    main()
