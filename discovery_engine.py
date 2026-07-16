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
import threading
import unicodedata
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import yaml

from monitor.web_monitor import search_google_news
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
WATCHLIST_FILE = BASE_DIR / "watchlist.json"
OBSERVATIONS_FILE = BASE_DIR / "radar_observations.json"

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


# ============================================================
# CONFIG / STATO
# ============================================================

def load_config() -> dict:
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


class PersistenceError(Exception):
    """Il DB e' configurato ma non risponde. Errore DEDICATO perche' chi legge
    non deve mai scambiarlo per 'nessun dato': un refresh partito da {} per un
    errore transitorio finirebbe, a fine run, per sovrascrivere su Postgres
    l'INTERO storico append-only con i soli dati del run corrente - il tipo di
    perdita che noti solo il giorno che ti servivano i mesi di storico."""


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


# Connessione riusata a livello di modulo, dietro lock (il refresh gira in un
# thread di sfondo mentre le richieste web leggono): prima ogni load/save
# apriva una connessione NUOVA a Neon (handshake TLS + resume dall'autosuspend
# del free tier = secondi) e rieseguiva la CREATE TABLE ogni volta - decine di
# connessioni sequenziali per un solo refresh. Il retry singolo serve proprio
# per Neon: chiude le connessioni rimaste inattive, il primo uso dopo una
# pausa fallisce e deve solo riconnettersi, non e' un errore vero.
_db_lock = threading.Lock()
_db_conn = None
_db_table_ready = False


def _db_run(fn):
    """Esegue fn(conn) sulla connessione condivisa, con commit e un retry su
    connessione fresca. Dopo due tentativi falliti alza PersistenceError -
    mai un risultato vuoto spacciato per 'nessun dato'."""
    global _db_conn, _db_table_ready
    with _db_lock:
        last_error = None
        for _attempt in (1, 2):
            try:
                if _db_conn is None or _db_conn.closed:
                    _db_conn = psycopg2.connect(DATABASE_URL, connect_timeout=10)
                    _db_table_ready = False
                if not _db_table_ready:
                    _db_ensure_table(_db_conn)
                    _db_table_ready = True
                result = fn(_db_conn)
                _db_conn.commit()
                return result
            except Exception as e:
                last_error = e
                try:
                    _db_conn.close()
                except Exception:
                    pass
                _db_conn = None
                _db_table_ready = False
        raise PersistenceError(f"Postgres non risponde: {last_error}") from last_error


def _load_json(path: Path) -> dict:
    """path.stem diventa la chiave su Postgres quando DATABASE_URL e'
    impostata (radar_feed.json -> 'radar_feed'), altrimenti file locale -
    stesso comportamento di prima, cosi' lo sviluppo senza DB configurato
    non si rompe. Se il DB e' configurato ma non risponde alza
    PersistenceError (vedi la classe): il chiamante fallisce in modo
    esplicito invece di proseguire su uno stato vuoto."""
    if DATABASE_URL and psycopg2:
        def read(conn):
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM radar_state WHERE key = %s", (path.stem,))
                row = cur.fetchone()
                return row[0] if row else {}
        return _db_run(read)

    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_json(path: Path, data: dict):
    if DATABASE_URL and psycopg2:
        def write(conn):
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO radar_state (key, data, updated_at)
                    VALUES (%s, %s, now())
                    ON CONFLICT (key) DO UPDATE SET data = EXCLUDED.data, updated_at = now()
                    """,
                    (path.stem, psycopg2.extras.Json(data)),
                )
        try:
            _db_run(write)
            return
        except PersistenceError as e:
            # Il DB e' morto A META' refresh (le letture iniziali erano
            # passate, altrimenti non saremmo qui): il lavoro gia' fatto non
            # si butta, si scrive il backup d'emergenza su file locale. Ma a
            # voce alta nei log, non in silenzio: il file su Cloud Run e'
            # effimero e /api/radar/health continuera' a dire la verita'.
            print(f"[persistenza] ATTENZIONE: {e} - '{path.stem}' scritto SOLO su file locale effimero.")

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def persistence_status() -> dict:
    """Dice CHIARAMENTE dove vive lo stato: Postgres durevole, oppure file
    effimero. Con il DB configurato le letture falliscono ESPLICITAMENTE se
    Postgres non risponde (PersistenceError, vedi _load_json) e solo le
    scritture a meta' refresh ripiegano sul file locale come backup
    d'emergenza - questo endpoint resta il posto dove 'credo sia su Neon'
    diventa 'lo vedo', p.es. per uno sbaglio nella DATABASE_URL."""
    if not DATABASE_URL:
        return {"mode": "file", "durable": False,
                "message": "Nessun DATABASE_URL impostata: lo stato e' su file locale, EFFIMERO su Cloud Run (si azzera a ogni deploy/riavvio)."}
    if not psycopg2:
        return {"mode": "file", "durable": False,
                "message": "DATABASE_URL c'e' ma psycopg2 non e' installato: si sta scrivendo su file locale effimero."}

    def read(conn):
        with conn.cursor() as cur:
            cur.execute("SELECT key, pg_column_size(data), updated_at FROM radar_state ORDER BY key")
            return cur.fetchall()
    try:
        rows = _db_run(read)
        keys = [{"key": r[0], "kb": round((r[1] or 0) / 1024, 1),
                 "updated_at": r[2].isoformat() if r[2] else None} for r in rows]
        return {"mode": "postgres", "durable": True,
                "message": f"Stato durevole su Postgres: {len(keys)} tabelle di stato salvate. Lo storico sopravvive ai deploy.",
                "keys": keys}
    except PersistenceError as e:
        return {"mode": "file", "durable": False,
                "message": f"DATABASE_URL impostata ma il DB NON risponde ({e}): lo storico NON e' al sicuro e ogni operazione fallira' esplicitamente."}


def slugify(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# GRAFO DELLE FONTI - osservazioni con provenienza + risolutore
# ============================================================
# Il difetto strutturale misurato dal vivo (audit 2026-07 su 100 QID reali
# del feed: 52% senza club su Wikidata, 19/48 con club "aperto" senza data
# di inizio, casi confermati di club stantio tipo Yokoyama Imabari->Cerezo):
# il motore memorizzava FATTI senza bibliografia ("club = FC Imabari") e a
# ogni run li risovrascriveva dalla stessa fonte. Conseguenze: una correzione
# scoperta via stampa moriva al run successivo, e la query buzz cercava il
# giocatore col club VECCHIO proprio nel momento del trasferimento - zero
# menzioni esattamente quando il segnale esplode (il falso negativo peggiore
# possibile per lo scopo dichiarato del radar).
#
# Qui ogni dato diventa un'OSSERVAZIONE: (candidato, campo, valore, fonte,
# osservato_il, datato_al, url). Le osservazioni si ACCUMULANO (append-only,
# stessa filosofia dello storico punteggi) e un risolutore con regole
# esplicite decide il valore corrente spiegando perche' - mai una
# sovrascrittura muta.
#
# La piramide delle fonti (radar_config.yaml -> piramide.livelli) da' a ogni
# fonte un livello: in basso la nicchia locale e l'occhio umano (fresco,
# vicino al campo), in alto i dati strutturati globali (consolidati, in
# ritardo). REGOLA D'INVERSIONE (piramide.regole_campo): i fatti VELOCI
# (club attuale) si leggono dal basso - un articolo datato batte un claim
# Wikidata non datato - i fatti LENTI (data di nascita) dall'alto.

_OBS_MAX_PER_FIELD = 30  # bound crescita per candidato+campo (come runs[-20:])

# etichette leggibili per le spiegazioni del risolutore
_FONTE_LABELS = {
    "umano": "conferma umana",
    "news": "stampa (ricerca web)",
    "wikipedia_torneo": "pagina torneo Wikipedia",
    "wikidata": "Wikidata",
}


def _fonte_label(fonte: str) -> str:
    return _FONTE_LABELS.get(fonte, fonte)


def record_observation(store: dict, candidate_id: str, campo: str, valore: str,
                       fonte: str, cfg: dict, datato_al: str | None = None,
                       url: str | None = None, nota: str | None = None) -> bool:
    """Aggiunge un'osservazione al grafo (in memoria - il salvataggio e' del
    chiamante). Ritorna True se il grafo e' cambiato. Dedup: se l'ultima
    osservazione della STESSA fonte porta lo stesso valore e' una conferma,
    non una riga nuova - si aggiorna osservato_il e basta."""
    valore = (valore or "").strip()
    if not valore or not candidate_id:
        return False
    livelli = (cfg.get("piramide") or {}).get("livelli") or {}
    if fonte not in livelli:
        # fonte non censita nella piramide: rifiutata esplicitamente - mai un
        # livello indovinato (stessa regola di "mai un numero inventato")
        return False
    obs_list = store.setdefault(candidate_id, {}).setdefault(campo, [])
    now = _now_iso()
    for obs in reversed(obs_list):
        if obs["fonte"] != fonte:
            continue
        if obs["valore"] == valore:
            obs["osservato_il"] = now
            if datato_al and not obs.get("datato_al"):
                obs["datato_al"] = datato_al
            return True
        break  # l'ultima della stessa fonte dice altro -> riga nuova
    entry = {"valore": valore, "fonte": fonte, "osservato_il": now}
    if datato_al:
        entry["datato_al"] = datato_al
    if url:
        entry["url"] = url
    if nota:
        entry["nota"] = nota
    obs_list.append(entry)
    del obs_list[:-_OBS_MAX_PER_FIELD]
    return True


def resolve_field(store: dict, candidate_id: str, campo: str, cfg: dict,
                  fallback: str | None = None) -> dict | None:
    """Il valore corrente di un campo secondo il grafo, con spiegazione
    leggibile. Deterministico: stesse osservazioni -> stessa risposta.

    Regole, in ordine:
      1. la conferma umana piu' recente batte tutto;
      2. se tutte le fonti concordano, vince il valore condiviso;
      3. in disaccordo: per i campi 'dal_basso' (fatti veloci, es. club)
         vince l'osservazione DATATA piu' fresca, e a parita' di niente-date
         il livello di piramide piu' basso (piu' vicino al campo); per i
         campi 'dall_alto' (fatti lenti, es. dob) vince il livello piu' alto.

    fallback: valore noto al chiamante fuori dal grafo - usato solo se il
    grafo non sa nulla, e dichiarato tale nella spiegazione."""
    pir = cfg.get("piramide") or {}
    livelli = pir.get("livelli") or {}
    obs_list = (store.get(candidate_id) or {}).get(campo) or []
    if not obs_list:
        if fallback:
            return {"valore": fallback, "fonte": None, "livello": None,
                    "spiegazione": "dato di partenza, nessuna osservazione registrata",
                    "conflitto": False, "alternativa": None}
        return None

    # ultima osservazione per ciascuna fonte (la lista e' cronologica)
    latest_per_fonte = {}
    for obs in obs_list:
        latest_per_fonte[obs["fonte"]] = obs
    obs_set = list(latest_per_fonte.values())

    def _result(best, spiegazione, conflitto):
        alternative = [o for o in obs_set if o["valore"] != best["valore"]]
        alternative.sort(key=lambda o: o["osservato_il"], reverse=True)
        return {
            "valore": best["valore"],
            "fonte": best["fonte"],
            "livello": livelli.get(best["fonte"]),
            "datato_al": best.get("datato_al"),
            "url": best.get("url"),
            "spiegazione": spiegazione,
            "conflitto": conflitto,
            "alternativa": alternative[0]["valore"] if alternative else None,
            "alternativa_fonte": alternative[0]["fonte"] if alternative else None,
        }

    # 1. umano batte tutti
    human = [o for o in obs_set if livelli.get(o["fonte"]) == 0]
    if human:
        best = max(human, key=lambda o: o["osservato_il"])
        others = any(o["valore"] != best["valore"] for o in obs_set)
        return _result(best, f"confermato a mano il {best['osservato_il'][:10]}", others)

    # 2. accordo pieno
    distinct = {o["valore"] for o in obs_set}
    if len(distinct) == 1:
        best = max(obs_set, key=lambda o: o["osservato_il"])
        spieg = (f"{len(obs_set)} fonti concordano" if len(obs_set) > 1
                 else f"unica fonte: {_fonte_label(best['fonte'])}")
        return _result(best, spieg, False)

    # 3. disaccordo: regola d'inversione per campo
    regola = (pir.get("regole_campo") or {}).get(campo, "dal_basso")
    if regola == "dall_alto":
        best = max(obs_set, key=lambda o: (livelli.get(o["fonte"], -1), o["osservato_il"]))
        spieg = (f"\"{best['valore']}\" secondo {_fonte_label(best['fonte'])} - per questo campo "
                 f"la fonte consolidata batte quella fresca")
        return _result(best, spieg, True)

    dated = [o for o in obs_set if o.get("datato_al")]
    if dated:
        best = max(dated, key=lambda o: o["datato_al"])
        spieg = (f"\"{best['valore']}\" secondo {_fonte_label(best['fonte'])} "
                 f"(datato {best['datato_al'][:10]}) - un'osservazione datata batte i claim senza data")
    else:
        best = min(obs_set, key=lambda o: (livelli.get(o["fonte"], 9), _reversed_ts(o)))
        spieg = (f"\"{best['valore']}\" secondo {_fonte_label(best['fonte'])} - nessuna fonte porta "
                 f"una data, vince il livello piu' vicino al campo")
    return _result(best, spieg, True)


def _reversed_ts(obs: dict) -> float:
    """Chiave di ordinamento per 'piu' recente vince' dentro un min():
    timestamp negato. Un'osservazione con timestamp assente/malformato
    ritorna 0.0, che e' maggiore di ogni timestamp negato valido: perde
    contro qualunque osservazione ben datata, mai un crash."""
    try:
        return -datetime.fromisoformat(obs.get("osservato_il", "")).timestamp()
    except (ValueError, TypeError):
        return 0.0


def confirm_club(candidate_id: str, club: str) -> dict:
    """Conferma umana dalla card: registra l'osservazione fonte=umano (che il
    risolutore fa vincere su tutto) e la PERSISTE subito - e' il fix della
    correzione che prima moriva alla riscrittura successiva da Wikidata."""
    cfg = load_config()
    store = _load_json(OBSERVATIONS_FILE)
    changed = record_observation(store, candidate_id, "club", club, "umano", cfg,
                                 datato_al=_now_iso()[:10])
    if changed:
        _save_json(OBSERVATIONS_FILE, store)
    resolution = resolve_field(store, candidate_id, "club", cfg)
    return {"registrata": changed, "club_provenienza": resolution}


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


def _buzz_queries(candidate: dict) -> list[str]:
    """Le query news per un candidato. Il club viene dal RISOLUTORE del grafo
    (club_risolto), non dal fetch grezzo: una scheda Wikidata stantia non deve
    piu' far cercare il giocatore al club vecchio. Se le fonti sono in
    disaccordo (finestra di transizione, es. trasferimento appena uscito
    sulla stampa ma non ancora su Wikidata) si cerca con ENTRAMBI i club -
    il momento del salto e' esattamente quello in cui il radar non puo'
    permettersi di essere cieco."""
    name = candidate["name"]
    club = candidate.get("club_risolto") or candidate.get("club")
    if not club:
        return [f'"{name}"']
    queries = [f'"{name}" "{club}"']
    alt = candidate.get("club_alternativo")
    if alt and alt != club:
        queries.append(f'"{name}" "{alt}"')
    return queries


def buzz_score(candidate: dict, history: dict, cfg: dict) -> dict:
    """Ritorna dict con 'score' (0-1 o None) e i dettagli per la UI/storico.
    Cold start esplicito: al primo run per un candidato la velocita' non e'
    calcolabile (nessun run precedente) -> il buzz intero e' 'non ancora
    disponibile', non un numero stimato."""
    candidate_id = candidate["candidate_id"]
    prior_runs = history.get(candidate_id, {}).get("runs", [])
    is_cold_start = len(prior_runs) == 0

    results = []
    for query in _buzz_queries(candidate):
        results.extend(search_google_news(query, max_results=8))
    results = [r for r in results if "error" not in r]
    # dedup per titolo/link (la doppia query in transizione puo' riportare lo
    # stesso articolo due volte) + cap a 8 per non gonfiare la scala di
    # mention_count rispetto ai run a query singola
    seen, unique = set(), []
    for r in results:
        key = (r.get("link") or "") + (r.get("title") or "")[:60]
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    results = unique[:8]

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


