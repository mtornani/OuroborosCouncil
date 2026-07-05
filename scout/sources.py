"""
Collettori di segnali oggettivi. Tutte fonti gratuite, zero API key.

  1. Google News RSS multi-lingua -> menzioni, tier fonti, spread linguistico,
     keyword di rumor mercato nei titoli.
  2. Wikipedia API -> esistenza pagina per lingua, numero edizioni (langlinks).
     La CREAZIONE della pagina e' un evento di attraversamento della curva.
  3. Wikimedia Pageviews API -> serie giornaliera visite pagina.
     Uno spike di pageviews = il pubblico ha iniziato a cercarlo.

REGOLA: ZERO dati inventati. Fonte muta -> campo "available": False.
"""
import re
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

HEADERS = {
    "User-Agent": "OuroborosRadar/1.0 (+https://github.com/mtornani/OuroborosCouncil)"
}
TIMEOUT = 20

# Lingue monitorate: lo SPREAD LINGUISTICO e' un proxy di diffusione
# internazionale. Un 2008 di Serie C di cui parla la stampa spagnola
# non e' piu' un segreto.
NEWS_LOCALES = {
    "it": {"hl": "it", "gl": "IT", "ceid": "IT:it"},
    "en": {"hl": "en", "gl": "US", "ceid": "US:en"},
    "es": {"hl": "es", "gl": "ES", "ceid": "ES:es"},
    "pt": {"hl": "pt-BR", "gl": "BR", "ceid": "BR:pt-419"},
    "fr": {"hl": "fr", "gl": "FR", "ceid": "FR:fr"},
    "de": {"hl": "de", "gl": "DE", "ceid": "DE:de"},
}

# Keyword di rumor/mercato per lingua: la comparsa di queste parole nei
# titoli indica che il MERCATO (non solo la stampa) si sta muovendo.
RUMOR_KEYWORDS = [
    # it
    "mercato", "interesse", "osservatori", "trattativa", "offerta",
    "rinnovo", "clausola", "valutazione", "richiesta", "gioiello",
    "talento", "big", "seguito da", "nel mirino", "piace a",
    # en
    "transfer", "interest", "scouts", "scouted", "linked", "bid",
    "target", "wonderkid", "monitored", "race", "battle", "swoop",
    "release clause", "contract talks",
    # es
    "fichaje", "interesa", "ojeadores", "seguimiento", "perla",
    "joya", "cantera", "clausula",
    # pt
    "contratacao", "interessado", "observadores", "joia", "promessa",
    "sondagem", "negociacao",
    # fr
    "transfert", "interet", "recruteurs", "pepite", "courtise",
    "dans le viseur",
    # de
    "wechsel", "interesse", "scouts", "juwel", "talent", "umworben",
]

WIKI_LANGS = ["it", "en", "es", "pt", "fr", "de"]

_ITEM_RE = re.compile(
    r"<item>(.*?)</item>", re.DOTALL
)
_FIELD_RES = {
    "title": re.compile(r"<title>(.*?)</title>", re.DOTALL),
    "link": re.compile(r"<link>(.*?)</link>", re.DOTALL),
    "pubDate": re.compile(r"<pubDate>(.*?)</pubDate>", re.DOTALL),
    "source": re.compile(r'<source url="(.*?)">(.*?)</source>', re.DOTALL),
}


def _clean(text: str) -> str:
    return text.replace("<![CDATA[", "").replace("]]>", "").strip()


def _parse_rss_items(xml: str, max_items: int = 50) -> list[dict]:
    """Parsa gli <item> di un feed RSS Google News, incluso il publisher."""
    items = []
    for m in _ITEM_RE.finditer(xml):
        block = m.group(1)
        item = {}
        for field in ("title", "link", "pubDate"):
            fm = _FIELD_RES[field].search(block)
            item[field] = _clean(fm.group(1)) if fm else ""
        sm = _FIELD_RES["source"].search(block)
        if sm:
            item["source_url"] = _clean(sm.group(1))
            item["source_name"] = _clean(sm.group(2))
        else:
            item["source_url"] = ""
            item["source_name"] = ""
        items.append(item)
        if len(items) >= max_items:
            break
    return items


def _days_ago(pub_date: str) -> float | None:
    """Giorni trascorsi dalla pubblicazione. None se data non parsabile."""
    try:
        dt = parsedate_to_datetime(pub_date)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    except Exception:
        return None


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower())


