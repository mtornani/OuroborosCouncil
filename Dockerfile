FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run inietta PORT (di solito 8080) e si aspetta che il container
# ci ascolti sopra - niente porta fissa come nel Procfile locale.
ENV PORT=8080
EXPOSE 8080

# --timeout 120: gunicorn di default chiude un worker dopo 30s, ma
# /api/radar/refresh (Wikidata + Wikipedia + buzz Google News + swarm AI)
# puo' richiederne 30-60+ - senza alzarlo la richiesta fallirebbe a meta'
# anche se il codice funziona. "exec" in forma shell serve a espandere
# $PORT all'avvio (pattern standard per Cloud Run).
CMD exec gunicorn --bind 0.0.0.0:$PORT --workers 1 --timeout 120 visual_council_app:app
