"""
DISCOVERY — Caccia ai nomi non ancora in watchlist.

La watchlist risolve "quando si chiude la finestra per i giocatori che
CONOSCO?". Discovery risolve il problema a monte: "quali nomi stanno
comparendo nelle fonti di nicchia che NON conosco ancora?".

Metodo:
  1. Interroga Google News con query "da early adopter": esordi giovanili,
     wonderkid, primavera, nazionali giovanili — in piu' lingue.
  2. Estrae candidati nome-cognome dai titoli (euristica su maiuscole).
  3. Tiene solo i nomi che ricorrono in >= min_hits titoli DIVERSI
     e che compaiono SOLO su fonti tier 0-1 (se ne parla gia' il
     mainstream, e' tardi: non e' piu' un early adopter).
  4. Output: candidati ordinati per frequenza, con i titoli a supporto.

E' volutamente una rete a strascico rumorosa: l'ultima parola resta
all'occhio umano, che decide chi promuovere in players.yaml.
"""
import re
import time
import urllib.parse

import requests

from . import tiers
from .sources import HEADERS, TIMEOUT, _parse_rss_items, _days_ago

DISCOVERY_QUERIES = {
    "it": [
        "esordio primavera talento classe",
        "esordio serie C giovane classe 2008",
        "gioiello settore giovanile debutto",
        "under 17 azzurro talento",
    ],
    "en": [
        "wonderkid debut youngest",
        "academy prospect first team debut",
        "under-17 starlet scouts",
    ],
    "es": [
        "joya cantera debut juvenil",
        "perla sub-17 debut",
    ],
    "pt": [
        "joia base estreia profissional",
        "promessa sub-17 estreia",
    ],
}

LOCALES = {
    "it": "&hl=it&gl=IT&ceid=IT:it",
    "en": "&hl=en&gl=US&ceid=US:en",
    "es": "&hl=es&gl=ES&ceid=ES:es",
    "pt": "&hl=pt-BR&gl=BR&ceid=BR:pt-419",
}

# Euristica nome persona: 2-3 parole capitalizzate consecutive.
# Accetta lettere accentate; esclude sigle/tutto-maiuscolo.
_NAME_RE = re.compile(
    r"\b([A-ZÀ-Þ][a-zà-þ]+(?:\s+(?:[A-ZÀ-Þ][a-zà-þ]+|d[aei]l?|De|Di|Van|Dos|Da)){1,2})\b"
)

# Parole che sembrano nomi ma non lo sono (club, competizioni, frasi comuni)
STOPWORDS = {
    "Serie", "Lega", "Primavera", "Under", "Champions", "Europa",
    "Coppa", "Juventus", "Inter", "Milan", "Napoli", "Roma", "Lazio",
    "Atalanta", "Fiorentina", "Torino", "Bologna", "Genoa", "Sampdoria",
    "Real", "Madrid", "Barcelona", "Manchester", "United", "City",
    "Liverpool", "Chelsea", "Arsenal", "Bayern", "Borussia", "Paris",
    "Saint", "Germain", "Premier", "League", "Liga", "Bundesliga",
    "World", "Cup", "Euro", "Mondiale", "Europeo", "Nazionale", "Italia",
    "San", "Marino", "Copa", "Libertadores", "Sub", "News", "Sport",
    "Football", "Calcio", "Futbol", "Futebol", "Video", "Gol", "Goal",
    "Highlights", "Live", "Diretta", "Ecco", "Chi", "Come", "Dove",
    "The", "New", "Top", "Best", "Young", "First", "Team", "Club",
    "Boca", "River", "Plate", "Santos", "Flamengo", "Palmeiras",
    "Corinthians", "Gremio", "Ajax", "Porto", "Benfica", "Sporting",
}


def _looks_like_name(candidate: str) -> bool:
    words = candidate.split()
    if len(words) < 2:
        return False
    if any(w in STOPWORDS for w in words):
        return False
    if any(len(w) < 2 for w in words):
        return False
    return True


def run_discovery(
    known_names: set[str], min_hits: int = 2, max_age_days: int = 14
) -> list[dict]:
    """Scansiona le query discovery e ritorna candidati nuovi."""
    candidates: dict[str, dict] = {}
    known_lower = {n.lower() for n in known_names}

    for lang, queries in DISCOVERY_QUERIES.items():
        for q in queries:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote(q)
                + LOCALES[lang]
            )
            try:
                resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
                if resp.status_code != 200:
                    continue
                items = _parse_rss_items(resp.text, max_items=25)
            except Exception:
                continue
            time.sleep(0.4)

            for item in items:
                age = _days_ago(item["pubDate"])
                if age is None or age > max_age_days:
                    continue
                src = item["source_url"] or item["link"]
                tier = tiers.classify(src)
                for m in _NAME_RE.finditer(item["title"]):
                    name = m.group(1).strip()
                    if not _looks_like_name(name):
                        continue
                    if name.lower() in known_lower:
                        continue
                    entry = candidates.setdefault(
                        name,
                        {"name": name, "hits": 0, "max_tier": 0,
                         "langs": set(), "titles": []},
                    )
                    # conta titoli distinti, non ripetizioni
                    if item["title"] not in [t["title"] for t in entry["titles"]]:
                        entry["hits"] += 1
                        entry["max_tier"] = max(entry["max_tier"], tier)
                        entry["langs"].add(lang)
                        if len(entry["titles"]) < 4:
                            entry["titles"].append(
                                {"title": item["title"], "tier": tier,
                                 "source": item["source_name"],
                                 "url": item["link"]}
                            )

    results = []
    for entry in candidates.values():
        # gia' sul mainstream = non e' piu' materiale early adopter
        if entry["hits"] >= min_hits and entry["max_tier"] <= 1:
            entry["langs"] = sorted(entry["langs"])
            results.append(entry)

    results.sort(key=lambda e: (-e["hits"], e["name"]))
    return results[:20]