def _assert_no_duplicate_candidate_ids(candidate_ids: list[str], stage: str) -> None:
    """Guardia anti-doppione per lo swarm AI: blocca PRIMA di spendere una
    chiamata, non dopo che e' gia' stata pagata/consumata. Il dossier e'
    lingua-agnostico per design (vedi run_swarm_dossier) - questa e' la
    difesa contro un futuro bug (es. un ciclo "per ogni lingua") che
    rimetterebbe lo stesso candidato in coda due volte nello stesso turno."""
    seen = set()
    for cid in candidate_ids:
        if cid in seen:
            raise RuntimeError(
                f"GUARDIA anti-doppione ({stage}): {cid} compare due volte nello stesso "
                "turno - un secondo giro rischierebbe di raddoppiare silenziosamente la "
                "chiamata AI (es. un dossier per lingua). Il dossier resta lingua-agnostico "
                "per design: vedi il commento in run_swarm_dossier."
            )
        seen.add(cid)


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
# LAYER C - stima bayesiana del "livello vero" (filtro alla Kalman, 1D)
# ============================================================
# NON e' un algoritmo predittivo (non abbiamo ancora esiti reali verificati
# per calibrarlo, vedi discussione su validazione) - e' un filtro che stima
# quanto fidarsi del Signal Score attuale alla luce delle osservazioni
# passate dello STESSO candidato, gia' salvate in radar_feed.json. Un run
# isolato e rumoroso pesa meno di una serie di run coerenti nel tempo.
# Formula standard (Kalman 1D): ad ogni osservazione, l'incertezza cresce
# per il tempo passato (process_variance) poi si restringe in base a quanto
# la nuova osservazione e' vicina alla stima corrente rispetto al suo
# rumore atteso (observation_variance, piu' alto se dati parziali).

def bayesian_estimate(history: list[dict], cfg: dict) -> dict | None:
    if not history:
        return None
    bcfg = cfg["bayesian"]
    mean = None
    variance = bcfg["prior_variance"]
    # innovazione normalizzata (z-score) dell'ULTIMA osservazione valida:
    # quanto quel numero ha sorpreso il modello rispetto a cio' che si
    # aspettava da tutte le run precedenti, in deviazioni standard - non e'
    # un sottoprodotto scartato, alimenta la sonda di cambiamento di stato
    # (radar_config.yaml: state_change.shock_z_threshold).
    last_innovation_z = None
    for obs in history:
        score = obs.get("signal_score")
        if score is None:
            continue
        obs_variance = bcfg["observation_variance_partial"] if obs.get("partial_data") else bcfg["observation_variance_full"]
        if mean is None:
            mean = score
            continue
        predicted_variance = variance + bcfg["process_variance"]
        innovation = score - mean
        innovation_std = (predicted_variance + obs_variance) ** 0.5
        last_innovation_z = innovation / innovation_std if innovation_std > 0 else 0.0
        gain = predicted_variance / (predicted_variance + obs_variance)
        mean = mean + gain * innovation
        variance = (1 - gain) * predicted_variance
    if mean is None:
        return None
    std_dev = variance ** 0.5
    return {
        "estimate": round(mean, 1),
        "std_dev": round(std_dev, 1),
        "confidence_band": [round(max(0.0, mean - 1.96 * std_dev), 1), round(min(100.0, mean + 1.96 * std_dev), 1)],
        "n_observations": len(history),
        "last_innovation_z": round(last_innovation_z, 2) if last_innovation_z is not None else None,
    }


def _update_cusum(cusum_state: dict, z: float, cfg: dict) -> dict:
    """CUSUM a due code sullo z-score (non sul punteggio grezzo, cosi' resta
    comparabile tra tier/candidati con rumore atteso diverso). Persistito
    per candidato tra un run e l'altro (radar_feed.json), non ricalcolato
    da zero ogni volta - altrimenti una deriva lenta non si accumulerebbe
    mai abbastanza da superare la soglia."""
    scfg = cfg["state_change"]
    k = scfg["cusum_k"]
    pos = max(0.0, cusum_state.get("pos", 0.0) + z - k)
    neg = max(0.0, cusum_state.get("neg", 0.0) - z - k)
    return {"pos": round(pos, 3), "neg": round(neg, 3)}


