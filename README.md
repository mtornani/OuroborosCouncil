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
| `/radar` | **ARCHIVIO** | Tutti i candidati filtrabili per profilo/ruolo/età/paese **e per segnale costoso** (il filtro che rende cercabile il *tesoro silenzioso*), con la mini-curva e il dossier per scheda. |

Ogni scheda giocatore porta con sé:
- il suo **percorso** sulla curva di adozione (dove sta: *nessuno ne parla →
  solo fonti locali → se ne parla → sta per esplodere → sui grandi giornali →
  lo sanno tutti*);
- il **verdetto** dello swarm di AI;
- **chi ci ha già puntato**: i fatti *costosi* registrati su di lui — minuti veri
  in prima squadra, convocazioni in nazionale — con la prova riga per riga. È
  l'unico blocco della scheda che non misura attenzione;
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

## Come si costruisce il punteggio (i sei layer)

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
  per profilo (rivendita / rosa Serie C / profilo tattico).
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
- **Layer F — VALIDAZIONE TECNICA (il segnale costoso).** L'unico layer che
  *non* misura attenzione. Vedi la sezione dedicata qui sotto.

---

## Il Layer F: il segnale costoso

I layer A–E misurano tutti la stessa cosa — **l'attenzione** — e hanno un
difetto strutturale che questo README dichiarava già da sé: **scrivere un
articolo non costa nulla**. Un procuratore, un ufficio stampa o un blog
compiacente possono emetterlo a volontà. Un radar che ascolta solo quel canale
è aggirabile per costruzione.

Il Layer F legge una classe di segnali diversa: **gratis da leggere, costosi da
emettere**.

- un allenatore che manda in campo un 17enne in una lega professionistica ci
  mette punti, classifica e alla lunga il posto di lavoro;
- una federazione che lo convoca spende uno slot di rosa conteso, **ed è un
  valutatore indipendente dal club** (il club ha interesse a gonfiare il
  proprio asset, la federazione no);
- un club che lo compra da una categoria inferiore ci mette soldi.

Nessuno di questi atti è falsificabile dall'entourage del giocatore. Base
teorica consolidata, non inventata qui: **signaling costoso** (Spence 1973) e
**principio dell'handicap** (Zahavi 1975).

> Continua a valere la frase di apertura: SENTINEL **non misura quanto è bravo
> un giocatore**. Il Layer F misura *quanto qualcuno che rischiava qualcosa ha
> già puntato su di lui*. È una misura di scommesse altrui, non un voto
> tecnico. La qualità la decide sempre il tuo occhio.

### I quadranti (perché non è un numero da sommare al Signal Score)

Sommare validazione e buzz distruggerebbe informazione: un giocatore con
buzz 80 / validazione 0 e uno con buzz 0 / validazione 80 finirebbero sullo
stesso numero, e sono i due casi **più opposti** che esistano. Quindi i due
assi restano separati e si incrociano:

|  | validazione assente/debole | validazione forte |
|---|---|---|
| **buzz alto** | ⚠️ **NE PARLANO E BASTA** | ✅ **CONFERMATO** |
| **buzz basso** | quiete | 💎 **TESORO SILENZIOSO** |

**TESORO SILENZIOSO è il quadrante che il radar prima non poteva vedere.** Un
17enne con minuti veri in una prima divisione di cui nessun giornalista ha
ancora scritto ha buzz ≈ 0: usciva dal funnel come rumore. Il Layer F non
aggiunge solo un controllo — **raddoppia lo spazio di ricerca** coprendo
l'angolo cieco strutturale del sistema.

**NE PARLANO E BASTA** è l'altro guadagno: è la firma del falso positivo che
finora lo Scettico dello swarm poteva solo *indovinare*. Ed è la difesa contro
l'attacco che questo README ammette (il buzz è aggirabile): chi pianta articoli
muove il buzz e **non** muove la validazione, quindi finisce in un quadrante
che si chiama da solo invece di passare per un vero positivo.

### La regola cardinale: può solo confermare, mai condannare

Le fonti libere sono incomplete per costruzione (audit di questo stesso repo:
52% dei QID senza club su Wikidata). **L'assenza di un dato non è prova
dell'assenza del fatto.** Quindi un componente entra nel calcolo *solo* con
evidenza positiva: non esistono zeri "per dato mancante". Conseguenza,
bloccata da test: **aggiungere un record non può mai abbassare il punteggio.**

È anche il motivo per cui i componenti si combinano in **noisy-OR** invece che
con la media pesata del Layer A. Là i componenti sono due viste dello stesso
fenomeno latente e la media ha senso; qui ogni segnale costoso è una conferma
*indipendente*, e non averne uno non è un voto contro. La media violerebbe la
monotonia; il noisy-OR no, mai.

