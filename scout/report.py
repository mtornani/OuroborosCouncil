"""
Report generator: RADAR_REPORT.md (repo/terminale) + docs/radar.html
(dashboard self-contained per meeting — zero dipendenze, si apre col browser).

La dashboard posiziona ogni giocatore sulla curva di Rogers in base
all'ADI: la posizione E' il messaggio. I colori seguono lo stato della
finestra (status palette, mai da soli: sempre badge testuale accanto).
"""
import html as html_mod
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MD_FILE = REPO_ROOT / "RADAR_REPORT.md"
HTML_FILE = REPO_ROOT / "docs" / "radar.html"

WINDOW_BADGE = {
    "OPEN": ("🟢", "FINESTRA APERTA"),
    "CLOSING": ("🟠", "FINESTRA IN CHIUSURA — AGIRE"),
    "CLOSED": ("⚪", "FINESTRA CHIUSA"),
}

PHASE_IT = {
    "INNOVATOR": "Innovator",
    "EARLY_ADOPTER": "Early Adopter",
    "CROSSING": "Crossing the Chasm",
    "MAINSTREAM": "Mainstream",
}


def write_markdown(cards: list[dict], discoveries: list[dict]) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    valid = [c for c in cards if "error" not in c]
    # ordina: CLOSING prima, poi per breakout decrescente
    order = {"CLOSING": 0, "OPEN": 1, "CLOSED": 2}
    valid.sort(key=lambda c: (order.get(c["window"], 9), -c["breakout"]))

    lines = [
        "# 🐍 OUROBOROS RADAR — Report",
        "",
        f"*Aggiornato: {now} — {len(valid)} giocatori in watchlist*",
        "",
        "> Il radar misura la posizione di ogni giocatore sulla curva di",
        "> diffusione dell'attenzione e la velocita' con cui la attraversa.",
        "> **ADI** = dove sei sulla curva. **Breakout** = quanto in fretta",
        "> ti stai muovendo. La decisione resta all'occhio umano.",
        "",
        "| Giocatore | Finestra | Fase | ADI | Breakout | Mainstream tra |",
        "|-----------|----------|------|----:|---------:|----------------|",
    ]
    for c in valid:
        emoji, label = WINDOW_BADGE[c["window"]]
        weeks = c.get("weeks_to_mainstream")
        eta = f"~{weeks} sett." if weeks else "—"
        lines.append(
            f"| **{c['player']}** | {emoji} {c['window']} | "
            f"{PHASE_IT[c['phase']]} | {c['adi']} | {c['breakout']} | {eta} |"
        )

    lines.append("")
    for c in valid:
        emoji, label = WINDOW_BADGE[c["window"]]
        lines += [
            f"## {emoji} {c['player']}",
            "",
            f"**{label}** — {c['window_desc']}",
            "",
            f"- Fase: **{PHASE_IT[c['phase']]}** ({c['phase_desc']})",
            f"- ADI: **{c['adi']}/100** — Breakout: **{c['breakout']}/100**"
            f" — snapshot storici: {c['snapshots']}",
        ]
        if c.get("weeks_to_mainstream"):
            w = c["weeks_to_mainstream"]
            sett = "settimana" if w == 1 else "settimane"
            lines.append(f"- ⏳ A questo ritmo, mainstream tra ~**{w} {sett}**")
        lines.append("- Posizione (ADI):")
        lines += [f"  - {r}" for r in c["adi_reasons"]]
        lines.append("- Movimento (Breakout):")
        lines += [f"  - {r}" for r in c["breakout_reasons"]]
        lines.append("")

    if discoveries:
        lines += [
            "## 🔍 Discovery — nomi sotto radar non in watchlist",
            "",
            "Nomi ricorrenti nelle fonti di nicchia (tier 0-1) nelle ultime",
            "2 settimane. Rete a strascico rumorosa: verifica umana necessaria.",
            "",
        ]
        for d in discoveries[:10]:
            lines.append(
                f"- **{d['name']}** — {d['hits']} titoli, tier max "
                f"{d['max_tier']}, lingue: {', '.join(d['langs'])}"
            )
            for t in d["titles"][:2]:
                lines.append(f"  - _{t['title']}_ ({t['source']})")
        lines.append("")

    lines += [
        "---",
        "*Fonti: Google News RSS (6 lingue), Wikipedia API, Wikimedia",
        "Pageviews. Zero dati inventati: fonte muta = campo non disponibile.*",
    ]

    MD_FILE.write_text("\n".join(lines), encoding="utf-8")
    return MD_FILE


# ============================================================
# DASHBOARD HTML
# ============================================================

def _esc(s) -> str:
    return html_mod.escape(str(s))


