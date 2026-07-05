"""
Storico snapshot per giocatore — il cuore del calcolo di VELOCITA'
e ACCELERAZIONE dell'attenzione.

Un singolo snapshot dice DOVE sei sulla curva.
La serie storica dice QUANTO VELOCEMENTE la stai attraversando.
E' la differenza tra una foto e un radar.

Formato: un file JSONL per giocatore in data/radar/history/<slug>.jsonl,
una riga per snapshot giornaliero. Le GitHub Actions committano lo storico
nel repo: il repo stesso e' il database (zero infrastruttura).
"""
import json
import re
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HISTORY_DIR = REPO_ROOT / "data" / "radar" / "history"
LATEST_FILE = REPO_ROOT / "data" / "radar" / "latest.json"


def slugify(name: str) -> str:
    norm = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", norm.lower()).strip("-")


def history_path(player_name: str) -> Path:
    return HISTORY_DIR / f"{slugify(player_name)}.jsonl"


def _compact(snapshot: dict) -> dict:
    """Riduce lo snapshot ai campi necessari per le serie storiche.

    Nello storico non servono titoli/URL completi (stanno in latest.json):
    servono i numeri per calcolare le derivate.
    """
    news = snapshot.get("news", {})
    by_lang = {}
    for lang, d in news.get("by_lang", {}).items():
        by_lang[lang] = {
            "m7": d["mentions_7d"],
            "m30": d["mentions_30d"],
            "tier": d["max_tier"],
            "domains": len(d["domains"]),
            "rumors": len(d["rumor_hits"]),
        }
    wiki = snapshot.get("wikipedia", {})
    views = snapshot.get("pageviews", {})
    daily = views.get("daily", [])
    return {
        "date": snapshot["date"],
        "news": by_lang,
        "news_available": news.get("available", False),
        "wiki_langs": wiki.get("total_langs", 0),
        "wiki_it": bool(wiki.get("pages", {}).get("it")),
        "wiki_en": bool(wiki.get("pages", {}).get("en")),
        "pv_avg7": _avg(daily[-7:]),
        "pv_avg30": _avg(daily),
        "pv_available": views.get("available", False),
    }


def _avg(daily: list[dict]) -> float | None:
    vals = [d["views"] for d in daily if isinstance(d.get("views"), int)]
    return round(sum(vals) / len(vals), 1) if vals else None


def append_snapshot(snapshot: dict) -> dict:
    """Aggiunge lo snapshot compatto allo storico (sostituisce se stessa data)."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    path = history_path(snapshot["player"])
    compact = _compact(snapshot)

    rows = load_history(snapshot["player"])
    rows = [r for r in rows if r.get("date") != compact["date"]]
    rows.append(compact)
    rows.sort(key=lambda r: r["date"])

    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return compact


def load_history(player_name: str) -> list[dict]:
    path = history_path(player_name)
    if not path.exists():
        return []
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    rows.sort(key=lambda r: r.get("date", ""))
    return rows


def save_latest(results: list[dict]):
    """Salva l'output completo dell'ultimo run (snapshot + score)."""
    LATEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LATEST_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def load_latest() -> list[dict]:
    if not LATEST_FILE.exists():
        return []
    with open(LATEST_FILE, "r", encoding="utf-8") as f:
        return json.load(f)
