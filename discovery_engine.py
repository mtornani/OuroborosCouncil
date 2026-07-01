"""OB1 Radar - motore di discovery talenti.

Trova candidati PRIMA che diventino notizia (non fact-checka notizie gia'
uscite). Due meccanismi di enumerazione verificati live (non ipotizzati):
- Serie C/D italiana: Wikidata SPARQL (dati strutturati, rose correnti).
- Giovanili sudamericane CONMEBOL: parsing del testo Wikipedia delle rose
  (Wikidata non ha dati strutturati per queste pagine, verificato).
Il segnale differenziante e' il Buzz Score: velocita' di menzione in fonti
di nicchia PRIMA che la stampa mainstream se ne accorga.

ZERO dati inventati: se una fonte non risponde o un dato manca, si segnala
esplicitamente ("fonte non disponibile" / flag "dati parziali"), mai un
numero stimato spacciato per reale. Stessa regola gia' in monitor/web_monitor.py.
"""
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

from monitor.web_monitor import search_google_news, deduplicate_signals
from openrouter_client import call_openrouter, get_available_models
from nvidia_client import call_nvidia, get_available_models as get_available_nvidia_models
from gemini_client import call_gemini, get_available_models as get_available_gemini_models

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # ok in locale senza DB configurato - vedi _load_json/_save_json

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "radar_config.yaml"
FEED_FILE = BASE_DIR / "radar_feed.json"
BUZZ_HISTORY_FILE = BASE_DIR / "buzz_history.json"

# Se impostata (in produzione: Neon/Supabase, mai committata), lo storico
# vive su Postgres invece che su disco locale - un host gratuito con
# filesystem effimero (Render/HF Spaces free tier) azzera i file a ogni
# riavvio, e l'intero senso dello storico append-only e' non perderlo mai.
DATABASE_URL = os.getenv("DATABASE_URL", "")

USER_AGENT = "OB1Radar/0.1 (contact: mirko-tornani-ai-lab.com)"
WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
WIKIPEDIA_API = "https://en.wikipedia.org/w/api.php"

# Solo giocatori fino a questa eta': e' un radar di talenti giovani, non
# un archivio storico dei club. BUG TROVATO E CORRETTO: prima era un anno
# di nascita ASSOLUTO (1999), che sembrava "giovani" solo perche' scritto
# quando il 2026 era gia' l'anno corrente - il filtro si allarga da solo
# ogni anno che passa (nel 2030 "dal 1999" includerebbe trentunenni). Ora
# e' relativo a oggi, non si allarga mai da solo. Verificato dal vivo che
# il vecchio bound (2026-1999=27 anni) faceva rientrare praticamente
# un'intera rosa Serie C (eta' media reale 25.9), non solo i giovani.
MAX_AGE_YEARS = 24


def _min_birth_year() -> int:
    return datetime.now().year - MAX_AGE_YEARS

# Classe Wikidata "reserve team" (verificato live su Juventus Next Gen) -
# costante strutturale, non un peso da tarare, resta nel codice.
RESERVE_TEAM_QID = "Q2412834"

DEFAULT_FALLBACK_MODEL = "google/gemini-2.0-flash-lite-preview-02-05:free"


# ============================================================
# CONFIG / STATO
# ============================================================

def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _db_ensure_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS radar_state (
                key TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
    conn.commit()


def _load_json(path: Path) -> dict:
    """path.stem diventa la chiave su Postgres quando DATABASE_URL e'
    impostata (radar_feed.json -> 'radar_feed'), altrimenti file locale -
    stesso comportamento di prima, cosi' lo sviluppo senza DB configurato
    non si rompe."""
    if DATABASE_URL and psycopg2:
        try:
            with psycopg2.connect(DATABASE_URL) as conn:
                _db_ensure_table(conn)
                with conn.cursor() as cur:
                    cur.execute("SELECT data FROM radar_state WHERE key = %s", (path.stem,))
                    row = cur.fetchone()
                    return row[0] if row else {}
        except Exception:
            return {}  # fonte non disponibile: mai un fallback silenzioso con dati vecchi/inventati

    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path: Path, data: dict):
    if DATABASE_URL and psycopg2:
        try:
            with psycopg2.connect(DATABASE_URL) as conn:
                _db_ensure_table(conn)
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO radar_state (key, data, updated_at)
                        VALUES (%s, %s, now())
                        ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                        """,
                        (path.stem, psycopg2.extras.Json(data)),
                    )
                conn.commit()
            return
        except Exception:
            pass  # DB irraggiungibile in questo run: non blocca il refresh, scrive comunque su file locale

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


_BARE_QID_RE = re.compile(r"^Q\d+$")


def _clean_label(value: str) -> str:
    """SERVICE wikibase:label ripiega sul QID nudo (es. 'Q20053389') quando
    l'entita' non ha un'etichetta in it/en (verificato live: club minori
    senza pagina Wikipedia). Un QID mostrato come nome club confonderebbe
    piu' di quanto aiuti - meglio trattarlo come dato mancante."""
    if not value or _BARE_QID_RE.match(value):
        return ""
    return value


DAY_PRECISION = 11  # Wikidata: 11=giorno, 10=mese, 9=anno, ...


def _precise_dob(row: dict) -> str | None:
    """None se la data di nascita non e' precisa al giorno (verificato live:
    un caso reale con precisione 'solo anno' aveva quasi certamente l'anno
    sbagliato) - mai un'eta' calcolata su un dato che Wikidata stesso non
    dichiara affidabile a quel livello."""
    precision = (row.get("dobPrecision") or {}).get("value")
    if precision != str(DAY_PRECISION):
        return None
    return (row.get("dob") or {}).get("value", "")[:10] or None