def write_html(cards: list[dict], discoveries: list[dict]) -> Path:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    valid = [c for c in cards if "error" not in c]
    order = {"CLOSING": 0, "OPEN": 1, "CLOSED": 2}
    valid.sort(key=lambda c: (order.get(c["window"], 9), -c["breakout"]))

    closing = sum(1 for c in valid if c["window"] == "CLOSING")
    data_json = json.dumps(
        [
            {
                "name": c["player"], "club": c.get("club", ""),
                "adi": c["adi"], "breakout": c["breakout"],
                "phase": PHASE_IT[c["phase"]], "window": c["window"],
                "weeks": c.get("weeks_to_mainstream"),
                "adi_reasons": c["adi_reasons"],
                "breakout_reasons": c["breakout_reasons"],
            }
            for c in valid
        ],
        ensure_ascii=False,
    )

    cards_html = []
    for c in valid:
        emoji, label = WINDOW_BADGE[c["window"]]
        weeks = c.get("weeks_to_mainstream")
        sett = "settimana" if weeks == 1 else "settimane"
        eta = (
            f'<span class="eta">⏳ mainstream tra ~{weeks} {sett}</span>'
            if weeks else ""
        )
        reasons = "".join(
            f"<li>{_esc(r)}</li>"
            for r in (c["breakout_reasons"] + c["adi_reasons"])[:5]
        )
        cards_html.append(f"""
    <article class="card w-{c['window'].lower()}">
      <header>
        <h3>{_esc(c['player'])}</h3>
        <span class="badge b-{c['window'].lower()}">{emoji} {_esc(c['window'])}</span>
      </header>
      <p class="meta">{_esc(c.get('club') or '')} · {_esc(PHASE_IT[c['phase']])} {eta}</p>
      <div class="bars">
        <div class="barrow"><span class="barlabel">ADI</span>
          <div class="track"><div class="fill f-adi" style="width:{c['adi']}%"></div></div>
          <span class="barval">{c['adi']}</span></div>
        <div class="barrow"><span class="barlabel">Breakout</span>
          <div class="track"><div class="fill f-brk" style="width:{c['breakout']}%"></div></div>
          <span class="barval">{c['breakout']}</span></div>
      </div>
      <ul class="reasons">{reasons}</ul>
    </article>""")

    disc_html = ""
    if discoveries:
        rows = "".join(
            f"<tr><td>{_esc(d['name'])}</td><td>{d['hits']}</td>"
            f"<td>{d['max_tier']}</td><td>{_esc(', '.join(d['langs']))}</td>"
            f"<td class='ttl'>{_esc(d['titles'][0]['title'] if d['titles'] else '')}</td></tr>"
            for d in discoveries[:10]
        )
        disc_html = f"""
  <section>
    <h2>🔍 Discovery — nomi sotto radar, non in watchlist</h2>
    <p class="note">Nomi ricorrenti nelle fonti di nicchia (tier 0-1), ultime 2 settimane. Verifica umana necessaria.</p>
    <div class="tablewrap"><table>
      <thead><tr><th>Nome</th><th>Titoli</th><th>Tier max</th><th>Lingue</th><th>Esempio</th></tr></thead>
      <tbody>{rows}</tbody>
    </table></div>
  </section>"""

    table_rows = "".join(
        f"<tr><td>{_esc(c['player'])}</td><td>{_esc(c['window'])}</td>"
        f"<td>{_esc(PHASE_IT[c['phase']])}</td><td>{c['adi']}</td>"
        f"<td>{c['breakout']}</td>"
        f"<td>{('~' + str(c['weeks_to_mainstream']) + ' sett.') if c.get('weeks_to_mainstream') else '—'}</td></tr>"
        for c in valid
    )

    page = f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ouroboros Radar</title>
<style>
:root {{
  --surface: #fcfcfb; --page: #f9f9f7;
  --ink: #0b0b0b; --ink2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --ring: rgba(11,11,11,.10);
  --open: #0ca30c; --closing: #ec835a; --closed: #898781;
  --adi: #2a78d6; --brk: #eb6834;
}}
@media (prefers-color-scheme: dark) {{
  :root {{
    --surface: #1a1a19; --page: #0d0d0d;
    --ink: #ffffff; --ink2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,.10);
    --open: #0ca30c; --closing: #ec835a; --closed: #898781;
    --adi: #3987e5; --brk: #d95926;
  }}
}}
* {{ box-sizing: border-box; margin: 0; }}
body {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--page); color: var(--ink); padding: 24px; line-height: 1.45; }}
main {{ max-width: 1040px; margin: 0 auto; }}
h1 {{ font-size: 1.5rem; }} h2 {{ font-size: 1.1rem; margin: 28px 0 8px; }}
.sub {{ color: var(--ink2); margin: 4px 0 20px; }}
.tiles {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr));
  gap: 12px; margin-bottom: 24px; }}
