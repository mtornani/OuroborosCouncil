# Miss Minute - PowerShell Launcher per Gemini CLI
# =================================================

function Start-MissMinute {
    param(
        [Parameter(ValueFromRemainingArguments=$true)]
        [string[]]$Query
    )
    
    $briefingFile = "D:\AI\.miss_minute\MIRKO_BRIEFING.md"
    $prioritiesFile = "D:\AI\.miss_minute\priorities.yaml"
    
    # Leggi i file
    $briefing = Get-Content $briefingFile -Raw
    $priorities = Get-Content $prioritiesFile -Raw
    
    # Costruisci context
    $context = @"
$briefing

---
STATO ATTUALE PROGETTI (live):
$priorities
---

TIMESTAMP: $(Get-Date -Format "yyyy-MM-dd HH:mm")
"@

    # Salva in temp file (gemini cli legge meglio da file)
    $tempFile = [System.IO.Path]::GetTempFileName() + ".md"
    $context | Out-File -FilePath $tempFile -Encoding UTF8
    
    if ($Query) {
        # Query singola
        $queryString = $Query -join " "
        Write-Host "⏰ Miss Minute | Query: $queryString" -ForegroundColor Cyan
        Write-Host ""
        gemini --systemInstruction (Get-Content $tempFile -Raw) "$queryString"
    } else {
        # Modalità interattiva
        Write-Host "⏰ Miss Minute | Modalità interattiva" -ForegroundColor Cyan
        Write-Host "   Digita 'exit' per uscire" -ForegroundColor DarkGray
        Write-Host ""
        gemini --systemInstruction (Get-Content $tempFile -Raw)
    }
    
    # Cleanup
    Remove-Item $tempFile -ErrorAction SilentlyContinue
}

# Alias brevi
Set-Alias -Name mmg -Value Start-MissMinute
Set-Alias -Name jarvis -Value Start-MissMinute

Write-Host "⏰ Miss Minute Gemini loaded. Comandi: Start-MissMinute, mmg, jarvis" -ForegroundColor Cyan

# Esempi:
# mmg "cosa devo fare oggi?"
# mmg "aiutami a finire ob1"
# jarvis "status progetti"
# Start-MissMinute   # Modalità interattiva