_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")


def _clean_name(value: str) -> str:
    """Wikidata a volte allega un disambiguatore tra parentesi al nome
    quando esistono omonimi (es. 'Alejandro Cichero (footballer, born
    2003)') - va bene come dato interno, non come nome mostrato a Mirko.
    Stesso ripiego sul QID nudo gia' visto per il club (verificato live:
    'Q138840467' mostrato come se fosse un nome) - stessa correzione."""
    cleaned = _TRAILING_PAREN_RE.sub("", value).strip()
    return "" if _BARE_QID_RE.match(cleaned) else cleaned


# Wikidata (P413) restituisce etichette granulari in italiano ("mediano",
# "ala sinistra", "trequartista"...), il parsing Wikipedia (CONMEBOL) da'
# sigle inglesi (GK/DF/MF/FW). Un solo normalizzatore per i 4 macro-ruoli
# utili a un filtro in UI - i dettagli granulari si perdono, va bene cosi'
# per un filtro, non per un report tattico.
_ROLE_BUCKETS = [
    ("Portiere", ["portiere", "gk"]),
    ("Difensore", ["difensore", "terzino", "libero", "df"]),
    ("Centrocampista", ["centrocampista", "mediano", "mezzala", "trequartista", "regista", "mf"]),
    ("Attaccante", ["attaccante", "ala", "punta", "seconda punta", "fw"]),
]


def _normalize_role(raw: str) -> str | None:
    if not raw:
        return None
    raw_lower = raw.strip().lower()
    for bucket, keywords in _ROLE_BUCKETS:
        if any(raw_lower == kw or raw_lower.startswith(kw) for kw in keywords):
            return bucket
    return None  # etichetta non riconosciuta - mai un ruolo inventato


# ============================================================
# CANDIDATE POOL - Serie C/D via Wikidata SPARQL (verificato live)
# ============================================================

def _sparql_current_squad(league_qid: str) -> list[dict]:
    """Rosa corrente di una lega Wikidata (P118) via appartenenza club (P54)
    senza data di fine (FILTER NOT EXISTS end time) - approccio verificato
    con query reale prima di scrivere questo codice."""
    # RESERVE_TEAM_QID (Q2412834, "reserve team") individua le squadre
    # Next Gen/U23 via classe Wikidata, non per nome - verificato live che
    # "Juventus Next Gen" e' l'unica in Serie C ora, ma il meccanismo regge
    # se ne arrivano altre (es. un domani Atalanta U23). In questi club
    # l'eta' bassa e' un requisito di regolamento (obbligo U21), non un
    # segnale raro - da solo il Signal Score la trattava come rara (finche'
    # il primo dossier reale del Giudice non l'ha segnalato).
    # p:P569/psv:P569/wikibase:timeValue+timePrecision invece del semplice
    # wdt:P569: serve a scartare le date con precisione "solo anno" (9),
    # non "giorno" (11) - verificato live su un caso reale (Esad Deniz,
    # segnato "2010" con precisione anno su Wikidata, quasi certamente
    # sbagliato: un Next Gen titolare a 16 anni e' implausibile, e lo
    # stesso Cronista dello swarm - da conoscenza propria, non dai nostri
    # dati - lo dava nato nel 2005). Una data non precisa al giorno viene
    # trattata come mancante, mai presa per buona cosi' com'e'.
    query = f"""
    SELECT ?player ?playerLabel ?club ?clubLabel ?posLabel ?dob ?dobPrecision ?isReserve WHERE {{
      ?club wdt:P118 wd:{league_qid} .
      BIND(EXISTS {{ ?club wdt:P31/wdt:P279* wd:{RESERVE_TEAM_QID} }} AS ?isReserve)
      ?player p:P54 ?membership .
      ?membership ps:P54 ?club .
      FILTER NOT EXISTS {{ ?membership pq:P582 ?endTime . }}
      ?player p:P569 ?dobStatement .
      ?dobStatement psv:P569 ?dobValue .
      ?dobValue wikibase:timeValue ?dob .
      ?dobValue wikibase:timePrecision ?dobPrecision .
      FILTER(YEAR(?dob) >= {_min_birth_year()})
      OPTIONAL {{ ?player wdt:P413 ?pos . }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
    }}
    LIMIT 500
    """
    url = WIKIDATA_SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception:
        return []

    out = []
    for row in data.get("results", {}).get("bindings", []):
        qid = row["player"]["value"].rsplit("/", 1)[-1]
        out.append(
            {
                "candidate_id": qid,
                "name": _clean_name(row.get("playerLabel", {}).get("value", "")) or f"Senza nome ({qid})",
                "club": _clean_label(row.get("clubLabel", {}).get("value", "")),
                "role": _normalize_role(row.get("posLabel", {}).get("value", "")),
                "dob": _precise_dob(row),
                "source": "wikidata",
                "is_reserve": row.get("isReserve", {}).get("value") == "true",
            }
        )
    return out


def fetch_serie_players(cfg: dict) -> list[dict]:
    """Candidati Serie C/D. Se Wikidata non risponde: lista vuota per
    quella lega, mai un fallback silenzioso con dati inventati."""
    candidates = []
    for league_key, league_cfg in cfg["candidate_sources"]["wikidata_leagues"].items():
        rows = _sparql_current_squad(league_cfg["qid"])
        for row in rows:
            row["tier"] = f"{league_cfg['tier']}_riserve" if row.pop("is_reserve", False) else league_cfg["tier"]
            candidates.append(row)
    return candidates