Da qui i **tre stati**, che vanno tenuti distinti a ogni costo:

| stato | significato |
|---|---|
| `validato` | evidenza costosa trovata → punteggio 0–100 leggibile |
| `non_corroborato` | le fonti si sono lette **davvero**, non c'era nulla di costoso |
| `non_validabile` | **non si è potuto guardare** (fonte muta/assente) |

La differenza fra gli ultimi due è la differenza fra *"ho guardato e non c'era
niente"* e *"non ho potuto guardare"*. Confonderle — o far somigliare la
seconda a un voto basso — sarebbe esattamente il tipo di disonestà che questo
progetto rifiuta altrove. Per questo un `non_validabile` con buzz alto resta
**NON VALIDABILE**, e non diventa mai "NE PARLANO E BASTA".

### Cosa cambia nel prodotto

- **IL TURNO** ha un motivo nuovo, e apre la lista: **QUALCUNO CI HA PUNTATO** —
  un fatto costoso *nuovo* (una prima convocazione, i primi minuti in un club).
  È l'unico motivo del turno in cui a muoversi non è l'attenzione ma qualcosa
  che qualcuno ha pagato. Non può inondare il turno: il confronto è sulle
  *firme* (tipo+squadra), non sui punteggi, quindi le presenze che crescono
  ogni settimana non generano nulla.
- **STA PER ESPLODERE** porta ora la controprova: risponde alla domanda che un
  uomo di campo fa per prima — *"sì, ma ha giocato davvero?"*.
- **Il contraddittorio** smette di essere generico ("il buzz è fragile", vero
  per tutti) e diventa specifico: *nessuno che rischiava qualcosa ha ancora
  puntato su di lui*, oppure *la conferma c'è ma viene da un solo soggetto*.
- **`/processo`** mette sotto processo anche questo layer, con la sua copertura
  reale misurata (`validazione_copertura`).

### Limiti misurati dal vivo (non stimati)

Verificato durante lo sviluppo su Wikidata reale:

- **`P1350` (presenze) è quasi non popolato per i giovani di Serie C.** Su un
  campione reale di U22 di Serie C le presenze registrate erano nulle: quei
  candidati risultano `non_corroborato`, non "scarsi". È il motivo per cui
  quello stato esiste come stato a sé.
- **Le convocazioni in nazionale sono invece ben popolate**, e non dipendono da
  `P1350`: basta che la membership esista. Oggi è il canale più affidabile del
  layer, ed è anche quello col peso più alto — coincidenza fortunata, ma
  l'ordine dei pesi è motivato dal *costo dell'atto*, non dalla copertura.
- Esempio reale end-to-end (dati live): un 17enne con 11 presenze in una prima
  divisione top + 17 in nazionale U17 → **61.6/100, `validato`, 3
  scommettitori distinti** → con buzz basso finisce in **TESORO SILENZIOSO**.
- Una lega non mappata in `competizioni` non vale zero: vale **livello ignoto**,
  finisce nella copertura e viene dichiarata sulla scheda.
- Durante lo sviluppo l'endpoint SPARQL di Wikidata era **sotto outage
  dichiarato** (`429 - aggressively rate-limiting to 1 req/min`). Per questo
  cache e tetto di query per run non sono ottimizzazioni ma parte del
  contratto: **la validazione è un lusso che non deve mai far fallire una
  scansione.** Se la fonte tace, il radar torna esattamente a com'era prima
  del Layer F.

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

- **Wikidata (SPARQL)** — rose per lega (Serie B/C/D + 2ª/3ª di Portogallo,
  Francia, Spagna, Olanda, Germania) e pool per nazionalità (per
  cittadinanza, con filtro genere obbligatorio).
- **Wikipedia** — rose dei tornei CONMEBOL U-17/U-20 (parsing del wikitext).
- **Google News (RSS)** — segnale di buzz, cercando sempre *nome + squadra* per
  evitare le omonimie.
- **Watchlist manuale** — nomi curati a mano in `radar_config.yaml`.

Ogni candidato è identificato internamente dal suo **QID Wikidata** stabile, mai
dal solo nome. FBref e Transfermarkt sono esclusi per rispetto di ToS/robots.

### Il grafo delle fonti (la piramide)

Le fonti gratuite sono spesso stantie (audit live 2026-07 su 100 QID reali del
feed: 52% senza club su Wikidata, mediana 24 giorni dall'ultima modifica della
scheda, p75 a 120 giorni). Per questo il motore non memorizza *fatti* ma
**osservazioni con provenienza** — `(candidato, campo, valore, fonte, quando,
citazione)` — accumulate in append-only (`radar_observations.json`, su Postgres
in produzione). Un **risolutore** con regole esplicite decide il valore
corrente e lo spiega sulla card ("secondo chi, da quando").

