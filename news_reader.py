"""Lettore "news" del grafo delle fonti: ricava il club corrente dai TITOLI
Google News che il buzz check gia' scarica a ogni run, senza AI e senza tool
di ricerca a pagamento.

PERCHE' ESISTE
--------------
Il club aggiornato veniva scoperto solo dal Cronista dello swarm, tramite il
server tool `openrouter:web_search`. Tre problemi misurati, tutti strutturali:

1. quel tool e' FATTURATO A PARTE anche sui modelli ":free" (~$0.005 a
   richiesta) - il modello e' gratis, la ricerca no;
2. il tier free di OpenRouter e' a 50 richieste/giorno sotto i $10 di credito
   storico: a 8 dossier per scansione bastano sei scansioni per esaurirlo, e
   il sistema retrocede in silenzio a grounded=False;
3. anche quando funziona, il risultato e' la PAROLA di un modello su cosa
   dice di aver cercato. `web_search_tool_available` lo ammette gia' nel suo
   commento: sapere che il tool era disponibile non dice che la ricerca sia
   avvenuta.

La ricerca del club non ha pero' bisogno di un LLM: ha bisogno di una query e
di un parser. La query c'e' gia' (buzz_score interroga Google News RSS per
ogni candidato della pool, a ogni run) e le risposte contengono gia' titolo,
testata e data. Qui si legge quel materiale e si emette un'OSSERVAZIONE nel
grafo a livello `news` (2) - il livello che radar_config.yaml aveva gia'
previsto ("stampa via ricerca web, la piu' fresca che abbiamo") e che finora
nessun lettore alimentava: _READER_FONTE copriva solo wikidata e wikipedia.

Il risolutore fa il resto senza modifiche: `club` e' un campo `dal_basso`, e
un'osservazione DATATA batte i claim Wikidata senza data.

DISCIPLINA (la stessa del resto del motore: mai un dato inventato)
------------------------------------------------------------------
- **Vocabolario chiuso.** Un club viene riconosciuto solo se compare nel
  lessico costruito dalla pool candidati reale. Non si estrae mai un nome di
  club dal testo libero: cosi' il lettore puo' non vedere un trasferimento
  (falso negativo, accettabile) ma non puo' inventarne uno (falso positivo,
  inaccettabile - finirebbe nel grafo come fatto datato).
- **Serve un indizio esplicito di trasferimento.** Nessun verbo di
  trasferimento nel titolo = nessuna osservazione. Un titolo che nomina un
  club puo' nominarlo per mille motivi (avversario, ex squadra, stadio).
- **Il club deve stare DOPO il verbo.** In "lascia il Palermo per il Bari" il
  club di destinazione segue l'indizio; prenderlo a caso invertirebbe il
  trasferimento. Se dopo il verbo non c'e' nessun club noto, si tace.
- **Il club attuale non genera osservazioni.** Un titolo che conferma dove
  gia' sappiamo che gioca non e' una notizia di trasferimento.

Ogni osservazione emessa porta con se' data (dal pubDate RSS), URL e la nota
della testata: sulla card resta verificabile riga per riga, che e' il punto.
"""
import re
import unicodedata
from email.utils import parsedate_to_datetime

# Un club piu' corto di questo non entra nel lessico: sigle e nomi brevi
# ("Roma", "Bari", "Lens") collidono con parole comuni e nomi di citta' nei
# titoli, e un falso positivo qui entra nel grafo come fatto datato. Meglio
# perdere il match che sporcare la provenienza.
_MIN_CLUB_LEN = 5

# Indizi di trasferimento. Multilingua perche' la stampa locale - quella che
# per il two-step flow arriva PER PRIMA, cioe' esattamente quella che interessa
# al radar - scrive nella sua lingua anche quando Google News risponde in
# inglese. Ordinati per specificita': si usa il primo che compare nel titolo.
_TRANSFER_CUES = [
    # inglese
    r"completes?\s+(?:a\s+)?(?:permanent\s+|loan\s+)?move\s+to",
    r"set\s+to\s+join", r"agrees?\s+(?:to\s+)?(?:a\s+)?(?:deal|terms)\s+with",
    r"signs?\s+(?:for|with)", r"joins?", r"moves?\s+to",
    r"on\s+loan\s+(?:at|to)", r"loaned?\s+to", r"transferred?\s+to",
    r"new\s+signing\s+(?:for|at)", r"unveiled\s+(?:by|at)",
    # italiano
    r"passa\s+a[lieo]?", r"firma\s+(?:con|per|il)", r"si\s+trasferisce\s+a[lieo]?",
    r"in\s+prestito\s+a[lieo]?", r"ceduto\s+a[lieo]?", r"acquistato\s+da[lieo]?",
    r"nuovo\s+giocatore\s+de[lieo]",
    # spagnolo
    r"ficha\s+por", r"se\s+une\s+a[l]?", r"cedido\s+a[l]?",
    r"nuevo\s+jugador\s+de[l]?", r"refuerzo\s+de[l]?",
    # portoghese
    r"assina\s+(?:com|pelo|pela)", r"contratado\s+pel[oa]", r"refor[cç]o\s+d[oa]",
    r"emprestado\s+a[o]?", r"transfer[ie]do\s+para",
]

_TRANSFER_RE = re.compile("|".join(f"(?:{p})" for p in _TRANSFER_CUES), re.IGNORECASE)


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text)
                   if not unicodedata.combining(c))