def _sparql_nationality_pool(country_qid: str, gender_qid: str) -> list[dict]:
    """Ricerca PER CITTADINANZA, indipendente da dove il giocatore gioca ora
    - query strutturalmente diversa da _sparql_current_squad (li' si parte
    dal club, qui dalla persona). Il club e' OPTIONAL: verificato live che
    la maggior parte dei candidati non ha un club corrente risolvibile su
    Wikidata (23/30 nel test Portogallo) - restano candidati validi lo
    stesso, con dati parziali. Il filtro di genere (P21) e' obbligatorio:
    verificato live che senza non torna quasi altro che calciatrici donne
    per questo taglio d'eta'."""
    query = f"""
    SELECT ?player ?playerLabel ?club ?clubLabel ?posLabel ?dob ?dobPrecision WHERE {{
      ?player wdt:P27 wd:{country_qid} .
      ?player wdt:P106 wd:Q937857 .
      ?player wdt:P21 wd:{gender_qid} .
      ?player p:P569 ?dobStatement .
      ?dobStatement psv:P569 ?dobValue .
      ?dobValue wikibase:timeValue ?dob .
      ?dobValue wikibase:timePrecision ?dobPrecision .
      FILTER(YEAR(?dob) >= {_min_birth_year()})
      OPTIONAL {{ ?player wdt:P413 ?pos . }}
      OPTIONAL {{
        ?player p:P54 ?membership .
        ?membership ps:P54 ?club .
        FILTER NOT EXISTS {{ ?membership pq:P582 ?endTime . }}
        # esclude le nazionali dal binding "club" - verificato live: senza
        # questo filtro un giocatore convocato risultava due volte, una con
        # il club vero e una con "nazionale di calcio del Portogallo" come
        # se fosse un club (P54 vale anche per le convocazioni in nazionale)
        FILTER NOT EXISTS {{ ?club wdt:P31/wdt:P279* wd:Q6979593 . }}
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "it,en". }}
    }}
    LIMIT 500
    """
    url = WIKIDATA_SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
    except Exception:
        return []

    out = []
    for row in data.get("results", {}).get("bindings", []):
        qid = row["player"]["value"].rsplit("/", 1)[-1]
        out.append(
            {
                "candidate_id": qid,
                "name": _clean_name(row.get("playerLabel", {}).get("value", "")) or f"Senza nome ({qid})",
                "club": _clean_label(row.get("clubLabel", {}).get("value", "")),
                "role": _normalize_role(row.get("posLabel", {}).get("value", "")),
                "dob": _precise_dob(row),
                "source": "wikidata",
            }
        )
    return out


def fetch_nationality_players(cfg: dict) -> list[dict]:
    """Candidati per cittadinanza (una voce di config per paese, zero codice
    da toccare per aggiungerne uno nuovo). Le query girano in parallelo -
    con piu' di una manciata di paesi in config farle in sequenza allungava
    troppo un singolo refresh (verificato: ogni query pesa qualche secondo,
    in sequenza 15 paesi diventano un minuto solo per questa fase)."""
    pools = list((cfg["candidate_sources"].get("wikidata_nationalities") or {}).items())
    candidates = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(_sparql_nationality_pool, pool_cfg["country_qid"], pool_cfg["gender_qid"]): (pool_key, pool_cfg)
            for pool_key, pool_cfg in pools
        }
        for future in as_completed(futures):
            pool_key, pool_cfg = futures[future]
            try:
                rows = future.result()
            except Exception:
                rows = []  # fonte non disponibile per questo paese in questo run
            for row in rows:
                row["tier"] = "nationality_pool"
                row["nationality_label"] = pool_cfg.get("label", pool_key)
                candidates.append(row)
    return candidates


# ============================================================
# CANDIDATE POOL - giovanili CONMEBOL via parsing Wikipedia (verificato live)
# ============================================================

_NAT_FS_PLAYER_RE = re.compile(
    r"\{\{nat fs player[^|]*\|"
    r"(?:[^}]*?\|)?pos=(?P<pos>\w+)\|"
    r"name=(?:'''?)?\[\[(?P<name>[^\]|]+)(?:\|[^\]]+)?\]\](?:'''?)?\|"
    r"age=\{\{birth date and age2\|\d+\|\d+\|\d+\|(?P<by>\d+)\|(?P<bm>\d+)\|(?P<bd>\d+)"
    r"[^}]*\}\}\|"
    r"club=(?:\[\[(?P<club>[^\]|]+)(?:\|[^\]]+)?\]\]|(?P<club_plain>[^|}]+))",
    re.IGNORECASE,
)


def _fetch_wikipedia_wikitext(title: str) -> str | None:
    url = WIKIPEDIA_API + "?" + urllib.parse.urlencode(
        {"action": "parse", "page": title, "prop": "wikitext", "format": "json"}
    )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return data["parse"]["wikitext"]["*"]
    except Exception:
        return None


