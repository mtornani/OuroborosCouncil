@echo off
:: MISS MINUTE - Quick Launch
:: Lancia questo per vedere lo status
:: Oppure aggiungilo allo startup di Windows

cd /d D:\AI\.miss_minute
python miss_minute.py %*

:: Per modalità daemon (sempre attivo):
:: miss_minute.bat --daemon

:: Per status completo:
:: miss_minute.bat --full

:: Per focus mode:
:: miss_minute.bat --focus