.tile {{ background: var(--surface); border: 1px solid var(--ring);
  border-radius: 10px; padding: 14px 16px; }}
.tile .v {{ font-size: 1.9rem; font-weight: 650; }}
.tile .l {{ color: var(--ink2); font-size: .82rem; }}
.chartbox {{ background: var(--surface); border: 1px solid var(--ring);
  border-radius: 10px; padding: 16px; overflow-x: auto; }}
.cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px,1fr));
  gap: 12px; margin-top: 12px; }}
.card {{ background: var(--surface); border: 1px solid var(--ring);
  border-radius: 10px; padding: 14px 16px; }}
.card header {{ display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }}
.card h3 {{ font-size: 1rem; }}
.badge {{ font-size: .7rem; font-weight: 650; padding: 2px 8px;
  border-radius: 999px; white-space: nowrap; }}
.b-open {{ color: var(--open); border: 1px solid var(--open); }}
.b-closing {{ color: var(--closing); border: 1px solid var(--closing); }}
.b-closed {{ color: var(--closed); border: 1px solid var(--closed); }}
.meta {{ color: var(--ink2); font-size: .8rem; margin: 4px 0 10px; }}
.eta {{ color: var(--closing); font-weight: 600; }}
.barrow {{ display: grid; grid-template-columns: 64px 1fr 34px;
  align-items: center; gap: 8px; margin: 4px 0; }}
.barlabel {{ font-size: .72rem; color: var(--muted); }}
.barval {{ font-size: .78rem; color: var(--ink2); text-align: right;
  font-variant-numeric: tabular-nums; }}
.track {{ height: 6px; background: var(--grid); border-radius: 4px; }}
.fill {{ height: 6px; border-radius: 4px; }}
.f-adi {{ background: var(--adi); }} .f-brk {{ background: var(--brk); }}
.reasons {{ margin: 10px 0 0 16px; padding: 0; color: var(--ink2);
  font-size: .78rem; }}
.reasons li {{ margin: 2px 0; }}
.legend {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: .78rem;
  color: var(--ink2); margin-top: 8px; }}
.legend .dot {{ display: inline-block; width: 9px; height: 9px;
  border-radius: 50%; margin-right: 5px; }}
.note {{ color: var(--ink2); font-size: .82rem; margin-bottom: 8px; }}
.tablewrap {{ overflow-x: auto; background: var(--surface);
  border: 1px solid var(--ring); border-radius: 10px; }}
table {{ border-collapse: collapse; width: 100%; font-size: .82rem; }}
th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--grid); }}
th {{ color: var(--muted); font-weight: 600; }}
td {{ font-variant-numeric: tabular-nums; }} td.ttl {{ color: var(--ink2); }}
tr:last-child td {{ border-bottom: none; }}
#tip {{ position: fixed; pointer-events: none; background: var(--surface);
  border: 1px solid var(--ring); border-radius: 8px; padding: 8px 10px;
  font-size: .75rem; max-width: 260px; display: none; z-index: 10;
  box-shadow: 0 4px 14px rgba(0,0,0,.25); }}
footer {{ color: var(--muted); font-size: .75rem; margin-top: 28px; }}
</style>
</head>
<body>
<main>
  <h1>🐍 Ouroboros Radar</h1>
  <p class="sub">Curva di diffusione dell'attenzione — aggiornato {now}</p>

  <div class="tiles">
    <div class="tile"><div class="v">{len(valid)}</div><div class="l">giocatori in watchlist</div></div>
    <div class="tile"><div class="v" style="color:var(--closing)">{closing}</div><div class="l">finestre in chiusura</div></div>
    <div class="tile"><div class="v">{len(discoveries)}</div><div class="l">candidati discovery</div></div>
  </div>

  <h2>La curva — dove si trova ogni giocatore</h2>
  <div class="chartbox">
    <svg id="curve" viewBox="0 0 1000 320" width="100%" role="img"
         aria-label="Posizione dei giocatori sulla curva di diffusione dell'attenzione, asse ADI da 0 a 100"></svg>
    <div class="legend">
      <span><span class="dot" style="background:var(--open)"></span>OPEN — finestra aperta</span>
      <span><span class="dot" style="background:var(--closing)"></span>CLOSING — agire ora</span>
      <span><span class="dot" style="background:var(--closed)"></span>CLOSED — mainstream</span>
    </div>
  </div>

  <h2>Schede giocatore</h2>
  <div class="cards">{''.join(cards_html)}
  </div>

  <h2>Vista tabellare</h2>
  <div class="tablewrap"><table>
    <thead><tr><th>Giocatore</th><th>Finestra</th><th>Fase</th><th>ADI</th><th>Breakout</th><th>Mainstream tra</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table></div>
{disc_html}
  <footer>Fonti: Google News RSS (6 lingue) · Wikipedia API · Wikimedia Pageviews.
  Zero dati inventati: fonte muta = campo non disponibile. ADI = posizione sulla
  curva; Breakout = velocita' di attraversamento. La decisione resta all'occhio umano.</footer>