def fetch_conmebol_squads(cfg: dict) -> list[dict]:
    """Candidati dai tornei giovanili CONMEBOL. Wikidata non ha dati
    strutturati per queste rose (verificato: nessun claim utile sull'item
    della lista) - qui si parsa il testo Wikipedia (template regex-estraibile,
    verificato sulla pagina 2025 South American U-20 Championship squads)."""
    candidates = []
    for page in cfg["candidate_sources"]["wikipedia_youth_squads"]:
        wikitext = _fetch_wikipedia_wikitext(page["title"])
        if not wikitext:
            continue  # fonte non disponibile per questa pagina, si salta
        for m in _NAT_FS_PLAYER_RE.finditer(wikitext):
            try:
                birth_year = int(m.group("by"))
            except (TypeError, ValueError):
                continue
            if birth_year < _min_birth_year():
                continue
            raw_name = m.group("name")
            club = m.group("club") or m.group("club_plain") or ""
            candidates.append(
                {
                    # ID dal nome grezzo (con eventuale disambiguatore Wikipedia
                    # tra parentesi): e' li' apposta perche' esistono piu'
                    # persone con lo stesso nome base - pulirlo prima
                    # dell'ID fonderebbe per errore persone diverse.
                    "candidate_id": f"wp-{slugify(raw_name)}-{page['tier']}",
                    "name": _clean_name(raw_name),
                    "club": club.strip(),
                    "role": _normalize_role(m.group("pos")),
                    "dob": f"{m.group('by')}-{int(m.group('bm')):02d}-{int(m.group('bd')):02d}",
                    "tier": page["tier"],
                    "source": "wikipedia",
                }
            )
    return candidates


# ============================================================
# CANDIDATE POOL - watchlist manuale
# ============================================================

def fetch_watchlist_candidates(cfg: dict) -> list[dict]:
    """Nomi che Mirko vuole sempre in pool. Nessuna data di nascita
    strutturata disponibile per questi (sono nomi, non QID) - il loro
    Signal Score restera' marcato 'dati parziali' finche' non arriva
    almeno il segnale di buzz."""
    out = []
    names = list(cfg["candidate_sources"]["manual_watchlist"])
    oriundi = cfg["candidate_sources"].get("fsgc_oriundi_watchlist") or []
    for name in names:
        out.append({"candidate_id": f"watch-{slugify(name)}", "name": name, "club": "",
                     "dob": None, "tier": "watchlist", "source": "manual_watchlist"})
    for name in oriundi:
        out.append({"candidate_id": f"oriundi-{slugify(name)}", "name": name, "club": "",
                     "dob": None, "tier": "watchlist", "source": "fsgc_oriundi_watchlist"})
    return out


def _more_complete(a: dict, b: dict) -> dict:
    """Un giocatore puo' comparire in piu' righe grezze con dati diversi
    (piu' appartenenze 'correnti' contemporanee su Wikidata - verificato
    live per club e ruolo). Tiene la riga con piu' campi utili valorizzati,
    non semplicemente l'ultima incontrata."""
    score_a = sum(1 for k in ("club", "role") if a.get(k))
    score_b = sum(1 for k in ("club", "role") if b.get(k))
    return a if score_a >= score_b else b


def fetch_candidate_pool(cfg: dict) -> list[dict]:
    pool = (
        fetch_serie_players(cfg)
        + fetch_conmebol_squads(cfg)
        + fetch_nationality_players(cfg)
        + fetch_watchlist_candidates(cfg)
    )
    seen = {}
    for c in pool:
        cid = c["candidate_id"]
        seen[cid] = _more_complete(seen[cid], c) if cid in seen else c
    return list(seen.values())


# ============================================================
# LAYER A - eta' relativa al livello
# ============================================================

def age_vs_level_score(candidate: dict, cfg: dict) -> float | None:
    """None = dato non disponibile (mai un numero inventato)."""
    dob = candidate.get("dob")
    tier = candidate.get("tier")
    ref = cfg["age_reference"].get(tier)
    if not dob or not ref:
        return None
    try:
        birth = datetime.fromisoformat(dob)
    except ValueError:
        return None
    age_years = (datetime.now() - birth).days / 365.25
    years_below = ref["reference_age"] - age_years
    # normalizzato 0-1, satura oltre spread_years - non premia all'infinito
    # un'eta' improbabile (bug di scala)
    return max(0.0, min(1.0, years_below / ref["spread_years"]))


# ============================================================
# LAYER A - buzz precoce
# ============================================================

def _publisher_of(title: str) -> str:
    """Google News RSS mette il link di redirect (news.google.com/...), non
    l'URL reale della testata (verificato live) - il nome della testata sta
    invece in coda al titolo: "Headline - Nome Testata"."""
    if " - " not in title:
        return title.strip()
    return title.rsplit(" - ", 1)[-1].strip()


def _source_tier(publisher: str, cfg: dict) -> int:
    tiers = cfg["source_tiers"]
    publisher_lower = publisher.lower()
    if any(publisher_lower == t.lower() for t in (tiers.get("tier_1") or [])):
        return 1
    if any(publisher_lower == t.lower() for t in (tiers.get("tier_2") or [])):
        return 2
    return 3  # default: fonte di nicchia, e' li' che nasce il segnale


