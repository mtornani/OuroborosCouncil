"""
MissMinute Web Monitor — Scraping leggero di fonti reali.
Gira su GitHub Actions ogni 12h oppure localmente.
Output: web_intel.json

REGOLA: ZERO dati inventati. Se una fonte non risponde,
il sistema dice "fonte non disponibile", NON inventa un sostituto.
"""
import json
import re
import urllib.parse
from datetime import datetime
from pathlib import Path

import requests

# Path intelligente: locale se esiste, altrimenti current dir (CI)
_LOCAL_DIR = Path(r"D:\AI\.miss_minute")
OUTPUT_FILE = _LOCAL_DIR / "web_intel.json" if _LOCAL_DIR.exists() else Path("web_intel.json")

# ============================================================
# RSS FEEDS — Google News, zero API key, sempre gratis
# ============================================================

RSS_FEEDS = {
    # K-Sport e competitor diretti
    "ksport_news": {
        "url": "https://news.google.com/rss/search?q=%22K-Sport%22+football+wearable&hl=en",
        "category": "priority_contact",
        "trigger_level": "HIGH",
    },
    "kfans_news": {
        "url": "https://news.google.com/rss/search?q=%22K-Fans%22+sensor+jersey&hl=en",
        "category": "priority_contact",
        "trigger_level": "HIGH",
    },
    "twelve_football": {
        "url": "https://news.google.com/rss/search?q=%22Twelve+Football%22+scouting&hl=en",
        "category": "competitor",
        "trigger_level": "MEDIUM",
    },
    "skillcorner": {
        "url": "https://news.google.com/rss/search?q=SkillCorner+football+tracking&hl=en",
        "category": "competitor",
        "trigger_level": "MEDIUM",
    },
    # Settore AI + Sport
    "ai_football_scouting": {
        "url": "https://news.google.com/rss/search?q=AI+football+scouting+2026&hl=en",
        "category": "sector",
        "trigger_level": "LOW",
    },
    "sport_tech_funding": {
        "url": "https://news.google.com/rss/search?q=sport+technology+startup+funding&hl=en",
        "category": "opportunity",
        "trigger_level": "MEDIUM",
    },
    # Serie C / mercato italiano
    "serie_c_mercato": {
        "url": "https://news.google.com/rss/search?q=Serie+C+calciomercato+svincolati&hl=it",
        "category": "ob1_feed",
        "trigger_level": "LOW",
    },
    "lega_pro": {
        "url": "https://news.google.com/rss/search?q=Lega+Pro+trasferimenti&hl=it",
        "category": "ob1_feed",
        "trigger_level": "LOW",
    },
    # San Marino / FSGC
    "fsgc_news": {
        "url": "https://news.google.com/rss/search?q=FSGC+San+Marino+calcio&hl=it",
        "category": "local",
        "trigger_level": "MEDIUM",
    },
    # Multi-club ownership & innovation
    "football_innovation": {
        "url": "https://news.google.com/rss/search?q=football+club+innovation+technology+AI&hl=en",
        "category": "sector",
        "trigger_level": "LOW",
    },
}

# Contatti da monitorare (via Google News)
CONTACTS = {
    "marcolini_ksport": {
        "name": "Mirko Marcolini",
        "role": "CEO K-Sport",
        "search_query": "Mirko Marcolini K-Sport",
        "relevance": "priority_1",
    },
    "vagnini_ksport": {
        "name": "Lorenzo Vagnini",
        "role": "Business Dev K-Sport",
        "search_query": "Lorenzo Vagnini K-Sport",
        "relevance": "priority_1",
    },
    "nardoni_fsgc": {
        "name": "Andrea Nardoni",
        "role": "FSGC contact",
        "search_query": "Andrea Nardoni FSGC San Marino",
        "relevance": "priority_4",
    },
}

# Giocatori OB1 tracked
TRACKED_PLAYERS = [
    "Ryan Evaristo",
    "Andre Maia",
    "Noah Saviolo",
    "Bruno Baldini",
    "Kauan Toledo",
    "Pietro Saio",
    "Louis Buffon",
]

# Repo GitHub da controllare
GITHUB_REPOS = [
    "mtornani/ob1-scout",
    "mtornani/ob1-serie-c",
]

# Sito da controllare (uptime)
SITE_CHECK = "https://www.matchanalysispro.online/theseus/demo/"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; MissMinute/2.0)"}


# ============================================================
# CORE: Google News RSS parser
# ============================================================