def normalize_club(name: str) -> str:
    """Chiave di confronto tra nomi di club. Toglie accenti, punteggiatura e
    doppi spazi, ma NON i prefissi societari (FC/AC/CD/SS...): "Milan" e "AC
    Milan" restano chiavi diverse di proposito - la disambiguazione tra prima
    squadra e riserve ("Juventus" vs "Juventus Next Gen") e' esattamente la
    differenza che il radar non puo' permettersi di appiattire."""
    cleaned = _strip_accents((name or "").lower())
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def build_club_lexicon(candidates: list[dict],
                       observations: dict | None = None) -> dict[str, str]:
    """Vocabolario chiuso dei club riconoscibili. chiave normalizzata -> nome
    canonico.

    Due sorgenti, ed entrambe servono:

    - la POOL corrente (Wikidata + Wikipedia): i club dove i candidati
      giocano ORA. Costruirlo da qui e non da una lista scritta a mano
      significa che cresce da solo quando si aggiunge una lega o un paese in
      radar_config.yaml, senza codice da toccare.
    - il GRAFO delle osservazioni, cioe' ogni club mai osservato per
      chiunque, anche in run passati.

    La seconda sorgente non e' un di piu': un trasferimento porta quasi
    sempre verso un club che NON e' nella pool dei candidati - e' il senso
    stesso del radar, il ragazzo sale di livello. Un lessico limitato alla
    pool corrente sarebbe cieco proprio sui trasferimenti che contano di
    piu'. Accumulando dal grafo il vocabolario si allarga a ogni run, e la
    copertura cresce da sola con l'uso.

    Resta comunque un vocabolario CHIUSO: un club mai visto da nessuna parte
    non viene riconosciuto. E' un falso negativo consapevole - preferibile a
    un club inventato che entrerebbe nel grafo come fatto datato."""
    lexicon: dict[str, str] = {}

    def _add(raw: str):
        raw = (raw or "").strip()
        if not raw or len(raw) < _MIN_CLUB_LEN:
            return
        norm = normalize_club(raw)
        if len(norm) < _MIN_CLUB_LEN:
            return
        # il nome piu' lungo vince come canonico: "Juventus Next Gen" e'
        # piu' informativo di "Juventus" per la stessa chiave normalizzata
        if norm not in lexicon or len(raw) > len(lexicon[norm]):
            lexicon[norm] = raw

    for c in candidates:
        for key in ("club_risolto", "club", "club_alternativo"):
            _add(c.get(key))

    for per_campo in (observations or {}).values():
        for obs in (per_campo or {}).get("club") or []:
            _add(obs.get("valore"))

    return lexicon


def _title_without_publisher(title: str) -> str:
    """Google News accoda la testata al titolo ("Headline - Nome Testata").
    Va tolta prima di cercare club: una testata come "Milan News" farebbe
    scattare un match sul club sbagliato a ogni singolo titolo."""
    return title.rsplit(" - ", 1)[0].strip() if " - " in title else title.strip()


def _parse_pubdate(raw: str) -> str | None:
    """pubDate RSS ("Mon, 01 Jul 2026 10:00:00 GMT") -> 'YYYY-MM-DD'.
    None se illeggibile: meglio un'osservazione senza data (che il risolutore
    tratta come piu' debole) che una data inventata."""
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError):
        return None


def _find_clubs_after(text: str, start: int, lexicon: dict[str, str]) -> list[str]:
    """Club del lessico che compaiono nel testo a partire da `start`, in
    ordine di apparizione. Match su confine di parola sul testo normalizzato:
    "Cerezo Osaka" non deve matchare dentro un'altra parola."""
    norm_text = normalize_club(text)
    # la normalizzazione puo' spostare gli indici (punteggiatura -> spazio):
    # si normalizza anche il prefisso per riportare `start` sulla stessa scala
    norm_start = len(normalize_club(text[:start]))
    found = []
    for norm_club, canonical in lexicon.items():
        for m in re.finditer(rf"\b{re.escape(norm_club)}\b", norm_text):
            if m.start() >= norm_start:
                found.append((m.start(), canonical))
                break
    return [c for _, c in sorted(found)]


def extract_club_observations(news_items: list[dict], known_clubs: set[str],
                              lexicon: dict[str, str]) -> list[dict]:
    """Osservazioni di club deducibili dai titoli, in ordine di apparizione.

    news_items: gli item grezzi di search_google_news (title/url/date).
    known_clubs: i club gia' noti per QUESTO candidato (risolto + alternativo)
                 - un titolo che li conferma non e' una notizia di
                 trasferimento e non genera osservazioni.

    Ritorna dict pronti per record_observation: valore, datato_al, url, nota.
    Lista vuota = nessun indizio abbastanza solido, che e' l'esito corretto
    nella grande maggioranza dei titoli.
    """
    known_norm = {normalize_club(c) for c in known_clubs if c}
    out = []
    seen = set()
    for item in news_items:
        raw_title = (item.get("title") or "").strip()
        if not raw_title:
            continue
        headline = _title_without_publisher(raw_title)
        cue = _TRANSFER_RE.search(headline)
        if not cue:
            continue  # nessun indizio di trasferimento: si tace
        for club in _find_clubs_after(headline, cue.end(), lexicon):
            if normalize_club(club) in known_norm:
                continue  # conferma di dove gia' sappiamo che gioca
            if club in seen:
                continue
            seen.add(club)
            publisher = raw_title.rsplit(" - ", 1)[-1].strip() if " - " in raw_title else ""
            out.append({
                "valore": club,
                "datato_al": _parse_pubdate(item.get("date")),
                "url": item.get("url"),
                "nota": f"titolo stampa: \"{headline[:120]}\"" + (f" ({publisher})" if publisher else ""),
            })
            break  # un solo club per titolo: il primo dopo il verbo e' la destinazione
    return out
