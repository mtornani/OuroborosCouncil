#!/bin/bash
# MISS MINUTE - Launcher per Gemini CLI
# ======================================
# Lancia Gemini con il contesto completo di Mirko
#
# USO:
#   ./gemini_miss_minute.sh "cosa devo fare oggi?"
#   ./gemini_miss_minute.sh "aiutami con ob1"
#   ./gemini_miss_minute.sh  # Senza argomenti = modalità interattiva

BRIEFING_FILE="D:/AI/.miss_minute/MIRKO_BRIEFING.md"
PRIORITIES_FILE="D:/AI/.miss_minute/priorities.yaml"

# Costruisci il context
CONTEXT="$(cat $BRIEFING_FILE)

---
STATO ATTUALE PROGETTI (da priorities.yaml):
$(cat $PRIORITIES_FILE)
---"

if [ -z "$1" ]; then
    # Modalità interattiva
    gemini -s "$CONTEXT"
else
    # Query singola
    gemini -s "$CONTEXT" "$1"
fi
