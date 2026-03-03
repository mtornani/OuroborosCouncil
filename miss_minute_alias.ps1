# Miss Minute - Quick Alias per PowerShell
# Aggiungi al tuo $PROFILE:
# . D:\AI\.miss_minute\miss_minute_alias.ps1

function mm { 
    python D:\AI\.miss_minute\miss_minute.py $args 
}

function mm-focus { 
    python D:\AI\.miss_minute\miss_minute.py --focus 
}

function mm-full { 
    python D:\AI\.miss_minute\miss_minute.py --full 
}

function mm-daemon { 
    python D:\AI\.miss_minute\miss_minute.py --daemon 
}

function ob1 {
    Set-Location "D:\AI\ob1-scout"
    code .
    mm-focus
}

function rooting {
    Set-Location "D:\AI\rooting-future-demo\RootingFuture\rooting-future"
    code .
}

Write-Host "⏰ Miss Minute aliases loaded. Comandi: mm, mm-focus, mm-full, ob1, rooting" -ForegroundColor Cyan
