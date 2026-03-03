@echo off
:: MISS MINUTE - Launcher per Gemini CLI (Windows)
:: ================================================
:: Lancia Gemini con il contesto completo di Mirko
::
:: USO:
::   gemini_miss_minute.bat "cosa devo fare oggi?"
::   gemini_miss_minute.bat "aiutami con ob1"
::   gemini_miss_minute.bat  (senza argomenti = interattivo)

setlocal enabledelayedexpansion

set BRIEFING_FILE=D:\AI\.miss_minute\MIRKO_BRIEFING.md
set PRIORITIES_FILE=D:\AI\.miss_minute\priorities.yaml

:: Crea file temporaneo con context completo
set TEMP_CONTEXT=%TEMP%\miss_minute_context.md

echo # MISS MINUTE CONTEXT > %TEMP_CONTEXT%
echo. >> %TEMP_CONTEXT%
type %BRIEFING_FILE% >> %TEMP_CONTEXT%
echo. >> %TEMP_CONTEXT%
echo --- >> %TEMP_CONTEXT%
echo STATO ATTUALE PROGETTI: >> %TEMP_CONTEXT%
type %PRIORITIES_FILE% >> %TEMP_CONTEXT%
echo --- >> %TEMP_CONTEXT%

if "%~1"=="" (
    :: Modalità interattiva
    gemini -s "$(type %TEMP_CONTEXT%)"
) else (
    :: Query singola
    gemini -s "$(type %TEMP_CONTEXT%)" "%~1"
)

del %TEMP_CONTEXT%
