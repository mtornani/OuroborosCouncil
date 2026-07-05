# 🐍 OUROBOROS RADAR
## Early Adopter Player Scouting — la finestra prima che si chiuda

> *"OB1 trova il talento. Il Radar ti dice quando il mercato sta per trovarlo anche lui."*

---

## Il problema che risolve

Un giocatore attraversa una **curva di diffusione dell'attenzione** (Rogers):

```
 attenzione
     ▲                    ╭───╮
     │                 ╭──╯   ╰──╮
     │              ╭──╯         ╰──╮
     │          ╭───╯               ╰───╮
     │   ╭──────╯                       ╰──────╮
     └───┴──────────┴──────────┴───────────────┴──▶ tempo
      INNOVATOR   EARLY      CROSSING      MAINSTREAM
                 ADOPTER    (il chasm)
       solo web    gli        stampa        tutti lo
       locale    addetti    nazionale       conoscono
                ai lavori    arriva
```

Il valore per chi scouta sta **prima del chasm**: performance già visibile
a chi sa guardare, attenzione del mercato ancora bassa. Quando il giocatore
attraversa la curva, arrivano visibilità, concorrenza e prezzo.

Il Radar misura **oggettivamente** dove si trova ogni giocatore sulla curva
e — soprattutto — **a che velocità la sta attraversando**. Quando i segnali
dicono che sta per uscire dalla fase early adopter, suona l'allarme:
è il momento di visionarlo dal vivo o di muoversi.

## I tre numeri

| Numero | Domanda a cui risponde | Come si calcola |
|--------|------------------------|-----------------|
| **ADI** (Attention Diffusion Index, 0-100) | *Dove* sei sulla curva? | Tier delle fonti che ne parlano, presenza/edizioni Wikipedia, volume menzioni 30gg, spread linguistico, pageviews |
| **Breakout Score** (0-100) | *Quanto in fretta* la stai attraversando? | Accelerazione menzioni (derivata), escalation di tier, spike pageviews, keyword di mercato, nuove lingue, creazione pagina Wikipedia |
| **Finestra** (OPEN / CLOSING / CLOSED) | *Cosa devo fare?* | 🟢 OPEN = visionare con calma · 🟠 CLOSING = **agire ora** · ⚪ CLOSED = il mondo lo sa già |

Con almeno 3 snapshot il Radar stima anche **"mainstream tra ~N settimane"**
(estrapolazione lineare del trend ADI).

Ogni punteggio è **spiegabile**: porta con sé la lista dei fattori oggettivi
che l'hanno generato ("prima menzione tier 2", "menzioni da 4 a 10/settimana",
"spike pageviews 2.7x"). Davanti a un DS puoi sempre dire *perché* il radar suona.

## I segnali (tutti gratuiti, zero API key)

1. **Google News RSS in 6 lingue** (it/en/es/pt/fr/de) — menzioni 7/30gg,
   keyword di rumor mercato nei titoli, spread linguistico
2. **Tier delle fonti** — chi ne parla conta più di quanto se ne parla:
   - Tier 0: locale/nicchia → fase innovator
   - Tier 1: specialisti mercato (TMW, Transfermarkt...) → early adopter
   - Tier 2: mainstream nazionale (Gazzetta, Marca...) → sta attraversando
   - Tier 3: globale (BBC, ESPN...) → finestra chiusa
   L'**escalation di tier** è il segnale più predittivo.
3. **Wikipedia API** — esistenza pagina per lingua, numero edizioni.
   La *creazione* della pagina tra due snapshot è un evento di crossing.
4. **Wikimedia Pageviews** — il pubblico ha iniziato a cercarlo?

**Regola ereditata da Miss Minute: ZERO dati inventati.**
Fonte muta = campo "non disponibile", mai un sostituto.

## Lo storico è il vantaggio competitivo

Un singolo snapshot è una foto. Il Radar committa ogni giorno lo snapshot
nel repo (`data/radar/history/*.jsonl`): **il repo è il database**.
Con lo storico si calcolano velocità e accelerazione dell'attenzione —
le derivate sono ciò che nessun sito di statistiche ti dà.

## Uso

```bash
# Run completo: raccolta + scoring + report + alert Telegram
python -m scout run

# Senza Telegram (test locale)
python -m scout run --no-push

# Stato watchlist in terminale
python -m scout status

# Aggiungi un giocatore
python -m scout add "Nome Cognome" --club "Club" --born 2008 --position AT

# Rigenera i report dall'ultimo run
python -m scout report
```

La watchlist vive in [`players.yaml`](players.yaml).

## Discovery — i nomi che non conosci ancora

`scout run` scansiona anche query "da early adopter" (esordi giovanili,
wonderkid, primavera, cantera...) in 4 lingue ed estrae i nomi ricorrenti
nelle fonti di nicchia **che non sono ancora arrivati al mainstream**.
È una rete a strascico volutamente rumorosa: i candidati finiscono nel
report, l'occhio umano decide chi promuovere in watchlist.

## Automazione e output

- **GitHub Action** [`ouroboros-radar.yml`](.github/workflows/ouroboros-radar.yml):
  run giornaliero alle 05:30 UTC, committa storico e report, manda gli alert
- **Telegram**: stessa disciplina di Miss Minute (max 3/giorno, quiet hours
  22-07, CRITICAL passa sempre). Alert solo quando: finestra in chiusura,
  cambio di fase, o discovery con candidati forti. Il silenzio è un valore.
- **Dashboard**: [`docs/radar.html`](docs/radar.html) — self-contained,
  si apre col browser, pronta per un meeting. Nell'app deployata su
  Google Cloud è servita su **`/radar`** (dati JSON su `/radar/data`).
- **Report testuale**: [`RADAR_REPORT.md`](RADAR_REPORT.md), rigenerato a ogni run.

## Cosa NON fa (per design)

- Non giudica il talento: quello è il lavoro di OB1 e dell'occhio umano.
  Il Radar misura solo l'**attenzione** e la sua velocità.
- Non scrapa Transfermarkt o social (ToS): usa solo fonti pubbliche con
  API/RSS ufficiali.
- Non decide: prepara la decisione. Ogni alert dice *perché* e lascia
  l'ultima parola a chi guarda le partite.