</main>
<div id="tip"></div>
<script>
const PLAYERS = {data_json};
const svg = document.getElementById('curve');
const NS = 'http://www.w3.org/2000/svg';
const W = 1000, H = 320, PAD = {{l: 30, r: 30, t: 26, b: 46}};
const px = adi => PAD.l + (W - PAD.l - PAD.r) * adi / 100;
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
function el(tag, attrs, parent) {{
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  (parent || svg).appendChild(e); return e;
}}
// campana di Rogers (gaussiana) come sfondo recessivo
const mu = 50, sigma = 20, baseY = H - PAD.b;
let d = `M ${{px(0)}} ${{baseY}}`;
for (let x = 0; x <= 100; x += 2) {{
  const y = baseY - 200 * Math.exp(-((x - mu) ** 2) / (2 * sigma ** 2));
  d += ` L ${{px(x)}} ${{y.toFixed(1)}}`;
}}
d += ` L ${{px(100)}} ${{baseY}} Z`;
el('path', {{d, fill: css('--grid'), 'fill-opacity': .55, stroke: css('--axis'), 'stroke-width': 1}});
// bande di fase (hairline) + etichette
const bands = [[0,15,'Innovator'],[15,40,'Early Adopter'],[40,65,'Crossing'],[65,100,'Mainstream']];
bands.forEach(([lo, hi, label]) => {{
  if (lo > 0) el('line', {{x1: px(lo), y1: PAD.t, x2: px(lo), y2: baseY,
    stroke: css('--grid'), 'stroke-width': 1, 'stroke-dasharray': '3 4'}});
  const t = el('text', {{x: (px(lo) + px(hi)) / 2, y: baseY + 18,
    'text-anchor': 'middle', 'font-size': 12, fill: css('--muted')}});
  t.textContent = label;
}});
// asse
el('line', {{x1: px(0), y1: baseY, x2: px(100), y2: baseY, stroke: css('--axis'), 'stroke-width': 1}});
[0, 25, 50, 75, 100].forEach(v => {{
  const t = el('text', {{x: px(v), y: baseY + 34, 'text-anchor': 'middle',
    'font-size': 10, fill: css('--muted')}});
  t.textContent = 'ADI ' + v;
}});
// dot per giocatore, con anti-collisione verticale semplice
const colors = {{OPEN: css('--open'), CLOSING: css('--closing'), CLOSED: css('--closed')}};
const placed = [];
const tip = document.getElementById('tip');
PLAYERS.forEach(p => {{
  const x = px(p.adi);
  let y = baseY - 200 * Math.exp(-((p.adi - mu) ** 2) / (2 * sigma * sigma)) - 14;
  while (placed.some(q => Math.abs(q.x - x) < 46 && Math.abs(q.y - y) < 18)) y -= 20;
  placed.push({{x, y}});
  const g = el('g', {{cursor: 'pointer'}});
  el('circle', {{cx: x, cy: y, r: 13, fill: 'transparent'}}, g); // hit target
  el('circle', {{cx: x, cy: y, r: 6, fill: colors[p.window],
    stroke: css('--surface'), 'stroke-width': 2}}, g);
  // clamp: l'etichetta non deve uscire dal viewBox ai bordi
  const lx = Math.max(50, Math.min(W - 50, x));
  const t = el('text', {{x: lx, y: y - 11, 'text-anchor': 'middle',
    'font-size': 11, 'font-weight': 600, fill: css('--ink')}}, g);
  t.textContent = p.name;
  g.addEventListener('mousemove', ev => {{
    tip.style.display = 'block';
    tip.style.left = Math.min(ev.clientX + 14, window.innerWidth - 280) + 'px';
    tip.style.top = (ev.clientY + 14) + 'px';
    tip.innerHTML = `<strong>${{p.name}}</strong> ${{p.club ? '· ' + p.club : ''}}<br>` +
      `${{p.phase}} — finestra ${{p.window}}<br>` +
      `ADI ${{p.adi}} · Breakout ${{p.breakout}}` +
      (p.weeks ? `<br>⏳ mainstream tra ~${{p.weeks}} settimane` : '');
  }});
  g.addEventListener('mouseleave', () => tip.style.display = 'none');
}});
</script>
</body>
</html>"""
    HTML_FILE.parent.mkdir(parents=True, exist_ok=True)
    HTML_FILE.write_text(page, encoding="utf-8")
    return HTML_FILE