def fetch_news_mentions(player_name: str, aliases: list[str] | None = None) -> dict:
    """
    Cerca il giocatore su Google News in tutte le lingue monitorate.

    Ritorna per lingua: menzioni ultimi 7/30 giorni, tier massimo delle
    fonti, domini distinti, hit di keyword rumor, item recenti.
    """
    queries = [player_name] + (aliases or [])
    out = {"available": True, "by_lang": {}, "errors": []}

    for lang, loc in NEWS_LOCALES.items():
        seen_links = set()
        all_items = []
        for q in queries:
            url = (
                "https://news.google.com/rss/search?q="
                + urllib.parse.quote(f'"{q}"')
                + f"&hl={loc['hl']}&gl={loc['gl']}&ceid={loc['ceid']}"
            )
            try:
                resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
                if resp.status_code != 200:
                    out["errors"].append(f"{lang}: HTTP {resp.status_code}")
                    continue
                for item in _parse_rss_items(resp.text):
                    if item["link"] in seen_links:
                        continue
                    seen_links.add(item["link"])
                    all_items.append(item)
            except Exception as e:
                out["errors"].append(f"{lang}: {e}")
            time.sleep(0.4)  # gentile con Google

        mentions_7d = 0
        mentions_30d = 0
        max_tier = -1  # -1 = nessuna menzione
        domains = set()
        rumor_hits = []
        recent = []

        from . import tiers  # import locale per evitare cicli

        for item in all_items:
            age = _days_ago(item["pubDate"])
            if age is None or age > 30:
                continue
            mentions_30d += 1
            if age <= 7:
                mentions_7d += 1
            src = item["source_url"] or item["link"]
            tier = tiers.classify(src)
            max_tier = max(max_tier, tier)
            dom = tiers.domain_of(src)
            if dom:
                domains.add(dom)
            title_norm = _normalize(item["title"])
            hit_kw = [
                kw for kw in RUMOR_KEYWORDS if _normalize(kw) in title_norm
            ]
            if hit_kw:
                rumor_hits.append(
                    {"title": item["title"], "keywords": hit_kw[:5],
                     "url": item["link"], "tier": tier}
                )
            if len(recent) < 5:
                recent.append(
                    {"title": item["title"], "date": item["pubDate"],
                     "source": item["source_name"], "tier": tier,
                     "url": item["link"]}
                )

        out["by_lang"][lang] = {
            "mentions_7d": mentions_7d,
            "mentions_30d": mentions_30d,
            "max_tier": max_tier,
            "domains": sorted(domains),
            "rumor_hits": rumor_hits[:10],
            "recent": recent,
        }

    return out


def fetch_wikipedia_presence(player_name: str, aliases: list[str] | None = None) -> dict:
    """
    Controlla l'esistenza della pagina Wikipedia nelle lingue monitorate
    e conta le edizioni totali (langlinks).

    NON avere una pagina = fase innovator/early adopter.
    La pagina che APPARE tra due snapshot = evento di crossing.
    """
    out = {"available": True, "pages": {}, "total_langs": 0, "errors": []}
    candidates = [player_name] + (aliases or [])

    for lang in WIKI_LANGS:
        found = None
        for title in candidates:
            try:
                resp = requests.get(
                    f"https://{lang}.wikipedia.org/w/api.php",
                    params={
                        "action": "query", "titles": title,
                        "prop": "langlinks", "lllimit": "500",
                        "format": "json", "redirects": 1,
                    },
                    timeout=TIMEOUT, headers=HEADERS,
                )
                if resp.status_code != 200:
                    out["errors"].append(f"{lang}: HTTP {resp.status_code}")
                    continue
                pages = resp.json().get("query", {}).get("pages", {})
                for page_id, page in pages.items():
                    if page_id != "-1" and "missing" not in page:
                        found = {
                            "title": page.get("title", title),
                            "langlinks": len(page.get("langlinks", [])),
                        }
                        break
            except Exception as e:
                out["errors"].append(f"{lang}: {e}")
            if found:
                break
            time.sleep(0.2)
        out["pages"][lang] = found

    # total_langs: edizioni totali = langlinks della prima pagina trovata + 1
    for lang in WIKI_LANGS:
        if out["pages"][lang]:
            out["total_langs"] = out["pages"][lang]["langlinks"] + 1
            break

    return out


def fetch_pageviews(player_name: str, wiki_presence: dict, days: int = 30) -> dict:
    """
    Serie giornaliera di pageviews per la prima pagina Wikipedia esistente.
    Uno spike (media 7gg >> media 21gg precedenti) = il pubblico lo cerca.
    """
    out = {"available": False, "lang": None, "daily": [], "error": None}

    target_lang, target_title = None, None
    for lang in WIKI_LANGS:
        page = (wiki_presence or {}).get("pages", {}).get(lang)
        if page:
            target_lang, target_title = lang, page["title"]
            break
    if not target_lang:
        out["error"] = "no_wikipedia_page"
        return out

    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(days=days)
    article = urllib.parse.quote(target_title.replace(" ", "_"), safe="")
    url = (
        "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
        f"{target_lang}.wikipedia/all-access/all-agents/{article}/daily/"
        f"{start.strftime('%Y%m%d')}00/{end.strftime('%Y%m%d')}00"
    )
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers=HEADERS)
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            out["available"] = True
            out["lang"] = target_lang
            out["daily"] = [
                {"date": i["timestamp"][:8], "views": i["views"]} for i in items
            ]
        elif resp.status_code == 404:
            # pagina esiste ma senza dati pageviews (troppo nuova): e' un dato!
            out["available"] = True
            out["lang"] = target_lang
            out["daily"] = []
            out["error"] = "no_pageview_data_yet"
        else:
            out["error"] = f"HTTP {resp.status_code}"
    except Exception as e:
        out["error"] = str(e)
    return out


def collect_player(player: dict) -> dict:
    """Raccoglie tutti i segnali per un giocatore. Ritorna uno snapshot."""
    name = player["name"]
    aliases = player.get("aliases", [])
    news = fetch_news_mentions(name, aliases)
    wiki = fetch_wikipedia_presence(name, aliases)
    views = fetch_pageviews(name, wiki)
    return {
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "player": name,
        "news": news,
        "wikipedia": wiki,
        "pageviews": views,
    }