def search_google_news(query: str, max_results: int = 3) -> list[dict]:
    """Cerca su Google News via RSS feed."""
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}&hl=en&gl=US&ceid=US:en"
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        if resp.status_code != 200:
            return []

        items = []
        for match in re.finditer(
            r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<pubDate>(.*?)</pubDate>.*?</item>",
            resp.text,
            re.DOTALL,
        ):
            title = match.group(1).replace("<![CDATA[", "").replace("]]>", "").strip()
            link = match.group(2).strip()
            pub_date = match.group(3).strip()
            items.append({"title": title, "url": link, "date": pub_date})
            if len(items) >= max_results:
                break
        return items
    except Exception as e:
        return [{"error": str(e)}]


def fetch_rss_feed(url: str, max_results: int = 3) -> list[dict]:
    """Fetch diretto di un RSS feed URL."""
    try:
        resp = requests.get(url, timeout=15, headers=HEADERS)
        if resp.status_code != 200:
            return []

        items = []
        for match in re.finditer(
            r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?<pubDate>(.*?)</pubDate>.*?</item>",
            resp.text,
            re.DOTALL,
        ):
            title = match.group(1).replace("<![CDATA[", "").replace("]]>", "").strip()
            link = match.group(2).strip()
            pub_date = match.group(3).strip()
            items.append({"title": title, "url": link, "date": pub_date})
            if len(items) >= max_results:
                break
        return items
    except Exception as e:
        return [{"error": str(e)}]


# ============================================================
# MONITORS
# ============================================================


def monitor_rss_feeds() -> tuple[dict, list]:
    """Monitor all RSS feeds. Returns (feed_results, signals)."""
    feed_results = {}
    signals = []

    for feed_id, config in RSS_FEEDS.items():
        items = fetch_rss_feed(config["url"], max_results=3)
        feed_results[feed_id] = {
            "category": config["category"],
            "items": items,
        }

        for item in items:
            if "error" in item:
                continue
            signals.append(
                {
                    "type": f"RSS_{config['category'].upper()}",
                    "priority": config["trigger_level"],
                    "message": item["title"],
                    "url": item.get("url", ""),
                    "feed": feed_id,
                    "date": item.get("date", ""),
                }
            )

    return feed_results, signals


def monitor_contacts() -> tuple[dict, list]:
    """Monitor contatti via Google News."""
    contact_results = {}
    signals = []

    for contact_id, config in CONTACTS.items():
        news = search_google_news(config["search_query"], max_results=3)
        contact_results[contact_id] = {
            "name": config["name"],
            "role": config["role"],
            "relevance": config["relevance"],
            "recent_news": news,
        }

        if news and config["relevance"] == "priority_1":
            for item in news:
                if "error" not in item:
                    signals.append(
                        {
                            "type": "CONTACT_NEWS",
                            "priority": "HIGH",
                            "message": f"{config['name']} ({config['role']}): {item['title']}",
                            "url": item.get("url", ""),
                            "action_hint": "News pubblica su contatto priority_1. Potrebbe essere un aggancio.",
                        }
                    )

    return contact_results, signals


def check_transfermarkt_changes() -> list:
    """
    Controlla se i giocatori nel nostro tracking hanno news.
    NON scrapa Transfermarkt direttamente (ToS issues).
    Usa Google News con nome giocatore + "transfer" come proxy.
    """
    signals = []
    for player in TRACKED_PLAYERS:
        news = search_google_news(f'"{player}" transfer football', max_results=2)
        if news and not any("error" in n for n in news):
            signals.append(
                {
                    "type": "PLAYER_NEWS",
                    "priority": "HIGH",
                    "message": f"News su {player} (OB1 tracked): {news[0].get('title', '')}",
                    "url": news[0].get("url", ""),
                    "action_hint": f"{player} e' nel nostro tracking. Se confermato, aggiorna Evidence Log.",
                }
            )

    return signals


def check_job_opportunities() -> list:
    """
    Cerca posizioni aperte in club/aziende per scouting/innovation.
    Queste sono opportunita' dirette per Mirko.
    """
    queries = [
        '"football scouting" "AI" job',
        '"data analyst" "football club" hiring',
        '"innovation manager" "football" vacancy',
        '"scouting technology" "partnership"',
    ]

    signals = []
    for query in queries:
        news = search_google_news(query, max_results=2)
        for item in news:
            if "error" not in item:
                signals.append(
                    {
                        "type": "OPPORTUNITY",
                        "priority": "MEDIUM",
                        "message": f"Posizione/Opportunita': {item.get('title', '')}",
                        "url": item.get("url", ""),
                        "action_hint": "Valuta se contattare con portfolio Theseus Protocol",
                    }
                )

    return signals