Le fonti sono disposte in una **piramide** (`piramide` in `radar_config.yaml`):
in basso l'occhio umano e la nicchia locale (fresco, vicino al campo), in alto
i dati strutturati globali (consolidati, in ritardo). Regola d'inversione: i
fatti **veloci** (club attuale) si leggono *dal basso* — un articolo datato
batte un claim Wikidata senza data — i fatti **lenti** (data di nascita)
*dall'alto*. La conferma umana (un tap sulla card "CLUB DA CORREGGERE") batte
tutto e **sopravvive** alle riscritture da Wikidata. La query buzz usa il club
*risolto* e, finché due fonti sono in disaccordo, cerca con **entrambi** i
club — così un trasferimento non acceca il radar proprio nel momento del salto.

---

## Struttura del repo

Il repo `OuroborosCouncil` ospita più strumenti; **SENTINEL / OB1 Radar è quello
principale e più sviluppato**.

```
discovery_engine.py       # il motore: pool, scoring (Layer A–F), swarm, curva, validazione, tabellone
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
career_records.json       # CACHE (non storico) dei dati di carriera per il Layer F — si può buttare, si rilegge

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
| `RADAR_GUEST_KEY` | ⬜ | Chiave separata, **di sola lettura** — per mandare il link a qualcuno senza consegnare la chiave vera. Con `?guest_key=LACHIAVE` si legge tutto (turno, mappa, processo, archivio) ma ogni scrittura (scansione, watchlist, conferma club) risponde 403. Ha senso solo se `RADAR_ACCESS_KEY` è impostata; altrimenti è ignorata |

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
> sta davvero su Postgres (Neon) e non sul filesystem effimero — la stessa
> risposta include anche `version`/`build` (vedi sotto), un solo GET copre
> entrambi i check.

### "È andato il deploy?" — versione visibile

In fondo a ogni pagina (`/turno`, `/radar`, `/mappa`, `/processo`) c'è una
riga tipo `SENTINEL v0.6.0 · ob1-radar-00042-abcd`:

- **`v0.6.0`** viene dal file `VERSION` in root — bumpala a mano quando cambia
  qualcosa che conta (non ad ogni commit): è per un umano che guarda il
  footer, non un hash. `MAJOR.MINOR.PATCH` alla buona: PATCH per un fix,
  MINOR per una feature, MAJOR se cambia qualcosa in modo incompatibile
  (raro, per un tool personale).
- **`ob1-radar-00042-abcd`** è la *revision* che Cloud Run assegna in automatico
  a ogni deploy (env var `K_REVISION`, iniettata da Cloud Run stesso — zero
  configurazione): cambia SEMPRE ad ogni deploy, anche quando `VERSION` resta
  la stessa, quindi è la prova definitiva che il deploy nuovo è atterrato. In
  locale (`K_REVISION` assente) mostra `locale`.

Per uno script (Grok compreso) c'è `GET /api/version` → `{"version": "0.6.0",
"build": "ob1-radar-00042-abcd"}`, più leggero di caricare `/turno` intera.

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
| `GET` | `/api/version` | `{version, build}` — il check "è andato il deploy?" senza caricare una pagina intera |

---

## Limiti onesti

- Non esistono dati event-based gratuiti (xG, azioni progressive) a livello
  Serie C/D o giovanili sudamericane: SENTINEL **non sostituisce** Wyscout, è a
  monte. Il buzz è corroborazione, mai l'unica prova.
- Il Layer F **non colma** quel vuoto e non ci prova: non misura la prestazione,
  misura *chi ha già scommesso*. Un giocatore può avere 0 di validazione ed
  essere fortissimo — vuol dire solo che nessuno l'ha ancora rischiato, o che la
  fonte non lo sa. Per questo `non validabile` non è mai un voto basso.
- Il segnale di buzz (Google News RSS + tier dedotto dal nome della testata) è la
  parte più fragile e potenzialmente aggirabile — per questo un solo segnale non
  porta mai un candidato in cima, e tutto sta in un file di config correggibile.
- La qualità del segnale di velocità dipende dalla regolarità delle scansioni:
  con la scansione programmata (Cloud Scheduler, vedi deploy) la cadenza è
  regolare; a mano, dipende da quanto spesso premi "Aggiorna".
- La copertura del segnale costoso sulle fonti libere è **parziale e misurata
  in prodotto** (`/processo` → `validazione_copertura`): su Serie C/D le
  presenze registrate su Wikidata sono rare, le convocazioni in nazionale molto
  meno. Il layer si dichiara da solo, non promette più di quanto legge.
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
