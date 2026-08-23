#!/usr/bin/env bash
# DEPLOY DA TELEFONO — un comando solo.
#
#   ./deploy.sh
#
# Pensato per essere lanciato da Google Cloud Shell (shell.cloud.google.com),
# che si apre dal browser del telefono e ha gia' gcloud autenticato: da mobile
# e' l'unica strada che non fa impazzire. Su un computer funziona uguale.
#
# Fa tre cose, in quest'ordine, e si ferma alla prima che va male:
#   1. lancia lo smoke test         -> non si deploya un impianto rotto
#   2. deploya su Cloud Run          -> con i flag che NON sono opzionali
#   3. verifica che sia atterrato    -> confronta la versione servita
#
# Il punto 3 esiste perche' "il deploy e' andato a buon fine" secondo gcloud
# e "la versione nuova sta rispondendo" sono due cose diverse, e da telefono
# non hai voglia di scoprirlo il giorno dopo.
set -euo pipefail

SERVIZIO="${SERVIZIO:-ob1-radar}"
REGIONE="${REGIONE:-europe-west1}"
URL="${URL:-https://ob1-radar-957169827556.europe-west1.run.app}"

rosso() { printf '\033[31m%s\033[0m\n' "$1"; }
verde() { printf '\033[32m%s\033[0m\n' "$1"; }
grigio() { printf '\033[2m%s\033[0m\n' "$1"; }

attesa=$(tr -d ' \n' < VERSION 2>/dev/null || echo "")
grigio "── versione nel codice: ${attesa:-sconosciuta}"

# ---------- 1. l'impianto regge? ----------
echo
grigio "── smoke test (salta le fonti esterne: qui interessa il codice)"
if ! python3 smoke_test.py --offline; then
  rosso "Smoke test FALLITO: non deployo. Guarda cosa dice qui sopra."
  exit 1
fi

# ---------- 2. deploy ----------
echo
grigio "── deploy su Cloud Run (qualche minuto: costruisce l'immagine)"
# --no-cpu-throttling: la scansione gira in un thread di sfondo e senza questo
#   flag Cloud Run gli affama la CPU fra un polling e l'altro.
# --max-instances 1: lo stato della scansione vive nella memoria del processo;
#   con una seconda istanza il polling puo' finire su quella sbagliata.
gcloud run deploy "$SERVIZIO" \
  --source . \
  --region "$REGIONE" \
  --allow-unauthenticated \
  --no-cpu-throttling \
  --max-instances 1

# ---------- 3. e' davvero atterrato? ----------
echo
grigio "── verifico cosa sta rispondendo davvero"
sleep 5
risposta="$(curl -fsS --max-time 30 "$URL/api/version" || echo '')"
if [ -z "$risposta" ]; then
  rosso "Il servizio non risponde su $URL/api/version — controlla i log:"
  echo "  gcloud run services logs read $SERVIZIO --region $REGIONE --limit 50"
  exit 1
fi

servita="$(printf '%s' "$risposta" | sed -n 's/.*"version"[: ]*"\([^"]*\)".*/\1/p')"
build="$(printf '%s' "$risposta" | sed -n 's/.*"build"[: ]*"\([^"]*\)".*/\1/p')"

echo
if [ -n "$attesa" ] && [ "$servita" != "$attesa" ]; then
  rosso "ATTENZIONE: il codice dice $attesa ma il servizio risponde $servita."
  rosso "Il deploy non e' arrivato dove pensi. Non fidarti finche' non coincidono."
  exit 1
fi
verde "Deploy atterrato: versione $servita · revisione $build"
echo
grigio "Adesso, dall'app o da qui:"
grigio "  - apri /turno: sara' CORTO (da ~56 casi a ~17). E' voluto."
grigio "  - la prima scansione non validera' quasi nessuno: cache fredda,"
grigio "    servono 3-4 giri. 'non validabile' NON e' un voto basso."
grigio "  - il buzz scende una volta sola (database e livescore non contano piu')."
grigio "  - /processo ha tre blocchi nuovi, fra cui la precisione del turno."
