FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run inietta PORT (di solito 8080) e si aspetta che il container
# ci ascolti sopra - niente porta fissa come nel Procfile locale.
ENV PORT=8080
EXPOSE 8080

# --timeout 570: gunicorn di default chiude un worker dopo 30s, ma
# /api/radar/refresh (Wikidata + Wikipedia + buzz Google News + swarm AI,
# fino a 15 candidati x 4 ruoli con fallback multi-provider) puo' superare
# abbondantemente i 120s misurati in condizioni ideali, specie se OpenRouter
# rallenta o un modello va in 429 e scatta il fallback. Tenuto sotto i 600s
# di --timeout impostato sul servizio Cloud Run (vedi comando di deploy),
# cosi' e' sempre gunicorn/l'app a rispondere per prima con un errore
# leggibile, mai Cloud Run che tronca la connessione a meta'.
# "exec" in forma shell serve a espandere $PORT all'avvio (pattern standard
# per Cloud Run).
#
# IMPORTANTE in fase di deploy (non impostabile da qui, e' un flag di
# `gcloud run deploy`, non del container): il refresh vero gira in un
# thread di sfondo (visual_council_app._run_radar_job), fuori da una
# request HTTP attiva. Cloud Run di default alloca CPU solo mentre risponde
# a una richiesta - senza --no-cpu-throttling quel thread viene affamato di
# CPU tra un polling e l'altro del client, e una scansione misurata in
# ~60s in locale puo' arrivare a durare minuti in produzione per questo,
# non per il lavoro che fa davvero.
# --workers 1 e' DELIBERATO (lo stato del job di scansione vive nella memoria
# del processo: piu' worker = piu' copie scollegate dello stato); --threads 4
# da' comunque risposte concorrenti dentro quell'unico processo, cosi' il
# polling dello stato non resta in coda dietro una lettura lenta del feed.
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 570 visual_council_app:app