def buzz_score(candidate: dict, history: dict, cfg: dict) -> dict:
    """Ritorna dict con 'score' (0-1 o None) e i dettagli per la UI/storico.
    Cold start esplicito: al primo run per un candidato la velocita' non e'
    calcolabile (nessun run precedente) -> il buzz intero e' 'non ancora
    disponibile', non un numero stimato."""
    candidate_id = candidate["candidate_id"]
    prior_runs = history.get(candidate_id, {}).get("runs", [])
    is_cold_start = len(prior_runs) == 0

    query = f'"{candidate["name"]}" "{candidate["club"]}"' if candidate.get("club") else f'"{candidate["name"]}"'
    results = search_google_news(query, max_results=8)
    results = [r for r in results if "error" not in r]

    publishers = [_publisher_of(r["title"]) for r in results if r.get("title")]
    tiers_seen = [_source_tier(p, cfg) for p in publishers]
    mention_count = len(results)

    run_snapshot = {"run_at": _now_iso(), "mention_count": mention_count,
                     "publishers": publishers, "tier1_present": 1 in tiers_seen}

    if is_cold_start:
        return {"score": None, "available": False, "reason": "primo run, nessuno storico",
                "mention_count": mention_count, "snapshot": run_snapshot}

    bw = cfg["buzz_weights"]
    sub_scores = {}

    # velocita': delta rispetto all'ultimo run disponibile
    last = prior_runs[-1]
    velocity_raw = mention_count - last.get("mention_count", 0)
    sub_scores["velocity"] = max(0.0, min(1.0, velocity_raw / 5.0))

    # tier delle fonti: media pesata verso il tier 3 (nicchia)
    if mention_count > 0:
        tier_weight = {1: 0.1, 2: 0.5, 3: 1.0}
        niche = sum(tier_weight[t] for t in tiers_seen) / mention_count
        if mention_count > bw["mainstream_mention_threshold"]:
            niche *= 0.3  # gia' mainstream, il vantaggio e' sfumato
        sub_scores["niche_source_tier"] = niche
    else:
        sub_scores["niche_source_tier"] = 0.0

    # diffusione geografica: prima volta che compare una fonte tier-1
    # dopo che nei run precedenti non ce n'era nessuna
    had_tier1_before = any(r.get("tier1_present") for r in prior_runs)
    sub_scores["geographic_crossing"] = 1.0 if (1 in tiers_seen and not had_tier1_before) else 0.0

    total_weight = sum(bw[k] for k in sub_scores)
    score = sum(sub_scores[k] * bw[k] for k in sub_scores) / total_weight if total_weight else 0.0

    return {"score": score, "available": True, "sub_scores": sub_scores,
            "mention_count": mention_count, "snapshot": run_snapshot}


# ============================================================
# LAYER A - Signal Score combinato
# ============================================================

def _needs_more_signal(score_result: dict) -> bool:
    """Un solo componente disponibile E gia' saturo (>=0.9) non basta come
    evidenza per un dossier - lo dice il primo verdetto reale del Giudice
    (Deinner Ordonez, signal 100 basato solo su eta': 'punteggio 100 e' un
    puro artefatto anagrafico... segnale vuoto ad alta rumorosita'')."""
    components = score_result.get("components", {})
    if len(components) != 1:
        return False
    (value,) = components.values()
    return value >= 0.9


def _weights_for_tier(cfg: dict, tier: str) -> dict:
    """Pesi del Signal Score per tier, con fallback su 'default'. Serve per
    le squadre riserve (vedi RESERVE_TEAM_QID): li' l'eta' bassa e' un
    requisito di regolamento, non un segnale raro, quindi pesa molto meno
    li' che altrove - verificato dal Giudice sulla prima run reale, non
    per ipotesi."""
    weights_cfg = cfg["signal_score_weights"]
    return weights_cfg.get(tier, weights_cfg["default"])


def signal_score(candidate: dict, cfg: dict, buzz: dict | None) -> dict:
    """buzz=None significa 'non controllato in questo run' (candidato fuori
    dal sottoinsieme su cui si fa il check di rete, vedi performance.
    buzz_check_pool_size) - trattato come dato mancante, mai come zero."""
    age_component = age_vs_level_score(candidate, cfg)
    buzz = buzz or {"score": None, "available": False, "reason": "non controllato in questo run"}
    buzz_component = buzz["score"] if buzz["available"] else None

    weights = _weights_for_tier(cfg, candidate.get("tier"))
    components = {}
    if age_component is not None:
        components["age_vs_level"] = age_component
    if buzz_component is not None:
        components["buzz"] = buzz_component

    if not components:
        return {"signal_score": None, "components": {}, "partial_data": True,
                "excluded": True, "buzz_detail": buzz}

    total_weight = sum(weights.get(k, 0.0) for k in components)
    combined = sum(components[k] * weights.get(k, 0.0) for k in components) / total_weight if total_weight else 0.0
    return {
        "signal_score": round(combined * 100, 1),
        "components": components,
        "partial_data": len(components) < 2,
        "excluded": False,
        "buzz_detail": buzz,
    }


# ============================================================
# LAYER B - Fit Score contestuale
# ============================================================

def fit_score(candidate: dict, score_result: dict, profile_key: str, cfg: dict) -> dict | None:
    """None = il candidato non passa i filtri del profilo (non entra in lista)."""
    if score_result["excluded"]:
        return None

    profile = cfg["purpose_profiles"].get(profile_key) or next(iter(cfg["purpose_profiles"].values()))

    if candidate.get("tier") not in profile.get("max_tier", []):
        return None

    watchlist_key = profile.get("restrict_to_watchlist")
    if watchlist_key:
        allowed = {slugify(n) for n in (cfg["candidate_sources"].get(watchlist_key) or [])}
        if slugify(candidate["name"]) not in allowed:
            return None

    weights = _weights_for_tier(cfg, candidate.get("tier"))
    multipliers = profile.get("weight_multipliers", {})
    components = score_result["components"]
    total_weight = sum(weights.get(k, 0.0) * multipliers.get(k, 1.0) for k in components)
    if total_weight == 0:
        return {"fit_score": 0.0}
    combined = sum(components[k] * weights.get(k, 0.0) * multipliers.get(k, 1.0) for k in components) / total_weight
    return {"fit_score": round(combined * 100, 1), "profile": profile_key}


# ============================================================
# SWARM - dossier sulle candidature (Cronista/Verificatore/Scettico/Giudice)
# ============================================================