# ============================================================
# LAYER E - LA CURVA: posizione sulla curva di adozione
# ============================================================
# Lo scopo del radar, nella formulazione piu' precisa: trovare il giocatore
# mentre e' ANCORA nella fase early adopter ma sta per uscirne - quando piu'
# fattori oggettivi convergono e indicano che visibilita' e concorrenza
# stanno per salire, e con loro il costo per averlo. Basi consolidate, non
# inventate qui: curva di diffusione a S (Rogers/Bass: la fase di massima
# accelerazione PRECEDE il punto di flesso) e two-step flow (la notizia
# scala dalla stampa di nicchia alle testate generaliste un gradino per
# volta - la scalata dei tier delle fonti e' il preavviso del crossing).
#
# Tutto e' calcolato dagli snapshot gia' persistiti in buzz_history.json
# ({run_at, mention_count, publishers, tier1_present} per run): zero nuove
# chiamate di rete, zero dati inventati. Nessuna stima temporale ("croce
# tra 2 settimane") perche' i run avvengono a intervalli irregolari (solo
# quando si preme "cerca aggiornamenti") e sarebbe una precisione finta.

# Etichette in italiano-calcistico nativo, non gergo da diffusion-theory:
# "esplodere" e' esattamente il verbo che il calcio italiano usa per un
# giovane che sfonda ("quest'anno e' esploso"). La fase e' l'intero (stabile),
# l'etichetta e' cosmetica - il frontend la ri-deriva dall'intero cosi' un
# cambio di parole non lascia etichette vecchie nei feed gia' salvati.
_PHASE_LABELS = {
    0: "nessuno ne parla",
    1: "solo fonti locali",
    2: "se ne parla",
    3: "sta per esplodere",
    4: "sui grandi giornali",
    5: "lo sanno tutti",
}

# max_results della query Google News in buzz_score: oltre questo numero il
# conteggio menzioni satura e la crescita non e' piu' misurabile - il
# fattore accelerazione in quel caso si dichiara muto, non attivo ne'
# inattivo per finta.
_MENTION_SATURATION = 8


def adoption_curve_assessment(candidate_id: str, history: dict, cfg: dict) -> dict:
    """Classifica la posizione del candidato sulla curva di adozione (fasi
    0-5, vedi _PHASE_LABELS e radar_config.yaml sezione adoption_curve) e
    calcola i 4 fattori di decollo con una spiegazione in italiano ciascuno:
    sono LORO l'output per l'occhio umano, il numero e' solo il riassunto."""
    acfg = cfg["adoption_curve"]
    runs = history.get(candidate_id, {}).get("runs", [])
    if len(runs) < acfg["min_runs_for_assessment"]:
        return {
            "phase": None, "phase_label": "storico insufficiente",
            "runs_seen": len(runs), "exit_pressure": None, "factors": None,
        }

    counts = [r.get("mention_count", 0) or 0 for r in runs]
    cur = runs[-1]

    # tier-1 gia' visto prima di questo run = mainstream, il vantaggio e'
    # sfumato; tier-1 per la PRIMA volta ora = crossing, finestra chiusa in
    # questo istante (e' lo stesso evento del geographic_crossing di
    # buzz_score, riletto come posizione di fase)
    tier1_before = any(r.get("tier1_present") for r in runs[:-1])
    tier1_now = bool(cur.get("tier1_present"))
    if tier1_before:
        return {"phase": 5, "phase_label": _PHASE_LABELS[5], "runs_seen": len(runs),
                "exit_pressure": None, "factors": None}
    if tier1_now:
        return {"phase": 4, "phase_label": _PHASE_LABELS[4], "runs_seen": len(runs),
                "exit_pressure": None, "factors": None}

    # --- 4 fattori di decollo, ognuno indipendente e ispezionabile ---
    factors = {}

    # accelerazione: la crescita delle menzioni non sta rallentando sugli
    # ultimi due intervalli (firma pre-flesso di una curva a S)
    d_prev = counts[-2] - counts[-3]
    d_last = counts[-1] - counts[-2]
    saturated = counts[-1] >= _MENTION_SATURATION and counts[-2] >= _MENTION_SATURATION
    factors["accelerazione"] = {
        "active": (not saturated) and d_last > 0 and d_last >= d_prev,
        "detail": (
            "conteggio menzioni al tetto della query: crescita ulteriore non misurabile"
            if saturated else
            f"menzioni {counts[-3]} → {counts[-2]} → {counts[-1]} negli ultimi controlli"
        ),
    }

    # scalata dei tier: prima fonte tier-2 (nazionale/di settore) comparsa
    # negli ultimi N run, dopo controlli di sola stampa di nicchia
    def _tier2_in(run):
        return any(_source_tier(p, cfg) == 2 for p in (run.get("publishers") or []))
    window = acfg["tier_climb_recent_window"]
    climb_active = any(_tier2_in(r) for r in runs[-window:]) and not any(_tier2_in(r) for r in runs[:-window])
    factors["scalata_tier"] = {
        "active": climb_active,
        "detail": (
            "prima testata di livello nazionale/di settore comparsa negli ultimi controlli, prima solo stampa locale"
            if climb_active else
            "nessuna scalata recente nel livello delle fonti"
        ),
    }

    # allargamento fonti: piu' testate DISTINTE di quante mai viste in un
    # singolo controllo precedente - adozione indipendente, non lo stesso
    # blog che insiste
    distinct_now = len(set(cur.get("publishers") or []))
    distinct_max_before = max((len(set(r.get("publishers") or [])) for r in runs[:-1]), default=0)
    breadth_active = distinct_now >= 2 and distinct_now > distinct_max_before
    factors["allargamento_fonti"] = {
        "active": breadth_active,
        "detail": f"{distinct_now} testate distinte in questo controllo (massimo precedente: {distinct_max_before})",
    }

    # persistenza: presente nelle fonti da N controlli consecutivi - gli
    # spike (una partita buona, un articolo isolato) decadono, l'adozione
    # vera persiste
    k = acfg["persistence_min_runs"]
    persist_active = len(runs) >= k and all(c > 0 for c in counts[-k:])
    factors["persistenza"] = {
        "active": persist_active,
        "detail": (
            f"presente nelle fonti da almeno {k} controlli consecutivi"
            if persist_active else "presenza discontinua nelle fonti"
        ),
    }

    weights = acfg["factor_weights"]
    n_active = sum(1 for f in factors.values() if f["active"])
    exit_pressure = round(sum(weights[name] for name, f in factors.items() if f["active"]))

    if n_active >= acfg["takeoff_min_factors"]:
        phase = 3
    elif persist_active or (counts[-1] > 0 and counts[-2] > 0):
        phase = 2
    elif counts[-1] > 0:
        phase = 1
    else:
        phase = 0

    return {
        "phase": phase, "phase_label": _PHASE_LABELS[phase],
        "runs_seen": len(runs), "exit_pressure": exit_pressure, "factors": factors,
    }


# --- Validazione retroattiva della curva -------------------------------------
# La differenza tra una metodologia e un'opinione formattata bene: quando un
# candidato attraversa davvero verso il mainstream (fase 4), si guarda
# indietro nel suo storico e si registra se il radar l'aveva marcato
# "decollo imminente" PRIMA. Col tempo questo registro misura quanto il
# rilevatore anticipa per davvero - ed e' il dato con cui correggere i pesi
# dei fattori, invece che a sensazione.

CURVE_VALIDATION_FILE = BASE_DIR / "curve_validation.json"


# Il ledger viene caricato UNA volta a inizio refresh e salvato UNA volta a
# fine refresh (vedi refresh_radar): prima queste due funzioni facevano
# load+save su Postgres PER OGNI candidato con una fase fresca - fino a oltre
# cento round-trip sequenziali verso Neon in una sola scansione, per un file
# di pochi KB. Ritornano True se hanno modificato il ledger.

def _record_curve_crossing(ledger: dict, record: dict, candidate: dict, run_at: str) -> bool:
    events = ledger.get("events", [])
    # un candidato attraversa una sola volta: mai duplicare l'evento se un
    # run successivo rilegge lo stesso stato
    if any(ev.get("candidate_id") == candidate["candidate_id"] for ev in events):
        return False
    prior_phases = [
        e["curve"].get("phase")
        for e in record["history"][:-1]
        if isinstance(e.get("curve"), dict)
    ]
    events.append({
        "candidate_id": candidate["candidate_id"],
        "name": candidate.get("name"),
        "crossed_at": run_at,
        "anticipato": 3 in prior_phases,
        "fasi_precedenti": [p for p in prior_phases if p is not None][-5:],
    })
    ledger["events"] = events  # preserva "flags", non sovrascrivere l'intero ledger
    return True


# --- Il tabellone: precisione, non solo richiamo -----------------------------
# La mossa con cui si smonta un sistema come questo e' sempre la stessa:
# "citate solo i successi (Mora, Villarreal), e i fallimenti?". Il registro
# dei crossing sopra misura il RICHIAMO (dei giocatori esplosi, quanti
# avevamo segnalato). Ma da solo si presta all'accusa di survivorship bias,
# perche' non conta i falsi positivi. Qui si traccia la PRECISIONE: ogni
# volta che scatta "sta per esplodere" (fase 3) si apre una scommessa
# verificabile, e la si chiude con l'esito reale - esploso (ha attraversato)
# o sgonfiato (e' ricaduto senza attraversare). Un sistema che nasconde i
# suoi errori e' marketing; questo li conta, davanti a chi lo vuole debunkare.

def _update_flag_ledger(ledger: dict, candidate: dict, phase, run_at: str) -> bool:
    if phase is None:
        return False
    flags = ledger.get("flags", [])
    cid = candidate["candidate_id"]
    open_flag = next((f for f in flags if f["candidate_id"] == cid and f["outcome"] == "pending"), None)
    changed = False
    if phase == 3 and open_flag is None:
        # nuova segnalazione: scommessa aperta, esito ancora ignoto
        flags.append({
            "candidate_id": cid, "name": candidate.get("name"),
            "flagged_at": run_at, "outcome": "pending", "resolved_at": None,
        })
        changed = True
    elif phase != 3 and open_flag is not None:
        # la scommessa si chiude: attraversato (>=4) = esploso, altrimenti
        # ricaduto senza sfondare = sgonfiato (falso positivo, contato)
        open_flag["outcome"] = "esploso" if phase >= 4 else "sgonfiato"
        open_flag["resolved_at"] = run_at
        changed = True
    if changed:
        ledger["flags"] = flags
    return changed


