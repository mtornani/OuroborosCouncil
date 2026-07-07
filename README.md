# 🛰️ SENTINEL — OB1 Radar

> **Trova giovani calciatori prima che diventino nomi noti.**
> Non è un Wyscout più economico: è il layer che sta *a monte*.

SENTINEL non misura quanto è bravo un giocatore — per quello esistono già i
fornitori di dati evento (Wyscout, Instat, StatsBomb) e l'occhio di uno scout.
SENTINEL misura **quando l'attenzione su un giocatore inizia a muoversi**, dalla
stampa di nicchia verso quella mainstream, e prova a segnalarlo *prima* che
diventi notizia — nella finestra in cui costa ancora poco e la concorrenza è
bassa. È lo stesso pattern con cui nomi come Gilberto Mora o Neiser Villarreal
erano leggibili in anticipo: la stampa locale sapeva prima.

In una frase: **un prioritizzatore di attenzione, non un motore di previsione.**
Ti dice *su chi* puntare l'occhio umano questa settimana. La qualità la decidi tu.

---

## Cosa fa, in concreto

Interfaccia solo-mobile, pensata per essere letta in due secondi, con una sola
mano, anche al sole. Quattro schermate:

| Rotta | Nome | A cosa serve |
|-------|------|--------------|
| `/turno` | **IL TURNO** | Un caso alla volta: solo i giocatori su cui è cambiato qualcosa o che hanno una finestra ancora aperta. Finito l'ultimo, hai finito. |
| `/mappa` | **LA MAPPA** | Colpo d'occhio d'insieme: ogni giocatore un pallino sulla curva "da sconosciuto a conosciuto", con la zona calda in evidenza. Tocca una tappa per la lista completa. |
| `/processo` | **L'AVVOCATO DEL DIAVOLO** | Il sistema messo sotto processo dai suoi stessi numeri: precisione e richiamo (fallimenti compresi) + le obiezioni più dure con risposta onesta. |
| `/radar` | **ARCHIVIO** | Tutti i candidati filtrabili per profilo/ruolo/età/paese, con la mini-curva e il dossier per scheda. |

Ogni scheda giocatore porta con sé:
- il suo **percorso** sulla curva di adozione (dove sta: *nessuno ne parla →
  solo fonti locali → se ne parla → sta per esplodere → sui grandi giornali →
  lo sanno tutti*);