_ROLES = {
    "cronista": "Sei il Cronista. Raccogli i fatti grezzi disponibili su questo giocatore (squadra, ruolo, eta', fonti che lo citano). Nessuna opinione, solo fatti, in italiano, conciso.",
    "verificatore": "Sei il Verificatore. Controlla la coerenza del segnale nel report del Cronista: e' corroborato da piu' fonti indipendenti o da una sola? Il salto di menzioni sembra reale o rumore statistico? Rispondi in italiano, conciso.",
    "scettico": "Sei lo Scettico. Leggi i report precedenti e cerca il motivo per cui questo segnale potrebbe essere un falso positivo: nome comune/omonimia, contesto competitivo debole, dati insufficienti. Sii duro, in italiano, conciso.",
    "giudice": 'Sei il Giudice. Sintetizza i report precedenti in un verdetto finale in JSON RIGOROSO: {"vale_la_pena": true/false, "confidence": 0-100, "motivazione": "una riga"}. Nessun testo fuori dal JSON.',
}


def _candidate_models() -> list[tuple]:
    """Gemini provato per primo (quota per-progetto Google, piu' prevedibile
    della pool free community di OpenRouter che ci ha gia' bloccato con un
    limite giornaliero condiviso sull'intero account), poi OpenRouter, poi
    NVIDIA NIM come ultima riserva. Tre provider genuini nella stessa catena
    di fallback, non un test isolato. Verificato dal vivo quali modelli
    rispondono per davvero prima di fidarsene, per ciascuno: ne' il catalogo
    OpenRouter (includeva modelli non testuali) ne' quello NVIDIA (121
    modelli elencati, molti 404 'Not found for account') ne' quello Gemini
    (gemini-2.0-flash/-lite danno 429 'limit: 0' su questo progetto) erano
    affidabili solo perche' elencati."""
    pool = [(call_gemini, m["id"]) for m in get_available_gemini_models()]
    pool += [(call_openrouter, m["id"]) for m in get_available_models()[:5]]
    pool += [(call_nvidia, m["id"]) for m in get_available_nvidia_models()]
    return pool or [(call_openrouter, DEFAULT_FALLBACK_MODEL)]


def _call_with_fallback(model_pool: list[tuple], system_prompt: str, user_message: str):
    """I modelli gratuiti possono essere rate-limited in modo imprevedibile
    (verificato live: sia su OpenRouter con 429 per-modello e per-account,
    sia il bisogno di un secondo provider quando il primo e' esaurito per
    la giornata) - prova il prossimo candidato invece di far fallire subito
    l'intero dossier. Ritorna (risposta, call_fn, modello) cosi' il resto
    del dossier riusa lo stesso provider/modello che ha gia' risposto."""
    last_error = None
    for call_fn, model in model_pool:
        try:
            return call_fn(model, system_prompt, user_message), call_fn, model
        except Exception as e:
            last_error = e
    raise last_error


def run_swarm_dossier(candidate: dict, score_result: dict) -> dict:
    model_pool = _candidate_models()
    context = (
        f"Giocatore: {candidate['name']}\nSquadra: {candidate.get('club', 'N/D')}\n"
        f"Tier competizione: {candidate.get('tier', 'N/D')}\n"
        f"Signal Score: {score_result.get('signal_score', 'N/D')}\n"
        f"Componenti disponibili: {list(score_result.get('components', {}).keys())}"
    )

    # il primo ruolo sceglie provider+modello (provando la lista finche' uno
    # risponde), i successivi riusano la stessa coppia per coerenza nel dossier
    cronista, call_fn, model = _call_with_fallback(model_pool, _ROLES["cronista"], context)
    verificatore = call_fn(model, _ROLES["verificatore"], f"{context}\n\nReport Cronista:\n{cronista}")
    scettico = call_fn(
        model, _ROLES["scettico"],
        f"{context}\n\nReport Cronista:\n{cronista}\n\nReport Verificatore:\n{verificatore}",
    )
    giudice_raw = call_fn(
        model, _ROLES["giudice"],
        f"Cronista:\n{cronista}\n\nVerificatore:\n{verificatore}\n\nScettico:\n{scettico}",
    )
    try:
        giudice = json.loads(giudice_raw.replace("```json", "").replace("```", "").strip())
    except Exception:
        giudice = {"vale_la_pena": None, "confidence": None, "motivazione": giudice_raw[:200]}

    return {
        "generated_at": _now_iso(),
        "signal_score_at_generation": score_result.get("signal_score"),
        "model": model,
        "provider": {call_gemini: "gemini", call_nvidia: "nvidia"}.get(call_fn, "openrouter"),
        "cronista": cronista,
        "verificatore": verificatore,
        "scettico": scettico,
        "giudice": giudice,
    }


# ============================================================
# ORCHESTRATORE
# ============================================================