def curve_validation_summary() -> dict:
    events = _load_json(CURVE_VALIDATION_FILE).get("events", [])
    return {
        "crossings": len(events),
        "anticipated": sum(1 for e in events if e.get("anticipato")),
    }


def track_record_summary() -> dict:
    """Il tabellone completo per l'avvocato del diavolo: precisione (dei
    segnalati, quanti sono davvero esplosi vs sgonfiati) E richiamo (degli
    esplosi, quanti avevamo segnalato). Nessun numero gonfiato: precision e
    recall restano None finche' non c'e' un caso risolto, cosi' su campione
    minuscolo il sistema dice 'non lo so ancora' invece di inventare una
    percentuale."""
    ledger = _load_json(CURVE_VALIDATION_FILE)
    flags = ledger.get("flags", [])
    events = ledger.get("events", [])
    esplosi = sum(1 for f in flags if f["outcome"] == "esploso")
    sgonfiati = sum(1 for f in flags if f["outcome"] == "sgonfiato")
    pending = sum(1 for f in flags if f["outcome"] == "pending")
    resolved = esplosi + sgonfiati
    crossings = len(events)
    anticipati = sum(1 for e in events if e.get("anticipato"))
    return {
        "flagged": len(flags),
        "esplosi": esplosi,
        "sgonfiati": sgonfiati,
        "pending": pending,
        "precision": round(100 * esplosi / resolved) if resolved else None,
        "crossings": crossings,
        "anticipati": anticipati,
        "recall": round(100 * anticipati / crossings) if crossings else None,
    }


def phase_trail(record: dict) -> list:
    """La sequenza reale delle fasi occupate dal candidato nel tempo (una per
    run che aveva una curva calcolata). E' cio' che rende leggibile la salita:
    non un pallino fermo, ma un percorso da mostrare. Solo dati gia' salvati,
    nessun ricalcolo."""
    return [
        e["curve"]["phase"]
        for e in record.get("history", [])
        if isinstance(e.get("curve"), dict) and e["curve"].get("phase") is not None
    ]


def player_caveats(last_entry: dict, bayes: dict | None, identity: dict, cfg: dict) -> list:
    """IL CONTRADDITTORIO per-giocatore: i motivi OGGETTIVI per dubitare di
    questo specifico segnale, calcolati dai suoi stessi dati - non
    dall'AI, cosi' non si possono inventare. E' la versione granulare, sulla
    singola scheda, delle obiezioni del /processo: ogni giocatore si porta
    dietro le sue ragioni di dubbio, sempre, anche quando non c'e' un dossier
    AI. Onesto per costruzione: ogni voce compare solo se davvero vera per
    questo candidato."""
    caveats = []
    comps = last_entry.get("components") or {}
    av = comps.get("age_vs_level")

    if len(comps) == 1 and "age_vs_level" in comps:
        caveats.append("Si regge su un solo indicatore (eta' rispetto al livello): nessun segnale di attenzione esterna lo conferma ancora.")
    if av is not None and av >= 0.9:
        caveats.append("Il punteggio eta' e' al tetto: puo' essere un effetto anagrafico (molto giovane dove l'eta' bassa e' comune), non per forza qualita'.")
    if last_entry.get("partial_data"):
        caveats.append("Dati incompleti: manca almeno un'informazione, il punteggio pieno e' meno affidabile.")

    if bayes:
        n = bayes.get("n_observations")
        band = bayes.get("confidence_band")
        if n is not None and n <= 2:
            caveats.append(f"Visto poche volte ({n} osservazion{'e' if n == 1 else 'i'}): il punteggio puo' cambiare parecchio al prossimo controllo.")
        elif band and len(band) == 2 and (band[1] - band[0]) >= 20:
            caveats.append("Il margine d'incertezza e' ancora ampio: fidati del numero solo dopo qualche altro controllo.")

    curve = last_entry.get("curve") or {}
    runs_seen = curve.get("runs_seen")
    if curve.get("phase") is not None and runs_seen is not None and runs_seen < 4:
        caveats.append(f"La posizione sul percorso e' provvisoria (solo {runs_seen} controlli finora).")

    if identity.get("tier") == "nationality_pool":
        caveats.append("Contesto non d'elite e livello di lega spesso ignoto: mancano riscontri prestazionali sul campo.")

    return caveats


def curve_map_snapshot() -> dict:
    """LA MAPPA: la posizione sulla curva di TUTTI i giocatori con storico
    sufficiente, in un colpo d'occhio. E' la vista che spiega l'intero
    prodotto senza parole - dove sta ognuno nel percorso da sconosciuto a
    conosciuto, e chi e' nella zona calda appena prima dell'esplosione.

    Onesta' strutturale: chi non ha ancora abbastanza storico (< min_runs)
    NON viene posizionato con una fase inventata, viene solo contato come
    'ancora da profilare'. Zero previsione: sono posizioni attuali, non
    frecce sul futuro."""
    feed = _load_json(FEED_FILE)
    watchlist = get_watchlist()
    players = []
    not_yet = 0
    distribution = {p: 0 for p in _PHASE_LABELS}
    for candidate_id, record in feed.items():
        if not record or not record.get("history"):
            continue
        last = record["history"][-1]
        curve = last.get("curve")
        phase = curve.get("phase") if isinstance(curve, dict) else None
        if phase is None:
            not_yet += 1
            continue
        identity = record.get("identity") or {}
        trail = phase_trail(record)
        change = last.get("state_change") or {}
        distribution[phase] += 1
        players.append({
            "candidate_id": candidate_id,
            "name": identity.get("name"),
            "club": identity.get("club"),
            "role": identity.get("role"),
            "signal_score": last.get("signal_score"),
            "phase": phase,
            "exit_pressure": curve.get("exit_pressure") if isinstance(curve, dict) else None,
            # "salito da poco": l'ultima fase e' piu' avanti della precedente -
            # anima la mappa senza inventare nulla, e' il confronto tra due
            # posizioni reali
            "climbing": len(trail) >= 2 and trail[-1] > trail[-2],
            "is_takeoff": change.get("type") == "takeoff",
            "watchlisted": candidate_id in watchlist,
        })
    # i piu' avanti + chi sta esplodendo in cima, cosi' l'occhio cade sulla
    # zona calda per prima
    players.sort(key=lambda p: (p["phase"], p["exit_pressure"] or 0, p["signal_score"] or 0), reverse=True)
    return {
        "players": players,
        "assessed_count": len(players),
        "not_yet_count": not_yet,
        "total_count": len(feed),
        "distribution": distribution,
        "phase_labels": _PHASE_LABELS,
        "validation": curve_validation_summary(),
    }


# ============================================================
# LAYER D - sonda di cambiamento di stato (IL TURNO)
# ============================================================
# Decide se un candidato merita di entrare nel turno di revisione o restare
# silenzioso in archivio. ZERO invenzioni: ogni tipo di cambiamento o e' un
# fatto verificato (club aggiornato via ricerca web, dati parziali risolti,
# verdetto swarm ribaltato) o un test statistico consolidato (innovazione
# Kalman, CUSUM) - mai una soglia arbitraria su "sembra diverso".