- il **verdetto** dello swarm di AI;
- **il contraddittorio**: le ragioni oggettive per dubitare di *quel* segnale,
  calcolate dai suoi dati (non dall'AI, così non si possono inventare).

---

## L'idea di fondo

La scommessa è a favore fin dalla partenza, per due fatti (non per una legge
della fisica):

1. **L'universo misurato si espande di continuo.** Ogni anno più leghe coperte,
   più giovani finiscono nei database. La frontiera della misurazione scende.
2. **Nel segmento già misurato e condiviso, il vantaggio decade a zero** — tutti
   vedono lo stesso dato nello stesso istante (arbitraggio dell'informazione).

Quindi l'unico vantaggio durevole è **alla frontiera**, nel non-ancora-misurato.
E chi allarga la frontiera (Wyscout & co.) non è un concorrente: è l'**orologio**
che fa maturare le scommesse di SENTINEL. Ogni volta che un nome ignoto diventa
misurato, è una segnalazione che si chiude.

Base teorica consolidata, non inventata qui: **curva di diffusione a S**
(Rogers/Bass — la massima accelerazione precede il punto di flesso) e
**two-step flow** (la notizia scala dalla stampa di nicchia a quella generalista
un gradino per volta — la scalata dei tier delle fonti è il preavviso).

---

## Come si costruisce il punteggio (i cinque layer)

Backend deliberatamente leggibile ("alla Karpathy"): funzioni dirette, formule
esplicite e ispezionabili in `discovery_engine.py`, zero ML/training, tutti i
tunable in `radar_config.yaml`.

- **Layer A — Signal Score (0–100), uguale per tutti.** Due sole componenti
  calcolabili in modo onesto sui dati liberi:
  - *età rispetto al livello* — data di nascita (Wikidata) vs età di riferimento
    reale del tier di competizione;
  - *buzz precoce* — su uno storico persistito (`buzz_history.json`): velocità
    delle menzioni (accelerazione, non volume), tier delle fonti (bonus alla
    nicchia, penalità a chi è già mainstream), diffusione geografica.
- **Layer B — Fit Score contestuale.** Nessun modello: filtri + moltiplicatori
  per profilo (rivendita / rosa Serie C / profilo tattico / oriundi FSGC).
- **Layer C — Stima bayesiana.** Filtro alla Kalman 1D: *non prevede il futuro*,
  stima quanto fidarsi del punteggio attuale viste le osservazioni ripetute nel
  tempo. Banda stretta = segnale coerente; banda larga = poco da fidarsi.
- **Layer D — Rilevamento cambiamenti di stato (IL TURNO).** Combina innovazione
  di Kalman (shock 3-sigma), CUSUM a due code (deriva lenta), fatti verificati
  (club aggiornato via ricerca web) e le finestre "early adopter".
- **Layer E — LA CURVA.** Classifica la posizione sulla curva di adozione (6
  fasi) e i 4 fattori oggettivi di decollo (accelerazione, scalata dei tier,
  allargamento a testate distinte, persistenza). Quando ≥3 convergono e nessun
  grande giornale ne parla ancora → **STA PER ESPLODERE**.

---

## Lo swarm di AI (il dossier)

Su ogni candidato che supera il funnel, quattro ruoli in sequenza — un
contraddittorio, non una singola opinione:

1. **📰 Il Cronista** — raccoglie i fatti; con ricerca web reale (server tool
   OpenRouter) verifica la squadra *attuale*.
2. **🔍 Il Verificatore** — il segnale è corroborato da più fonti o da una sola?
3. **😈 Lo Scettico** — cerca attivamente perché potrebbe essere un falso positivo.
4. **⚖️ Il Giudice** — sintetizza: vale la pena seguirlo ora? sì/no, confidence,
   una riga di motivazione, club aggiornato.

Catena di fallback multi-provider genuina: **Gemini** (primario) → **OpenRouter**
→ **NVIDIA NIM**. Ogni modello verificato dal vivo prima di fidarsene.

---

## Onestà, non hype (è nel DNA, non nel marketing)

- **Zero dati inventati.** Se una fonte non risponde o un dato manca, si dice
  "non disponibile"; mai uno zero fittizio o un club dedotto.
- **Il tabellone.** Ogni "sta per esplodere" è una scommessa verificabile,
  chiusa con l'esito reale — *esploso* o *sgonfiato*. Precisione e richiamo
  (fallimenti compresi) sono in `/processo`. Su campione piccolo il sistema
  dice "non lo so ancora", non inventa una percentuale.
- **Niente sparisce in silenzio.** Una finestra aperta resta nel turno finché non
  si risolve; quando si chiude viene spiegata una volta ("arrivato ai grandi
  giornali" / "raffreddato"), mai un giocatore che svanisce senza motivo.
- **Il contraddittorio per-giocatore** su ogni scheda.
- **Limiti dichiarati** (vedi sotto), in-prodotto, non solo qui.

---

## Fonti dati (tutte pubbliche, zero budget, zero chiavi a pagamento)

- **Wikidata (SPARQL)** — rose Serie C/D italiane (per lega) e pool per
  nazionalità (per cittadinanza, con filtro genere obbligatorio).
- **Wikipedia** — rose dei tornei CONMEBOL U-17/U-20 (parsing del wikitext).
- **Google News (RSS)** — segnale di buzz, cercando sempre *nome + squadra* per
  evitare le omonimie.
- **Watchlist manuale** — nomi curati a mano in `radar_config.yaml`.

Ogni candidato è identificato internamente dal suo **QID Wikidata** stabile, mai
dal solo nome. FBref e Transfermarkt sono esclusi per rispetto di ToS/robots.

---

## Struttura del repo

Il repo `OuroborosCouncil` ospita più strumenti; **SENTINEL / OB1 Radar è quello
principale e più sviluppato**.

```
discovery_engine.py       # il motore: pool, scoring (Layer A–E), swarm, curva, tabellone
visual_council_app.py     # app Flask: rotte SENTINEL + il vecchio "Council"
radar_config.yaml         # UNICO posto per pesi/soglie/fonti/profili (no codice da toccare)
openrouter_client.py      # client swarm (+ ricerca web nativa per il Cronista)
gemini_client.py          # provider primario dello swarm
nvidia_client.py          # provider di riserva
monitor/web_monitor.py    # ricerca Google News / RSS (riusata dal buzz)
templates/
  turno.html              # IL TURNO
  mappa.html              # LA MAPPA
  processo.html           # L'AVVOCATO DEL DIAVOLO
  radar.html              # ARCHIVIO
  council.html            # tool "Council" (dibattito AI, indipendente)

# File di stato (append-only, generati a runtime; su Postgres se DATABASE_URL è settato)
radar_feed.json           # storico punteggi per candidato nel tempo
buzz_history.json         # snapshot menzioni per candidato
watchlist.json            # giocatori segnati a mano dalle schede
curve_validation.json     # registro scommesse (esplosi/sgonfiati) + crossing

# Legacy (non SENTINEL): Miss Minute — prioritizzazione progetti (miss_minute*.py, priorities.yaml)
```

---

## Setup ed esecuzione

### Variabili d'ambiente (`.env`)

| Variabile | Obbligatoria | A cosa serve |
|-----------|:---:|--------------|
| `OPENROUTER_API_KEY` | ✅ | Swarm + ricerca web reale del Cronista |
| `GEMINI_API_KEY` | ⬜ | Provider primario dello swarm (consigliato) |
| `NVIDIA_API_KEY` | ⬜ | Provider di riserva |
| `DATABASE_URL` | ⬜ | Postgres per persistere lo stato oltre il filesystem effimero |
| `RADAR_ACCESS_KEY` | ⬜ | Se impostata, l'app chiede una chiave d'accesso: si apre una volta con `?key=LACHIAVE` e da lì un cookie sblocca tutto. Senza, il servizio pubblico è aperto a chiunque trovi l'URL (che può bruciare le quote AI gratuite con scansioni a raffica) |

### In locale

```bash
pip install -r requirements.txt
python visual_council_app.py     # dev server su http://localhost:8081
# apri /turno, /mappa, /processo, /radar
```

### Diagnostica copertura fonti

```bash
python discovery_engine.py diagnose
```

### Deploy su Google Cloud Run

```bash
gcloud config set project <IL_TUO_PROJECT_ID>
gcloud run deploy ob1-radar --source . --region europe-west1 \
  --allow-unauthenticated --no-cpu-throttling --max-instances 1
```

> `--no-cpu-throttling` **non è opzionale**: la scansione gira in un thread di
> sfondo (per non far scadere la richiesta HTTP), e senza quel flag Cloud Run
> affama di CPU il thread tra un polling e l'altro, allungando una scansione da
> ~60s a diversi minuti.
>
> `--max-instances 1` **nemmeno**: lo stato della scansione vive nella memoria
> del processo, e se l'autoscaling accende una seconda istanza il polling di
> `/api/radar/refresh/status` può finire sull'istanza *sbagliata* — vedresti
> "inattivo" mentre la scansione gira altrove. Un'istanza sola basta e avanza
> per un uso personale.
>
> Le pagine escono con `Cache-Control: no-store` così ogni deploy si vede
> subito, senza refresh forzati. Dopo il primo deploy con `DATABASE_URL`
> impostata, apri `/api/radar/health` una volta per confermare che lo storico
> sta davvero su Postgres (Neon) e non sul filesystem effimero.

### Scansione automatica al mattino (consigliata)

La scansione da telefono resta possibile, ma il modo giusto di usare SENTINEL
è **non aspettarla mai**: un Cloud Scheduler che scansiona ogni mattina, così
apri l'app e i dati sono già freschi. Bonus non banale: run a cadenza regolare
rendono finalmente onesto il segnale di *velocità* delle menzioni, che con run
a intervalli casuali è dichiaratamente fragile.

```bash
gcloud scheduler jobs create http radar-scan-mattina \
  --location europe-west1 \
  --schedule "0 7 * * *" --time-zone "Europe/Rome" \
  --uri "https://<IL_TUO_SERVIZIO>.run.app/api/radar/refresh" \
  --http-method POST \
  --headers "Content-Type=application/json,X-Radar-Key=<LA_TUA_RADAR_ACCESS_KEY>" \
  --message-body '{"profile":"tactical_profile","wait":true}' \
  --attempt-deadline 600s
```

> `"wait": true` **è importante**: tiene la richiesta HTTP aperta fino a fine
> scansione, obbligando Cloud Run a tenere viva l'istanza (e la CPU) per tutta
> la durata. Un fire-and-forget senza nessuno che fa polling lascerebbe il
> thread di sfondo in balia del reclaim dell'istanza. L'header `X-Radar-Key`
> serve solo se hai impostato `RADAR_ACCESS_KEY`; senza gate, togli l'header.

---

## Riferimento API

| Metodo | Endpoint | Descrizione |
|--------|----------|-------------|
| `POST` | `/api/radar/refresh` | Avvia una scansione in background; con `{"wait":true}` risponde a scansione finita (per Cloud Scheduler) |
| `GET` | `/api/radar/refresh/status` | Polling dello stato: include `progress` (es. "dossier AI 3/8") e `feed_ready` (punteggi già salvati e consultabili mentre i dossier arrivano) |
| `GET` | `/api/radar/feed` | Archivio (cap ai primi 300 per signal; `?limit=all` per tutti) |
| `GET` | `/api/radar/turno` | Solo i casi con un cambiamento/finestra aperta |
| `GET` | `/api/radar/mappa` | Posizione sulla curva di tutti i profilati |
| `GET` | `/api/radar/processo` | Il tabellone (precisione/richiamo) |
| `POST` | `/api/radar/watchlist` | Segna/togli un giocatore |
| `GET` | `/api/radar/config` | Pesi/profili per il ricalcolo del Fit lato client |

---

## Limiti onesti

- Non esistono dati event-based gratuiti (xG, azioni progressive) a livello
  Serie C/D o giovanili sudamericane: SENTINEL **non sostituisce** Wyscout, è a
  monte. Il buzz è corroborazione, mai l'unica prova.
- Il segnale di buzz (Google News RSS + tier dedotto dal nome della testata) è la
  parte più fragile e potenzialmente aggirabile — per questo un solo segnale non
  porta mai un candidato in cima, e tutto sta in un file di config correggibile.
- La qualità del segnale di velocità dipende dalla regolarità delle scansioni:
  con la scansione programmata (Cloud Scheduler, vedi deploy) la cadenza è
  regolare; a mano, dipende da quanto spesso premi "Aggiorna".
- La validità del metodo è **una tesi, non un fatto dimostrato**. La prova è il
  tabellone del `/processo`, nel tempo: se batte il tasso base su un campione
  ampio, il metodo funziona; se no, il sistema lo dirà da solo.

---

## Stato

In produzione su Cloud Run, in uso reale da mobile. Il grosso delle capacità
(curva, mappa, tabellone, contraddittorio, persistenza delle finestre) emerge
con l'accumulo delle scansioni — servono ≥3 controlli per collocare un giocatore
sul percorso. Roadmap aperta: PWA (manifest/service worker), maggior peso ai
"segnali costosi" (presenze reali, convocazioni) rispetto al buzz falsificabile.