def refresh_radar(profile_key: str = "tactical_profile") -> dict:
    cfg = load_config()
    history = _load_json(BUZZ_HISTORY_FILE)
    feed = _load_json(FEED_FILE)

    candidates = fetch_candidate_pool(cfg)

    # Stage 1: eta'-relativa-al-livello, locale, zero chiamate di rete su
    # tutti i candidati (pool nell'ordine delle centinaia - vedi commento in
    # radar_config.yaml sotto "performance").
    age_scores = {c["candidate_id"]: age_vs_level_score(c, cfg) for c in candidates}

    perf = cfg["performance"]
    watchlist = [c for c in candidates if c["tier"] == "watchlist"]
    rest_sorted = sorted(
        (c for c in candidates if c["tier"] != "watchlist"),
        key=lambda c: age_scores[c["candidate_id"]] if age_scores[c["candidate_id"]] is not None else -1,
        reverse=True,
    )
    # watchlist sempre nel check buzz (curata a mano da Mirko, non si scarta
    # per un age score assente/basso); il resto e' il sottoinsieme piu'
    # promettente secondo lo score gratuito
    buzz_pool = watchlist + rest_sorted[: perf["buzz_check_pool_size"]]

    # Stage 2: buzz score in parallelo, solo sul sottoinsieme selezionato
    buzz_results = {}
    with ThreadPoolExecutor(max_workers=perf["buzz_check_workers"]) as executor:
        futures = {executor.submit(buzz_score, c, history, cfg): c for c in buzz_pool}
        for future in as_completed(futures):
            c = futures[future]
            try:
                buzz_results[c["candidate_id"]] = future.result()
            except Exception as e:
                buzz_results[c["candidate_id"]] = {
                    "score": None, "available": False, "reason": f"errore rete: {e}",
                    "mention_count": 0,
                    "snapshot": {"run_at": _now_iso(), "mention_count": 0,
                                 "publishers": [], "tier1_present": False},
                }

    ranked = []
    for candidate in candidates:
        buzz = buzz_results.get(candidate["candidate_id"])
        sres = signal_score(candidate, cfg, buzz)

        if buzz is not None:
            # aggiorna lo storico solo per chi e' stato davvero controllato
            # in questo run - mai un punteggio buzz costruito su dati non
            # raccolti
            history.setdefault(candidate["candidate_id"], {"runs": []})
            runs = history[candidate["candidate_id"]]["runs"]
            runs.append(buzz["snapshot"])
            history[candidate["candidate_id"]]["runs"] = runs[-20:]  # bound crescita file

        if sres["excluded"]:
            continue
        fres = fit_score(candidate, sres, profile_key, cfg)
        if fres is None:
            continue
        ranked.append({"candidate": candidate, "signal": sres, "fit": fres})

    ranked.sort(key=lambda r: r["fit"]["fit_score"], reverse=True)

    top_n = cfg["swarm"]["top_n_candidates_for_swarm"]
    threshold = cfg["swarm"]["rerun_threshold_points"]

    # Un solo componente disponibile E gia' saturo (es. solo eta', al
    # tetto) non basta per giustificare un dossier: verificato dal Giudice
    # sulla prima run reale ("punteggio 100 e' un puro artefatto
    # anagrafico... segnale vuoto ad alta rumorosita'", su Deinner
    # Ordonez). Si salta la generazione per questi candidati - lo slot
    # libero va al prossimo in classifica, invece di sprecare 4 chiamate
    # AI su un verdetto gia' prevedibile.
    swarm_candidates = [e for e in ranked if not _needs_more_signal(e["signal"])]

    # Misurato dal vivo: un ciclo sequenziale su top_n=15 (4 chiamate AI
    # ciascuno) ha superato i 9 minuti senza finire, troncato da Cloud Run
    # con un 503. I dossier di candidati DIVERSI sono indipendenti tra loro
    # (solo le 4 chiamate DENTRO un dossier devono restare in ordine, per
    # coerenza Cronista->Giudice) - si parallelizza a livello di candidato,
    # non dentro il singolo dossier.
    to_generate = []
    for entry in swarm_candidates[:top_n]:
        cid = entry["candidate"]["candidate_id"]
        existing = feed.get(cid, {})
        last_dossier = existing.get("dossier")
        new_score = entry["signal"]["signal_score"] or 0
        needs_dossier = (
            last_dossier is None
            or last_dossier.get("signal_score_at_generation") is None
            or abs(new_score - last_dossier["signal_score_at_generation"]) >= threshold
        )
        if needs_dossier:
            to_generate.append(entry)
        else:
            entry["dossier"] = last_dossier

    with ThreadPoolExecutor(max_workers=cfg["swarm"]["swarm_workers"]) as executor:
        futures = {
            executor.submit(run_swarm_dossier, entry["candidate"], entry["signal"]): entry
            for entry in to_generate
        }
        for future in as_completed(futures):
            entry = futures[future]
            try:
                entry["dossier"] = future.result()
            except Exception as e:
                # mai un crash silenzioso: il candidato resta in classifica,
                # solo il dossier AI risulta esplicitamente non disponibile
                entry["dossier"] = {"error": f"Dossier AI non disponibile: {e}"}

    for entry in ranked:
        if "dossier" not in entry and _needs_more_signal(entry["signal"]):
            entry["dossier"] = {
                "skipped": "Segnale singolo e gia' al tetto (es. solo eta'-relativa, senza buzz a corroborare): "
                           "serve un altro segnale prima di spendere un dossier AI, non solo un numero alto."
            }

    # persistenza append-only: uno storico di punteggi per candidato, mai
    # sovrascritto - e' l'unico modo per verificare nel tempo se il segnale
    # ha davvero anticipato qualcosa
    run_at = _now_iso()
    for entry in ranked:
        cid = entry["candidate"]["candidate_id"]
        record = feed.setdefault(cid, {"identity": entry["candidate"], "history": []})
        record["identity"] = entry["candidate"]
        record["history"].append(
            {
                "run_at": run_at,
                "signal_score": entry["signal"]["signal_score"],
                "components": entry["signal"]["components"],
                "partial_data": entry["signal"]["partial_data"],
                "fit_score": entry["fit"]["fit_score"],
                "profile_used": profile_key,
            }
        )
        if "dossier" in entry:
            record["dossier"] = entry["dossier"]

    _save_json(FEED_FILE, feed)
    _save_json(BUZZ_HISTORY_FILE, history)

    return {
        "run_at": run_at,
        "profile_used": profile_key,
        "candidates_evaluated": len(candidates),
        "candidates_ranked": len(ranked),
        "results": [
            {
                "candidate_id": e["candidate"]["candidate_id"],
                "name": e["candidate"]["name"],
                "club": e["candidate"].get("club"),
                "role": e["candidate"].get("role"),
                "dob": e["candidate"].get("dob"),
                "tier": e["candidate"].get("tier"),
                "nationality_label": e["candidate"].get("nationality_label"),
                "source": e["candidate"].get("source"),
                "signal_score": e["signal"]["signal_score"],
                "components": e["signal"]["components"],
                "fit_score": e["fit"]["fit_score"],
                "partial_data": e["signal"]["partial_data"],
                "dossier": e.get("dossier") or feed.get(e["candidate"]["candidate_id"], {}).get("dossier"),
            }
            for e in ranked
        ],
    }