def detect_state_change(
    candidate: dict,
    previous_last_entry: dict | None,
    previous_dossier: dict | None,
    current_dossier: dict | None,
    current_partial_data: bool,
    bayes: dict | None,
    cusum_state: dict,
    cfg: dict,
    buzz_detail: dict | None = None,
    curve: dict | None = None,
) -> dict | None:
    scfg = cfg["state_change"]
    current_dossier = current_dossier or {}
    giudice = current_dossier.get("giudice") or {}

    # 1. club aggiornato - solo se il Cronista l'ha davvero verificato via
    # ricerca web in QUESTO run, mai su un sospetto non confermato
    club_aggiornato = giudice.get("club_aggiornato")
    if club_aggiornato:
        old_club = candidate.get("club") or "N/D"
        # Se i due nomi si assomigliano (es. "RCD Mallorca" / "RCD Mallorca
        # B") il cambio sembra irrilevante a prima vista, mentre spesso e'
        # proprio la differenza che conta (prima squadra vs riserve) - il
        # testo lo dice esplicitamente invece di lasciarlo dedurre.
        return {
            "type": "club",
            "tag": "CLUB DA CORREGGERE",
            # campi strutturati per la card: servono al bottone "conferma"
            # che registra l'osservazione fonte=umano nel grafo delle fonti
            "club_vecchio": old_club,
            "club_nuovo": club_aggiornato,
            "lead": (
                f"Attenzione: negli archivi risultava a \"{old_club}\", ma la ricerca web piu' recente dice "
                f"\"{club_aggiornato}\". Controlla di persona se e' un cambio di squadra vero (es. da prima "
                f"squadra a squadra riserve/giovanile, o viceversa) prima di scartarlo o promuoverlo - "
                f"i due nomi possono sembrare uguali a colpo d'occhio ma indicare un livello molto diverso."
            ),
        }

    # 1a. DECOLLO IMMINENTE (Layer E, la ragione per cui il radar esiste):
    # piu' fattori oggettivi indipendenti convergono mentre il giocatore e'
    # ANCORA fuori dai riflettori mainstream - accelerazione delle menzioni,
    # scalata del livello delle fonti, allargamento delle testate,
    # persistenza. Non un singolo spike (quello e' FINESTRA PRECOCE, piu'
    # sotto, volutamente piu' debole): una congiunzione. I dettagli attivi
    # vengono elencati nel testo, cosi' il "perche' ora" e' verificabile
    # riga per riga, mai un punteggio da prendere sulla fiducia.
    if (curve or {}).get("phase") == 3:
        active_details = [f["detail"] for f in curve["factors"].values() if f["active"]]
        return {
            "type": "takeoff",
            "tag": "STA PER ESPLODERE",
            "lead": (
                "Piu' segnali indipendenti stanno salendo insieme, e nessun grande giornale "
                "ne ha ancora scritto: " + "; ".join(active_details) + ". "
                "E' il tratto in cui guardarlo costa ancora poco - appena lo prendono le testate "
                "grandi, salgono visibilita', concorrenza e prezzo. Se il profilo ti interessa, "
                "questo e' il momento del tuo occhio, non fra un mese."
            ),
        }

    # 1b/1c. finestra "early adopter": buzz_score gia' calcola una
    # sub_score "geographic_crossing" (1.0 solo quando una fonte mainstream
    # ne parla per la PRIMA volta, dopo run precedenti di sola nicchia) e
    # "velocity" (variazione di menzioni sul giro precedente) - oggi
    # venivano fuse in un unico numero e perse. Sono il segnale piu'
    # coerente con lo scopo dichiarato ("vede il segnale prima che diventi
    # notizia"): non un dato gia' successo (come il cambio club), ma la
    # finestra ANCORA APERTA prima che tutti se ne accorgano.
    sub_scores = (buzz_detail or {}).get("sub_scores") or {}
    if sub_scores.get("geographic_crossing") == 1.0:
        return {
            "type": "mainstream",
            "tag": "DIVENTATO MAINSTREAM",
            "lead": (
                "Una fonte mainstream ne ha parlato per la prima volta proprio in questo giro, dopo run "
                "precedenti con solo fonti di nicchia: la finestra \"prima che lo sappiano tutti\" si e' "
                "appena chiusa - se ti interessa, e' il momento di muoversi, non di aspettare ancora."
            ),
        }
    velocity = sub_scores.get("velocity")
    if (
        velocity is not None
        and velocity >= scfg["early_velocity_threshold"]
        and not (buzz_detail or {}).get("snapshot", {}).get("tier1_present")
    ):
        return {
            "type": "early",
            "tag": "FINESTRA PRECOCE",
            "lead": (
                "Il numero di menzioni sta salendo rispetto al giro precedente, ma finora solo da fonti di "
                "nicchia - nessuna testata mainstream se n'e' ancora accorta. E' probabilmente il momento "
                "migliore per guardarlo, prima che lo sappiano tutti."
            ),
        }

    # 2. dati parziali risolti dall'ultima volta - prima non c'era abbastanza
    # per fidarsi, ora si', un motivo genuino per riguardarlo
    if previous_last_entry and previous_last_entry.get("partial_data") and not current_partial_data:
        return {
            "type": "resolved",
            "tag": "DATI COMPLETATI",
            "lead": "Prima il segnale era su dati parziali (poco da fidarsi); ora i dati si sono completati.",
        }

    # 3. verdetto swarm ribaltato
    prev_verdict = (previous_dossier or {}).get("giudice", {}).get("vale_la_pena")
    curr_verdict = giudice.get("vale_la_pena")
    if prev_verdict is not None and curr_verdict is not None and prev_verdict != curr_verdict:
        return {
            "type": "verdict",
            "tag": "VERDETTO RIBALTATO",
            "lead": f"Il verdetto dello swarm e' cambiato: {'ora vale la pena seguirlo' if curr_verdict else 'non e piu prioritario ora'}.",
        }

    # 4. shock statistico - salto che l'incertezza attesa non giustifica
    z = (bayes or {}).get("last_innovation_z")
    if z is not None and abs(z) >= scfg["shock_z_threshold"]:
        rising = z > 0
        return {
            "type": "rising" if rising else "falling",
            "tag": f"SALTO ANOMALO ({'SALITA' if rising else 'DISCESA'})",
            "lead": f"Il segnale ha fatto un salto che il modello non si aspettava (z={z:+.1f}), non spiegabile dal solo rumore normale.",
        }

    # 5. deriva lenta ma sostenuta (nessun singolo salto la giustificherebbe)
    if cusum_state.get("pos", 0.0) >= scfg["cusum_threshold"]:
        return {
            "type": "rising",
            "tag": "TENDENZA SOSTENUTA (SALITA)",
            "lead": "Nessun singolo salto anomalo, ma la tendenza e' salita in modo consistente su piu' run.",
        }
    if cusum_state.get("neg", 0.0) >= scfg["cusum_threshold"]:
        return {
            "type": "falling",
            "tag": "TENDENZA SOSTENUTA (DISCESA)",
            "lead": "Nessun singolo salto anomalo, ma la tendenza e' scesa in modo consistente su piu' run.",
        }

    # 6. nuovo ingresso: mai visto prima in un dossier
    if previous_last_entry is None:
        return {
            "type": "new",
            "tag": "NUOVO INGRESSO",
            "lead": "Primo dossier per questo candidato: nessuno storico precedente da confrontare.",
        }

    return None


# Le finestre "aperte" (opportunita' che durano nel tempo) non devono
# sparire dal turno solo perche' un giro non le ha ri-analizzate: sarebbe
# una perdita silenziosa, che l'utente medio legge come un bug. Restano
# finche' non si risolvono davvero. Gli altri tipi (club da correggere,
# verdetto ribaltato, salti) sono eventi puntuali: si mostrano una volta.
_OPEN_WINDOW_TYPES = {"takeoff", "early"}
_CARRY_MAX_RUNS = 6  # oltre N giri senza aggiornamento la finestra "scade"


def _carry_or_close(previous_last_entry: dict | None, fresh_change: dict | None, current_curve: dict | None) -> dict | None:
    """Decide cosa mostrare nel turno per questo giro, senza far sparire
    niente in silenzio. Regole:
    - se c'e' un cambiamento nuovo calcolato ORA, vince (e' l'ultima verita');
    - se il giro precedente aveva una finestra APERTA non risolta, la si
      porta avanti ("gia' visto · finestra aperta") invece di lasciarla
      cadere - a meno che la curva fresca di oggi mostri che si e' risolta
      (arrivato ai grandi giornali, o raffreddato): in quel caso si mostra
      la CHIUSURA una volta, spiegata, e poi sparisce;
    - dopo troppi giri senza ri-analisi la finestra "scade" con una nota,
      mai un silenzio."""
    if fresh_change:
        return fresh_change

    prev = (previous_last_entry or {}).get("state_change") or {}
    if prev.get("type") not in _OPEN_WINDOW_TYPES:
        return None  # evento puntuale gia' mostrato, oppure niente: nulla da portare

    phase = (current_curve or {}).get("phase")
    if phase is not None:  # oggi la curva e' stata ricalcolata: possiamo verificare l'esito
        if phase >= 4:
            return {"type": "closed_crossed", "tag": "FINESTRA CHIUSA — ARRIVATO",
                    "lead": "La finestra si e' chiusa: ora ne parlano anche i grandi giornali. "
                            "Se non ti sei mosso prima, da qui in poi costa di piu' e c'e' piu' concorrenza.",
                    "closing": True}
        if phase <= 2:
            return {"type": "closed_faded", "tag": "FINESTRA CHIUSA — RAFFREDDATO",
                    "lead": "La finestra si e' chiusa senza sfondare: l'attenzione si e' raffreddata, "
                            "il segnale e' rientrato. Puo' sempre ripartire, ma per ora non e' piu' caldo.",
                    "closing": True}
        # phase == 3: ancora aperta, ma nessun dossier nuovo -> si porta avanti

    carried_runs = prev.get("carried_runs", 0) + 1
    if carried_runs > _CARRY_MAX_RUNS:
        return {"type": "closed_stale", "tag": "FINESTRA SCADUTA",
                "lead": "Questa finestra era aperta da diversi giri ma non e' stata piu' aggiornata: "
                        "meglio non fidarsi di un segnale vecchio. Se ti interessa ancora, ricontrollalo a mano.",
                "closing": True}

    carried = dict(prev)
    carried["carried"] = True
    carried["carried_runs"] = carried_runs
    return carried


# ============================================================
# SWARM - dossier sulle candidature (Cronista/Verificatore/Scettico/Giudice)
# ============================================================

# Lette da un procuratore/scout, non da chi ha scritto il codice: mai un
# nome di variabile o un termine tecnico interno (es. "age_vs_level") nel
# testo libero di nessun ruolo - vale per tutti e quattro, ripetuto in ogni
# prompt perche' verificato dal vivo che altrimenti il Giudice ripete
# parola per parola le chiavi che gli passiamo nel contesto.
_PLAIN_LANGUAGE_RULE = (
    "Scrivi per un procuratore o scout, non per un programmatore: mai nomi "
    "di variabili o termini tecnici interni (es. non scrivere 'age_vs_level', "
    "scrivi 'eta' rispetto al livello di squadra'). "
)

