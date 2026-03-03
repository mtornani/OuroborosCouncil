@echo off
title Ouroboros Council Server
color 0B

echo ========================================================
echo       OUROBOROS COUNCIL HUD - STARTUP SCRIPT
echo ========================================================
echo.

cd /d "d:\AI\_archivio\miss_minute"

echo [1] Apro l'interfaccia nel tuo browser principale...
timeout /t 2 /nobreak >nul
start "" "http://localhost:8081"

echo [2] Avvio il cervello e il server...
echo --------------------------------------------------------
echo NON CHIUDERE QUESTA FINESTRA NERA FINCHE' STAI LAVORANDO.
echo Per spegnere tutto chiudi semplicemente questa finestra (X).
echo --------------------------------------------------------
echo.

py visual_council_app.py
pause