def latest_feed() -> dict:
    return _load_json(FEED_FILE)


# ============================================================
# DIAGNOSTICA DI COPERTURA - "quanto e' buona questa biblioteca qui?"
# ============================================================
# Non sceglie automaticamente la fonte migliore per paese (richiederebbe
# avere piu' fonti candidate sullo stesso paese da confrontare, e oggi ne
# abbiamo una sola verificata per contesto). Misura solo quanto e' densa
# la copertura di una fonte gia' configurata, cosi' una copertura scarsa si
# vede subito invece di scoprirla per caso (com'e' successo con Oliver Odell
# e il club mancante). Riutilizzabile ogni volta che si aggiunge un paese.

def _dedup_by_id(rows: list[dict]) -> list[dict]:
    """Un giocatore puo' comparire piu' volte nei risultati grezzi (piu'
    appartenenze 'correnti' contemporanee su Wikidata - verificato live:
    per la Nigeria il conteggio grezzo superava il totale via COUNT). La
    diagnostica deve riflettere i candidati DISTINTI che finiranno davvero
    in pool dopo il dedup di fetch_candidate_pool, non le righe grezze -
    altrimenti i numeri mostrati sono gonfiati e fuorvianti."""
    seen = {}
    for r in rows:
        cid = r.get("candidate_id")
        seen[cid] = _more_complete(seen[cid], r) if cid in seen else r
    return list(seen.values())


def _coverage_stats(rows: list[dict], total_hint: int | None = None) -> dict:
    rows = _dedup_by_id(rows) if rows and rows[0].get("candidate_id") else rows
    n = len(rows)
    return {
        "candidati": n,
        "con_data_nascita": sum(1 for r in rows if r.get("dob")),
        "con_club_noto": sum(1 for r in rows if r.get("club")),
        "pct_con_club": round(sum(1 for r in rows if r.get("club")) / n * 100, 1) if n else 0.0,
        "limite_500_raggiunto": n >= 500,
        "totale_reale_stimato": total_hint,
    }


def _sparql_count_nationality(country_qid: str, gender_qid: str) -> int | None:
    """Query di sole COUNT (senza LIMIT) per sapere se il totale reale supera
    il tetto di 500 che mettiamo alla query principale (per restare veloci)."""
    query = f"""
    SELECT (COUNT(?player) AS ?count) WHERE {{
      ?player wdt:P27 wd:{country_qid} .
      ?player wdt:P106 wd:Q937857 .
      ?player wdt:P21 wd:{gender_qid} .
      ?player wdt:P569 ?dob .
      FILTER(YEAR(?dob) >= {_min_birth_year()})
    }}
    """
    url = WIKIDATA_SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({"query": query, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)
        return int(data["results"]["bindings"][0]["count"]["value"])
    except Exception:
        return None


def diagnose_coverage(cfg: dict | None = None) -> dict:
    """Diagnostica copertura di TUTTE le fonti configurate. Non modifica
    nulla, non salva nulla - solo lettura, per decidere se una fonte/paese
    e' abbastanza densa da fidarsi o se serve cercare un'alternativa."""
    cfg = cfg or load_config()
    report = {"wikidata_leagues": {}, "wikidata_nationalities": {}, "wikipedia_youth_squads": {}}

    for league_key, league_cfg in cfg["candidate_sources"]["wikidata_leagues"].items():
        rows = _sparql_current_squad(league_cfg["qid"])
        report["wikidata_leagues"][league_key] = _coverage_stats(rows)

    for pool_key, pool_cfg in (cfg["candidate_sources"].get("wikidata_nationalities") or {}).items():
        rows = _sparql_nationality_pool(pool_cfg["country_qid"], pool_cfg["gender_qid"])
        total = _sparql_count_nationality(pool_cfg["country_qid"], pool_cfg["gender_qid"])
        report["wikidata_nationalities"][pool_key] = _coverage_stats(rows, total_hint=total)

    for page in cfg["candidate_sources"]["wikipedia_youth_squads"]:
        wikitext = _fetch_wikipedia_wikitext(page["title"])
        rows = [{"dob": "x", "club": m.group("club") or m.group("club_plain")}
                for m in _NAT_FS_PLAYER_RE.finditer(wikitext or "")]
        stats = _coverage_stats(rows)
        stats["pagina_raggiungibile"] = wikitext is not None
        report["wikipedia_youth_squads"][page["title"]] = stats

    return report


def probe_nationality(country_qid: str, gender_qid: str, label: str = "") -> dict:
    """Diagnostica veloce su UN paese non ancora in config, per decidere se
    vale la pena aggiungerlo. Non tocca radar_config.yaml - va aggiunto a
    mano dopo aver visto numeri che convincono."""
    rows = _sparql_nationality_pool(country_qid, gender_qid)
    total = _sparql_count_nationality(country_qid, gender_qid)
    stats = _coverage_stats(rows, total_hint=total)
    stats["label"] = label or country_qid
    return stats


if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) > 1 and _sys.argv[1] == "diagnose":
        report = diagnose_coverage()
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print("Uso: python3 discovery_engine.py diagnose")