_ROLES = {
    "cronista": (
        "Sei il Cronista. Raccogli i fatti grezzi disponibili su questo giocatore (squadra, ruolo, eta', "
        "fonti che lo citano). Se hai uno strumento di ricerca web, USALO per verificare la squadra "
        "ATTUALE del giocatore (cerca il nome + 'transfer'/'trasferimento'/'firma con' nell'anno corrente): "
        "il campo squadra qui sotto viene da Wikidata e puo' essere non aggiornato rispetto a un "
        "trasferimento reale gia' avvenuto. Se la ricerca conferma una squadra diversa da quella indicata, "
        "dillo esplicitamente ('SQUADRA AGGIORNATA: ...') e specifica se e' un cambio di livello reale "
        "(es. da prima squadra a squadra riserve/giovanile, o il contrario), non solo il nome nuovo; se la "
        "ricerca non trova nulla di piu' recente o non hai potuto cercare, dillo altrettanto esplicitamente, "
        "mai un silenzio su questo punto. Nessuna opinione, solo fatti, in italiano, conciso. " + _PLAIN_LANGUAGE_RULE
    ),
    "verificatore": "Sei il Verificatore. Controlla la coerenza del segnale nel report del Cronista: e' corroborato da piu' fonti indipendenti o da una sola? Il salto di menzioni sembra reale o rumore statistico? Rispondi in italiano, conciso. " + _PLAIN_LANGUAGE_RULE,
    "scettico": "Sei lo Scettico. Leggi i report precedenti e cerca il motivo per cui questo segnale potrebbe essere un falso positivo: nome comune/omonimia, contesto competitivo debole, dati insufficienti. Sii duro, in italiano, conciso. " + _PLAIN_LANGUAGE_RULE,
    "giudice": (
        'Sei il Giudice. Sintetizza i report precedenti in un verdetto finale in JSON RIGOROSO: '
        '{"vale_la_pena": true/false, "confidence": 0-100, "motivazione": "una riga", '
        '"club_aggiornato": "nome club se il Cronista ne ha confermato uno diverso via ricerca web, altrimenti null", '
        '"club_verificato_via_ricerca": true/false (true solo se il Cronista ha esplicitamente riportato un esito di ricerca web, anche se ha confermato lo stesso club)}. '
        'Nessun testo fuori dal JSON. ' + _PLAIN_LANGUAGE_RULE
    ),
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
    # pool vuota = nessuna chiave configurata o cataloghi irraggiungibili:
    # meglio l'errore esplicito di _call_with_fallback che un finto fallback
    # su un modello hardcodato (il vecchio default era un modello ":preview"
    # che OpenRouter ha gia' ritirato - falliva comunque, ma piu' confuso)
    return pool


def _grounded_cronista_pool() -> list[tuple]:
    """Solo il server tool nativo di OpenRouter (openrouter:web_search) sa
    davvero cercare sul web dentro la stessa chiamata - ne' l'endpoint
    OpenAI-compatibile di Gemini (verificato sulla doc ufficiale: grounding
    disponibile solo per generazione immagini, non per chat.completions) ne'
    NVIDIA NIM lo offrono. Per questo il Cronista prova prima ESCLUSIVAMENTE
    modelli OpenRouter con web_search=True, non l'intera pool a 3 provider -
    altrimenti Gemini (primo in _candidate_models per quota) risponderebbe
    per primo senza aver cercato nulla, e il dossier lo spaccerebbe per
    verificato quando non lo e'."""
    return [
        (lambda model, sp, um: call_openrouter(model, sp, um, web_search=True), m["id"])
        for m in get_available_models()[:5]
    ]


# Circuit breaker per-modello, valido per la durata di UNA scansione (reset a
# inizio refresh_radar). Il problema misurato: un modello in rate-limit tiene
# occupata la chiamata fino al timeout PER OGNI tentativo, e la catena di
# fallback lo riprovava daccapo per ogni ruolo di ogni dossier - con 8 dossier
# x 4 ruoli un modello morto veniva riprovato fino a 32 volte, ed era LUI a
# fare la differenza tra una scansione da 2 minuti e una da 8+. Dopo
# _MODEL_FAILURE_LIMIT fallimenti consecutivi il modello si salta per il resto
# del run; un successo azzera il contatore. Dietro lock: i dossier girano in
# parallelo (swarm_workers).
_MODEL_FAILURE_LIMIT = 2
_model_failures: dict[str, int] = {}
_model_failures_lock = threading.Lock()


def _reset_model_failures():
    with _model_failures_lock:
        _model_failures.clear()


def _model_blocked(model: str) -> bool:
    with _model_failures_lock:
        return _model_failures.get(model, 0) >= _MODEL_FAILURE_LIMIT


def _record_model_result(model: str, ok: bool):
    with _model_failures_lock:
        _model_failures[model] = 0 if ok else _model_failures.get(model, 0) + 1


def _call_with_fallback(model_pool: list[tuple], system_prompt: str, user_message: str):
    """I modelli gratuiti possono essere rate-limited in modo imprevedibile
    (verificato live: sia su OpenRouter con 429 per-modello e per-account,
    sia il bisogno di un secondo provider quando il primo e' esaurito per
    la giornata) - prova il prossimo candidato invece di far fallire subito
    l'intero dossier. Ritorna (risposta, call_fn, modello) cosi' il resto
    del dossier riusa lo stesso provider/modello che ha gia' risposto."""
    if not model_pool:
        # senza questa guardia una pool vuota finiva in `raise None` in fondo
        # (TypeError fuorviante nei log al posto della causa vera)
        raise RuntimeError(
            "Nessun modello AI disponibile: nessuna chiave API configurata "
            "(OPENROUTER_API_KEY/GEMINI_API_KEY/NVIDIA_API_KEY) o cataloghi irraggiungibili."
        )
    usable = [(fn, m) for fn, m in model_pool if not _model_blocked(m)]
    if not usable:
        raise RuntimeError(
            "Tutti i modelli disponibili hanno superato il limite di fallimenti "
            "consecutivi in questa scansione (rate limit dei provider free): "
            "dossier saltato invece di riprovare a vuoto fino al timeout."
        )
    last_error = None
    for call_fn, model in usable:
        try:
            response = call_fn(model, system_prompt, user_message)
        except Exception as e:
            _record_model_result(model, ok=False)
            last_error = e
            continue
        if _looks_like_tool_markup(response):
            # il modello ha emesso sintassi di chiamata-strumento come testo:
            # non e' una risposta, e' un fallimento - prova il prossimo
            _record_model_result(model, ok=False)
            last_error = RuntimeError(f"{model} ha risposto con markup di tool call, non testo")
            continue
        _record_model_result(model, ok=True)
        return response, call_fn, model
    raise last_error


# Nomi dei componenti in italiano semplice - mai le chiavi grezze nel
# contesto che va allo swarm, altrimenti il Giudice le ripete parola per
# parola nel suo verdetto (verificato dal vivo: "age_vs_level" comparso
# cosi' com'e' in una motivazione mostrata a Mirko).
_COMPONENT_LABELS_IT = {"age_vs_level": "eta' rispetto al livello di squadra", "buzz": "velocita' di menzione nelle fonti (buzz)"}

# _PLAIN_LANGUAGE_RULE e' un'istruzione testuale nel prompt, non una garanzia:
# verificato dal vivo che un modello free puo' ignorarla e ripetere comunque
# la chiave grezza vista nel context ("age_vs_level" ricomparso in un
# verdetto mostrato a Mirko nonostante il divieto esplicito). Una sostituzione
# deterministica sull'output e' l'unica vera rete di sicurezza.
_TECHNICAL_TERM_PATTERN = re.compile(
    "|".join(re.escape(k) for k in sorted(_COMPONENT_LABELS_IT, key=len, reverse=True)),
    re.IGNORECASE,
)


def _sanitize_technical_terms(text: str) -> str:
    if not text:
        return text
    return _TECHNICAL_TERM_PATTERN.sub(lambda m: _COMPONENT_LABELS_IT[m.group(0).lower()], text)


# Un modello free puo' "rispondere" emettendo la sintassi di una chiamata
# strumento come TESTO (verificato dal vivo: la voce dello Scettico mostrava
# parola per parola "<tool_call> <function=openrouter_web_search>..." sulla
# card di Leandro Santos). Non e' una risposta: e' il tentativo fallito di
# usare un tool che quel modello non ha. In generazione si tratta come
# chiamata fallita (si passa al modello successivo); in lettura, per i
# dossier gia' salvati, il testo viene sostituito da una nota onesta.
_TOOL_MARKUP_PATTERN = re.compile(
    r"<\s*/?\s*tool_call|<\s*/?\s*function[=\s>]|<\s*/?\s*parameter[=\s>]"
    r"|\[\s*/?\s*TOOL_CALL\s*\]|<\|tool_call\|>",
    re.IGNORECASE,
)

_AI_VOICE_UNAVAILABLE = (
    "voce non disponibile in questo giro: il modello AI ha risposto in un "
    "formato tecnico non valido invece che in italiano."
)


def _looks_like_tool_markup(text) -> bool:
    return isinstance(text, str) and bool(_TOOL_MARKUP_PATTERN.search(text))


def _reject_tool_markup(text: str) -> str:
    return _AI_VOICE_UNAVAILABLE if _looks_like_tool_markup(text) else text


def run_swarm_dossier(candidate: dict, score_result: dict) -> dict:
    # INVARIANTE: questa funzione e' LINGUA-AGNOSTICA per design. Genera UN
    # SOLO dossier per candidato per scansione, sempre in italiano (i ruoli
    # in _ROLES sono prompt italiani) - la scelta IT/EN dell'interfaccia
    # (vedi translations.py, visual_council_app.py:_resolve_lang) e' solo
    # rendering lato server, non tocca mai lo swarm.
    # Se un giorno si vuole un dossier bilingue: tradurre il testo GIA'
    # generato con UNA chiamata leggera (o lato client), MAI ririlanciare
    # Cronista/Verificatore/Scettico/Giudice una volta per lingua - vedi la
    # guardia anti-doppione in refresh_radar (blocca prima di spendere la
    # chiamata, non dopo). Deciso con Mirko 2026-07 proprio per non bruciare
    # le quote AI free raddoppiandole silenziosamente col bilinguismo.
    model_pool = _candidate_models()
    component_names = [_COMPONENT_LABELS_IT.get(k, k) for k in score_result.get("components", {})]
    context = (
        f"Giocatore: {candidate['name']}\nSquadra: {candidate.get('club', 'N/D')}\n"
        f"Tier competizione: {candidate.get('tier', 'N/D')}\n"
        f"Signal Score: {score_result.get('signal_score', 'N/D')}\n"
        f"Componenti disponibili: {', '.join(component_names) if component_names else 'nessuno'}"
    )

    # Il Cronista prova prima la pool con ricerca web reale (solo OpenRouter
    # la supporta): se quella e' irraggiungibile (nessuna chiave, rate limit
    # su tutti i modelli), retrocede alla pool normale senza ricerca invece
    # di far fallire l'intero dossier - ma "grounded" resta False, cosi' il
    # resto del dossier non spaccia per verificata un'informazione che non
    # lo e'. I ruoli successivi riusano la stessa coppia provider/modello
    # del Cronista per coerenza nel dossier.
    try:
        cronista, call_fn, model = _call_with_fallback(_grounded_cronista_pool(), _ROLES["cronista"], context)
        grounded = True
    except Exception:
        cronista, call_fn, model = _call_with_fallback(model_pool, _ROLES["cronista"], context)
        grounded = False
    # _reject_tool_markup su OGNI voce: i ruoli dopo il Cronista riusano lo
    # stesso modello senza ripassare dal fallback, quindi un modello che
    # "risponde" con sintassi di tool call va intercettato anche qui - la
    # voce diventa una nota onesta, mai markup mostrato sulla card
    cronista = _sanitize_technical_terms(_reject_tool_markup(cronista))
    verificatore = _sanitize_technical_terms(_reject_tool_markup(
        call_fn(model, _ROLES["verificatore"], f"{context}\n\nReport Cronista:\n{cronista}")
    ))
    scettico = _sanitize_technical_terms(_reject_tool_markup(call_fn(
        model, _ROLES["scettico"],
        f"{context}\n\nReport Cronista:\n{cronista}\n\nReport Verificatore:\n{verificatore}",
    )))
    giudice_raw = _sanitize_technical_terms(_reject_tool_markup(call_fn(
        model, _ROLES["giudice"],
        f"Cronista:\n{cronista}\n\nVerificatore:\n{verificatore}\n\nScettico:\n{scettico}",
    )))
    try:
        giudice = json.loads(giudice_raw.replace("```json", "").replace("```", "").strip())
    except Exception:
        giudice = {
            "vale_la_pena": None, "confidence": None, "motivazione": giudice_raw[:200],
            "club_aggiornato": None, "club_verificato_via_ricerca": False,
        }

    return {
        "generated_at": _now_iso(),
        "signal_score_at_generation": score_result.get("signal_score"),
        "model": model,
        "provider": {call_gemini: "gemini", call_nvidia: "nvidia"}.get(call_fn, "openrouter"),
        # True solo se il tool di ricerca web era disponibile al Cronista in
        # questa chiamata - il modello decide da se' se e quanto cercare
        # (server tool OpenRouter), quindi non garantisce che una ricerca sia
        # avvenuta per davvero: quel dettaglio sta in
        # giudice.club_verificato_via_ricerca, letto dal report del Cronista.
        "web_search_tool_available": grounded,
        "cronista": cronista,
        "verificatore": verificatore,
        "scettico": scettico,
        "giudice": giudice,
    }


# ============================================================
# ORCHESTRATORE
# ============================================================

def _build_buzz_pool(watchlist: list[dict], rest_sorted: list[dict],
                     feed: dict, pool_size: int) -> list[dict]:
    """Chi entra nel giro dei controlli stampa di questo run.

    BUG TROVATO E CORRETTO (verificato sui dati live 2026-07): il pool era
    solo watchlist + i primi N per punteggio-eta'. Ma la testa di quella
    classifica e' occupata dalle centinaia di candidati saturi a 1.0 (solo
    eta', zero riscontri - il segmento che il funnel dossier giustamente
    SALTA), mentre i giocatori che vincono davvero il dossier e compaiono
    nel TURNO (age score alto ma non saturo) restavano fuori dal pool: mai
    un controllo stampa, mai uno snapshot buzz, quindi curva perennemente
    assente proprio sulle card che l'utente guarda.

    Regola: i CASI ATTIVI (chi ha gia' un dossier AI vero nel feed) hanno il
    posto garantito nel pool - sono i giocatori sotto revisione umana, il
    loro segnale stampa va tenuto aggiornato. I posti a classifica-eta'
    restano per scoprire candidati nuovi. Il pool cresce al massimo di
    ~top_n posti (i dossier per run sono cappati), quindi resta bounded."""
    active_ids = {
        cid for cid, rec in feed.items()
        if isinstance(rec, dict) and isinstance(rec.get("dossier"), dict)
        and "giudice" in rec["dossier"]
    }
    active = [c for c in rest_sorted if c["candidate_id"] in active_ids]
    rest = [c for c in rest_sorted if c["candidate_id"] not in active_ids]
    return watchlist + active + rest[:pool_size]


def refresh_radar(profile_key: str = "tactical_profile", progress_cb=None) -> dict:
    """progress_cb(stage, done=None, total=None, feed_ready=None) e' opzionale:
    riceve lo stato leggibile della scansione man mano che avanza, cosi' chi
    aspetta da telefono vede 'dossier 3/8' e non un contatore muto di secondi
    (verificato dal vivo che a 4 minuti di contatore nudo l'attesa si legge
    come 'si e' rotto'). feed_ready=True segnala che i punteggi sono GIA'
    salvati e consultabili anche se i dossier AI stanno ancora arrivando."""
    def _progress(stage, **extra):
        if progress_cb is None:
            return
        try:
            progress_cb(stage, **extra)
        except Exception:
            pass  # il progresso e' cosmetico: mai far fallire la scansione per lui

    cfg = load_config()
    _reset_model_failures()  # il circuit breaker sui modelli vale per UNA scansione
    _progress("leggo lo storico")
    history = _load_json(BUZZ_HISTORY_FILE)
    feed = _load_json(FEED_FILE)
    observations = _load_json(OBSERVATIONS_FILE)

    _progress("raccolgo i candidati dalle fonti (Wikidata/Wikipedia)")
    candidates = fetch_candidate_pool(cfg)

    # Grafo delle fonti: i lettori EMETTONO osservazioni (non sovrascrivono),
    # poi il risolutore decide il club corrente per ciascun candidato - e' lui
    # che alimenta la query buzz, non il fetch grezzo. Vedi la sezione GRAFO
    # DELLE FONTI in alto per il perche' (audit staleness 2026-07).
    _progress("aggiorno il grafo delle fonti")
    _READER_FONTE = {"wikidata": "wikidata", "wikipedia": "wikipedia_torneo"}
    for c in candidates:
        fonte = _READER_FONTE.get(c.get("source"))
        if fonte and c.get("club"):
            record_observation(observations, c["candidate_id"], "club", c["club"], fonte, cfg)
    for c in candidates:
        resolution = resolve_field(observations, c["candidate_id"], "club", cfg,
                                   fallback=c.get("club"))
        if resolution:
            c["club_risolto"] = resolution["valore"]
            c["club_provenienza"] = resolution
            if resolution["conflitto"] and resolution.get("alternativa"):
                c["club_alternativo"] = resolution["alternativa"]

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
    buzz_pool = _build_buzz_pool(watchlist, rest_sorted, feed, perf["buzz_check_pool_size"])

    # Stage 2: buzz score in parallelo, solo sul sottoinsieme selezionato
    _progress(f"controllo l'attenzione stampa su {len(buzz_pool)} candidati (pool: {len(candidates)})")
    buzz_results = {}
    with ThreadPoolExecutor(max_workers=perf["buzz_check_workers"]) as executor:
        futures = {executor.submit(buzz_score, c, history, cfg): c for c in buzz_pool}
        for future in as_completed(futures):
            c = futures[future]
            _progress("controllo attenzione stampa", done=len(buzz_results) + 1, total=len(buzz_pool))
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
            # Layer E: posizione sulla curva di adozione, calcolata SOLO per
            # chi ha uno snapshot fresco in questo run - mai una fase stimata
            # su dati non raccolti oggi
            sres["curve"] = adoption_curve_assessment(candidate["candidate_id"], history, cfg)

        if sres["excluded"]:
            continue
        fres = fit_score(candidate, sres, profile_key, cfg)
        if fres is None:
            continue
        ranked.append({"candidate": candidate, "signal": sres, "fit": fres})

    ranked.sort(key=lambda r: r["fit"]["fit_score"], reverse=True)

    # ============================================================
    # FASE 1 - punteggi subito nel feed (persistenza append-only)
    # ============================================================
    # Lo storico punteggi/curva/ledger si scrive e si salva PRIMA di generare
    # i dossier AI: i dossier sono di gran lunga la parte piu' lenta della
    # scansione (minuti, con fallback multi-provider), e non c'e' motivo di
    # tenere in ostaggio punteggi gia' pronti dietro di loro. Da telefono
    # significa: feed consultabile dopo ~1 minuto, dossier che arrivano
    # dopo, ognuno gia' protetto dal salvataggio incrementale.
    run_at = _now_iso()
    # il ledger di validazione si carica UNA volta qui e si salva UNA volta
    # (vedi commento su _record_curve_crossing): con Postgres ogni load/save
    # e' un round-trip di rete, farne due per candidato non scala
    ledger = _load_json(CURVE_VALIDATION_FILE)
    ledger_changed = False
    for entry in ranked:
        cid = entry["candidate"]["candidate_id"]
        record = feed.setdefault(cid, {"identity": entry["candidate"], "history": []})

        # stato PRIMA di questo run - serve alla sonda di cambiamento per
        # sapere cosa confrontare, va catturato prima di sovrascrivere nulla;
        # appeso all'entry perche' la sonda gira in fase 2, a dossier pronto
        entry["_record"] = record
        entry["_previous_last_entry"] = record["history"][-1] if record["history"] else None
        entry["_previous_dossier"] = record.get("dossier")

        record["identity"] = entry["candidate"]
        # provenienza del club dal risolutore del grafo: la card puo' dire
        # "secondo chi, da quando" invece di presentare un club nudo - e un
        # disaccordo tra fonti resta visibile invece di sparire nell'identity
        if entry["candidate"].get("club_provenienza"):
            record["club_provenienza"] = entry["candidate"]["club_provenienza"]
        record["history"].append(
            {
                "run_at": run_at,
                "signal_score": entry["signal"]["signal_score"],
                "components": entry["signal"]["components"],
                "partial_data": entry["signal"]["partial_data"],
                "fit_score": entry["fit"]["fit_score"],
                "profile_used": profile_key,
                "curve": entry["signal"].get("curve"),
            }
        )
        # bound alla crescita, come gia' per buzz_history (runs[-20:]): la
        # history serve a Kalman/CUSUM/trail, che convergono ben prima di 30
        # osservazioni - senza tetto il feed cresce di ~un'entry a candidato
        # PER OGNI scansione (pool in migliaia) e il JSONB monolitico su
        # Postgres viene riscritto per intero a ogni salvataggio incrementale.
        # Gli esiti di lungo periodo NON si perdono: vivono nel ledger di
        # validazione (curve_validation), che e' append-only per davvero.
        record["history"] = record["history"][-30:]

        # validazione retroattiva (Layer E): il crossing e' il momento della
        # verita' - si registra SEMPRE quando la fase 4 scatta, per qualunque
        # candidato con snapshot fresco, indipendentemente da chi ha vinto il
        # posto nel turno di revisione
        curve_phase = (entry["signal"].get("curve") or {}).get("phase")
        if curve_phase == 4:
            ledger_changed = _record_curve_crossing(ledger, record, entry["candidate"], run_at) or ledger_changed
        # tabellone precisione: apre/chiude la scommessa "sta per esplodere"
        # per ogni candidato con una fase fresca questo run (esploso vs
        # sgonfiato) - e' cio' che rende il rilevatore falsificabile sui fatti
        if curve_phase is not None:
            ledger_changed = _update_flag_ledger(ledger, entry["candidate"], curve_phase, run_at) or ledger_changed

        # stato provvisorio SENZA dossier: le finestre aperte si portano
        # avanti o si chiudono gia' ora (niente sparisce in silenzio nel
        # frattempo); per chi ricevera' un dossier fresco in fase 2 lo stato
        # viene ricalcolato con il giudice alla mano, come sempre
        record["history"][-1]["state_change"] = _carry_or_close(
            entry["_previous_last_entry"], None, entry["signal"].get("curve"))

    _progress("salvo i punteggi (gia' consultabili)")
    _save_json(FEED_FILE, feed)
    _save_json(BUZZ_HISTORY_FILE, history)
    _save_json(OBSERVATIONS_FILE, observations)
    if ledger_changed:
        _save_json(CURVE_VALIDATION_FILE, ledger)
    _progress("punteggi pronti; genero i dossier AI", feed_ready=True)

    # ============================================================
    # FASE 2 - dossier AI (la parte lenta), con finalizzazione incrementale
    # ============================================================
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

    # Un candidato in fase "decollo imminente" (Layer E) compra SEMPRE un
    # posto nella finestra swarm, anche fuori dal top_n del fit score: e' il
    # caso per cui il radar esiste, e lasciarlo in archivio silenzioso
    # perche' il suo punteggio contestuale non era tra i primi 15 sarebbe il
    # falso negativo peggiore possibile per lo scopo dichiarato.
    swarm_window = swarm_candidates[:top_n]
    for e in swarm_candidates[top_n:]:
        if (e["signal"].get("curve") or {}).get("phase") == 3:
            swarm_window.append(e)

    # Misurato dal vivo: un ciclo sequenziale su top_n=15 (4 chiamate AI
    # ciascuno) ha superato i 9 minuti senza finire, troncato da Cloud Run
    # con un 503. I dossier di candidati DIVERSI sono indipendenti tra loro
    # (solo le 4 chiamate DENTRO un dossier devono restare in ordine, per
    # coerenza Cronista->Giudice) - si parallelizza a livello di candidato,
    # non dentro il singolo dossier.
    #
    # GUARDIA ANTI-DOPPIONE: un candidate_id non deve mai finire in
    # to_generate due volte nello stesso turno - oggi non puo' succedere
    # (fetch_candidate_pool dedup, un solo entry per candidato in ranked),
    # ma e' esattamente il tipo di bug silenzioso che un futuro dossier
    # bilingue introdurrebbe (es. un ciclo "per ogni lingua" che ri-aggiunge
    # lo stesso candidato). Si blocca QUI, prima di spendere una sola
    # chiamata AI, non dopo - vedi anche l'invariante in run_swarm_dossier.
    _assert_no_duplicate_candidate_ids(
        [e["candidate"]["candidate_id"] for e in swarm_window], "finestra swarm")
    to_generate = []
    for entry in swarm_window:
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

    for entry in ranked:
        if "dossier" not in entry and _needs_more_signal(entry["signal"]):
            entry["dossier"] = {
                "skipped": "Segnale singolo e gia' al tetto (es. solo eta'-relativa, senza buzz a corroborare): "
                           "serve un altro segnale prima di spendere un dossier AI, non solo un numero alto."
            }

    def _finalize_dossier(entry):
        """Attacca il dossier al record e ricalcola lo stato del turno con il
        giudice fresco alla mano. La sonda di cambiamento gira solo sui
        candidati con un dossier AI vero (stesso sottoinsieme stretto del
        funnel, mai sull'intera pool): un dossier "skipped"/"error" non ha un
        giudice da confrontare, quindi non genera un caso da rivedere."""
        record = entry["_record"]
        dossier = entry["dossier"]
        has_real_dossier = "giudice" in dossier
        if not has_real_dossier:
            # errore o skip in QUESTO giro: se il record ha gia' un dossier
            # vero di un giro precedente, non lo si distrugge sostituendolo
            # con una nota d'errore - il verdetto vecchio (datato, il
            # generated_at lo dice) informa piu' di un "non disponibile"
            if isinstance(record.get("dossier"), dict) and "giudice" in record["dossier"]:
                return
            record["dossier"] = dossier
            return
        record["dossier"] = dossier
        # il club scoperto dal Cronista via ricerca web entra nel GRAFO come
        # osservazione fonte=news, datata a oggi: prima era solo un avviso
        # usa-e-getta (CLUB DA CORREGGERE) che moriva alla riscrittura
        # successiva da Wikidata - ora e' agli atti, e il risolutore lo fa
        # vincere sui claim non datati gia' dal prossimo run (query buzz
        # compresa)
        club_aggiornato = (dossier.get("giudice") or {}).get("club_aggiornato")
        if club_aggiornato:
            cid = entry["candidate"]["candidate_id"]
            if record_observation(observations, cid, "club", club_aggiornato,
                                  "news", cfg, datato_al=run_at[:10],
                                  nota="Cronista via ricerca web"):
                record["club_provenienza"] = resolve_field(observations, cid, "club", cfg)
        bayes = bayesian_estimate(record["history"], cfg)
        z = (bayes or {}).get("last_innovation_z")
        cusum_state = record.get("cusum", {"pos": 0.0, "neg": 0.0})
        if z is not None:
            cusum_state = _update_cusum(cusum_state, z, cfg)
        record["cusum"] = cusum_state
        fresh_change = detect_state_change(
            candidate=entry["candidate"],
            previous_last_entry=entry["_previous_last_entry"],
            previous_dossier=entry["_previous_dossier"],
            current_dossier=dossier,
            current_partial_data=entry["signal"]["partial_data"],
            bayes=bayes,
            cusum_state=cusum_state,
            cfg=cfg,
            buzz_detail=entry["signal"].get("buzz_detail"),
            curve=entry["signal"].get("curve"),
        )
        # niente sparisce in silenzio: una finestra aperta (sta per
        # esplodere) resta finche' non si risolve, e quando si risolve si
        # mostra la chiusura una volta, spiegata - non un giocatore che
        # svanisce senza motivo (che l'utente medio legge come un bug)
        record["history"][-1]["state_change"] = _carry_or_close(
            entry["_previous_last_entry"], fresh_change, entry["signal"].get("curve"))

    # dossier riusati e note di skip: zero rete, si finalizzano in blocco
    # (per i riusati la sonda gira comunque - takeoff/finestre/shock non
    # dipendono dal dossier nuovo)
    for entry in ranked:
        if "dossier" in entry:
            _finalize_dossier(entry)

    generated = 0
    if to_generate:
        _progress("dossier AI", done=0, total=len(to_generate))
    # seconda guardia (difesa in profondita'): anche se to_generate e' gia'
    # garantito senza doppioni dal controllo sopra, qui si blocca ESPLICITO
    # prima di sottomettere la chiamata AI - non nel loop as_completed dopo,
    # che scoprirebbe il doppione solo a chiamata gia' pagata/consumata.
    _assert_no_duplicate_candidate_ids(
        [e["candidate"]["candidate_id"] for e in to_generate], "sottomissione executor")
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
            _finalize_dossier(entry)
            generated += 1
            _progress("dossier AI", done=generated, total=len(to_generate))
            # salvataggio incrementale dopo ogni dossier AI (la parte lenta e
            # costosa): protegge il lavoro gia' fatto da un crash/timeout a
            # meta' turno - un riavvio del container non deve buttare via i
            # dossier gia' generati. Solo qui, non per i dossier riusati:
            # quelli sono gia' su disco/DB dal giro che li ha generati.
            _save_json(FEED_FILE, feed)

    _progress("salvataggio finale")
    _save_json(FEED_FILE, feed)
    _save_json(OBSERVATIONS_FILE, observations)

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
                "bayesian": bayesian_estimate(feed[e["candidate"]["candidate_id"]]["history"], cfg),
            }
            for e in ranked
        ],
    }


