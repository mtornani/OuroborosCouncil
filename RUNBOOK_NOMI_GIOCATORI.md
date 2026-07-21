# RUNBOOK — produrre N profili giocatori reali per sample/outreach

Scoped su questo repo (`OuroborosCouncil`, motore `discovery_engine.py` —
prodotto pubblico: OB1 Radar). Stesso schema del runbook bridge Claude
Code ↔ Grok: questo file serve a chi (persona o AI) deve lanciare un
campione senza dover leggere tutto `discovery_engine.py`.

## Repo attiva

path: repo checkout di `mtornani/OuroborosCouncil` (qui: `/home/user/OuroborosCouncil`)

## Prerequisiti

- Python 3.11+
- `pip install -r requirements.txt` (Flask, requests, PyYAML, psycopg2-binary, gunicorn, python-dotenv)
- Variabili d'ambiente (nomi, MAI valori, in un file condiviso):
  - Nessuna è obbligatoria per il campione base (Layer A età-vs-livello +
    Layer B buzz girano su dati aperti, senza chiave).
  - `OPENROUTER_API_KEY` e/o `NVIDIA_API_KEY` e/o `GEMINI_API_KEY` — solo
    se si usa `--with-dossier` (il dossier AI a 4 ruoli costa quota vera).
  - `DATABASE_URL` — opzionale, solo se si vuole persistenza durevole
    dello storico buzz su Postgres invece che su file locale effimero
    (`buzz_history.json`, già in `.gitignore`).

## Comando sample (3 profili, nessuna chiamata AI)

```
cd /home/user/OuroborosCouncil
python3 discovery_engine.py sample --limit 3 --profile tactical_profile \
  --out out/sample_3.json
```

`--profile` è una delle chiavi in `radar_config.yaml` → `purpose_profiles`
(`resale_value`, `first_team_need`, `tactical_profile`, `fsgc_oriundi`).

Con dossier AI (costa quota, richiede almeno una chiave API):

```
python3 discovery_engine.py sample --limit 3 --profile tactical_profile \
  --out out/sample_3.json --with-dossier
```

Senza `--out`, il JSON va su stdout invece che su file.

## Tempi attesi

- `fetch_candidate_pool()` interroga Wikidata (rose Serie C/D italiane +
  giovanili CONMEBOL) e da sola impiega **~60-90 secondi** — è il grosso
  del tempo, indipendente da `--limit`.
- Il check buzz (Google News) gira solo su una shortlist limitata
  (`radar_config.yaml` → `performance.buzz_check_pool_size`, default 60),
  non sull'intero pool: qualche decina di secondi in più.
- `--with-dossier` aggiunge 4 chiamate AI sequenziali *per candidato
  incluso nel campione finale* (non per l'intera shortlist) — un paio di
  minuti in più per candidato, se non viene saltato (vedi sotto).

## Output — schema campi

```jsonc
{
  "generated_at": "...", "profile": "...", "pool_size": 0,
  "disclosure": "...",  // cosa e' reale, cosa no, in chiaro
  "profiles": [
    {
      "candidate_id": "Q...",       // QID Wikidata stabile, MAI solo il nome
      "name": "...", "club": "...", "role": "...",
      "birth_year": "2005", "age": 20.3, "tier": "serie_c",
      "signal_score": 0.0, "fit_score": 0.0,
      "partial_data": true,          // manca un componente (eta' o buzz)
      "bullets": ["..."],            // fatti strutturati, o testo AI se --with-dossier
      "sources": ["Testata 1", "..."],  // testate viste nel controllo buzz
      "dossier": null                // dict a 4 ruoli solo con --with-dossier
    }
  ]
}
```

Un candidato con un solo componente disponibile E già al tetto (es. solo
età-relativa, satura a 1.0, niente buzz) **non riceve un dossier AI**
nemmeno con `--with-dossier` esplicito: è rumore travestito da punteggio
alto (lezione imparata dal vivo — vedi `_needs_more_signal` nel codice).
Il campo `dossier` in quel caso contiene `{"skipped": "..."}`, non un
errore: è un risparmio deliberato di quota, non un fallimento.

## Se fallisce

- `TypeError` / traceback su `_load_json` o simili → probabile
  disallineamento tra questo runbook e il codice: controllare
  `discovery_engine.py` per la firma corrente delle funzioni citate sopra.
- Il comando resta appeso oltre 3-4 minuti → quasi sempre Wikidata lento a
  rispondere, non un bug: SPARQL pubblico, nessun controllo su throughput.
- `--with-dossier` fallisce silenziosamente lasciando `dossier` con
  `{"error": "..."}` → nessuna chiave API valida nell'ambiente, o quota
  esaurita: il campo `error` riporta il messaggio esatto, mai un crash
  che perde il resto del campione.

## Dati già pronti (se non serve un nuovo giro)

Nessuno di default: questo comando non scrive su `radar_feed.json` (lo
stato "vivo" del prodotto), solo su `buzz_history.json` (storico
cumulativo condiviso col resto del sistema — un `sample` lascia comunque
traccia utile per i prossimi giri, non è usa-e-getta). Se un file
`out/sample_*.json` recente esiste già, verificarne `generated_at` prima
di rilanciare — la chiamata a Wikidata non è gratuita in tempo, anche se
è gratuita in quota.

## Cosa NON fa questo comando

- Non inventa giocatori: ogni nome viene da Wikidata (rose reali) o dalla
  watchlist manuale in `radar_config.yaml`.
- Non contatta nessuno: produce solo il JSON. L'invio resta una decisione
  e un'azione umana.
- Non tocca `radar_feed.json` (lo stato di produzione del prodotto OB1
  Radar servito da `visual_council_app.py`): è un comando a sé, pensato
  per girare anche da un runbook esterno senza capire l'intero
  orchestratore `refresh_radar()`.