def get_real_weather() -> dict:
    """Meteo reale da wttr.in — utile per pianificare allenamenti U14."""
    try:
        resp = requests.get(
            "https://wttr.in/San+Marino?format=j1",
            timeout=10,
            headers=HEADERS,
        )
        if resp.status_code == 200:
            data = resp.json()
            current = data["current_condition"][0]
            return {
                "location": "San Marino",
                "temp_c": current["temp_C"],
                "condition": current["weatherDesc"][0]["value"],
                "humidity": current["humidity"],
                "wind_kmph": current["windspeedKmph"],
                "source": "wttr.in",
                "real": True,
            }
    except Exception:
        pass
    return {"source": "wttr.in", "real": False, "error": "unavailable"}


def check_github_actions(repo: str) -> dict:
    """Controlla ultimo run di GitHub Actions."""
    url = f"https://api.github.com/repos/{repo}/actions/runs?per_page=1"
    try:
        resp = requests.get(
            url,
            timeout=10,
            headers={"Accept": "application/vnd.github.v3+json"},
        )
        if resp.status_code != 200:
            return {"repo": repo, "status": "unknown", "error": resp.status_code}

        runs = resp.json().get("workflow_runs", [])
        if not runs:
            return {"repo": repo, "status": "no_runs"}

        latest = runs[0]
        return {
            "repo": repo,
            "status": latest["conclusion"] or latest["status"],
            "name": latest["name"],
            "updated": latest["updated_at"],
            "url": latest["html_url"],
        }
    except Exception as e:
        return {"repo": repo, "status": "error", "error": str(e)}


def check_site_up(url: str) -> dict:
    """Controlla se il sito risponde."""
    try:
        resp = requests.get(url, timeout=15)
        return {
            "url": url,
            "status": "UP" if resp.status_code == 200 else f"DOWN ({resp.status_code})",
            "response_time_ms": int(resp.elapsed.total_seconds() * 1000),
        }
    except Exception as e:
        return {"url": url, "status": "DOWN", "error": str(e)}


# ============================================================
# DEDUPLICATION
# ============================================================


def deduplicate_signals(signals: list) -> list:
    """Rimuovi segnali duplicati basati su URL o titolo simile."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for s in signals:
        url = s.get("url", "")
        title = s.get("message", "")[:50].lower()

        if url and url in seen_urls:
            continue
        if title and title in seen_titles:
            continue

        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        unique.append(s)

    return unique


# ============================================================
# MAIN
# ============================================================


def run_monitor():
    """Esegui tutto il monitoring e salva risultati."""
    results = {
        "timestamp": datetime.now().isoformat(),
        "contacts": {},
        "feeds": {},
        "github": [],
        "site": None,
        "weather": None,
        "signals": [],
    }

    # 1. RSS Feeds
    feed_results, feed_signals = monitor_rss_feeds()
    results["feeds"] = feed_results
    results["signals"].extend(feed_signals)

    # 2. Contact monitoring
    contact_results, contact_signals = monitor_contacts()
    results["contacts"] = contact_results
    results["signals"].extend(contact_signals)

    # 3. GitHub Actions
    for repo in GITHUB_REPOS:
        status = check_github_actions(repo)
        results["github"].append(status)
        if status.get("status") not in ("success", "no_runs", "unknown"):
            results["signals"].append(
                {
                    "type": "SYSTEM_ALERT",
                    "priority": "CRITICAL",
                    "message": f"GitHub Actions FAILED: {repo} -- {status.get('name', 'unknown')}",
                    "url": status.get("url", ""),
                }
            )

    # 4. Site uptime
    site = check_site_up(SITE_CHECK)
    results["site"] = site
    if site["status"] != "UP":
        results["signals"].append(
            {
                "type": "SYSTEM_ALERT",
                "priority": "CRITICAL",
                "message": f"SITO DOWN: {SITE_CHECK} -- {site['status']}",
            }
        )

    # 5. Player tracking (OB1)
    player_signals = check_transfermarkt_changes()
    results["signals"].extend(player_signals)

    # 6. Job opportunities
    job_signals = check_job_opportunities()
    results["signals"].extend(job_signals)

    # 7. Weather (per coaching U14)
    results["weather"] = get_real_weather()

    # Deduplicate
    results["signals"] = deduplicate_signals(results["signals"])

    # Salva
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    signal_count = len(results["signals"])
    high_count = sum(1 for s in results["signals"] if s.get("priority") in ("CRITICAL", "HIGH"))
    print(f"Monitor completato: {signal_count} segnali ({high_count} HIGH/CRITICAL)")
    return results


if __name__ == "__main__":
    run_monitor()