def _sanitize_dossier(dossier: dict) -> dict:
    """Il dossier e' persistito e riusato tal quale finche' il Signal Score
    non si sposta oltre rerun_threshold_points (vedi refresh_radar) - quindi
    sanificare solo all'atto della generazione non basta: un dossier scritto
    PRIMA di questo fix (o da un modello che ha comunque ignorato la regola)
    resta a leak nel file finche' il punteggio non cambia abbastanza da
    giustificare un nuovo dossier, il che puo' non succedere mai. Sanificare
    anche in lettura garantisce che sia sempre pulito, indipendentemente da
    quando il testo e' stato scritto."""
    if not dossier:
        return dossier
    for key in ("cronista", "verificatore", "scettico"):
        if dossier.get(key):
            dossier[key] = _sanitize_technical_terms(_reject_tool_markup(dossier[key]))
    giudice = dossier.get("giudice")
    if isinstance(giudice, dict) and giudice.get("motivazione"):
        giudice["motivazione"] = _sanitize_technical_terms(
            _reject_tool_markup(giudice["motivazione"]))
    return dossier


def latest_feed() -> dict:
    feed = _load_json(FEED_FILE)
    for record in feed.values():
        if record.get("dossier"):
            _sanitize_dossier(record["dossier"])
    return feed


# ============================================================
# WATCHLIST - candidati segnati a mano da uno schermo (scheda giocatore),
# non dal file di config statico. Distinta da candidate_sources.manual_
# watchlist in radar_config.yaml (quella e' curata editando YAML, pensata
# per Mirko; questa e' un tocco su una card, persistito, pensata per
# chiunque usi il tool - stesso concetto, meccanismo diverso apposta).
# ============================================================

def get_watchlist() -> set:
    return set(_load_json(WATCHLIST_FILE).get("candidate_ids", []))


def set_watchlisted(candidate_id: str, watchlisted: bool) -> set:
    data = _load_json(WATCHLIST_FILE)
    ids = set(data.get("candidate_ids", []))
    if watchlisted:
        ids.add(candidate_id)
    else:
        ids.discard(candidate_id)
    _save_json(WATCHLIST_FILE, {"candidate_ids": sorted(ids)})
    return ids


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
