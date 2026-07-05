# ⏰ MISS MINUTE
## Sistema di Prioritizzazione Progetti per Mirko Tornani

> *"Il tempo è prezioso. Non sprecarlo sui progetti sbagliati."*

---

## 🐍 OUROBOROS RADAR — Early Adopter Player Scouting

Il modulo `scout/` applica la curva di diffusione di Rogers all'attenzione
del mercato: misura dove si trova ogni giocatore sulla curva (**ADI**),
a che velocità la sta attraversando (**Breakout Score**) e se la finestra
di vantaggio è OPEN / CLOSING / CLOSED. Run giornaliero via GitHub Actions,
alert Telegram quando una finestra si chiude, dashboard su `/radar`
nell'app deployata.

📖 **Documentazione completa: [RADAR.md](RADAR.md)** · Report live:
[RADAR_REPORT.md](RADAR_REPORT.md) · Watchlist: [players.yaml](players.yaml)

```bash
python -m scout run       # raccolta + scoring + report + alert
python -m scout status    # stato watchlist
python -m scout add "Nome Cognome" --club X --born 2008
```

---

## 🚀 Quick Start

### Opzione 1: Script Python standalone
```bash
cd D:\AI\.miss_minute
python miss_minute.py              # Status rapido
python miss_minute.py --full       # Report completo
python miss_minute.py --focus      # Solo priorità 1
python miss_minute.py --daemon     # Sempre attivo (refresh 60s)
```

### Opzione 2: PowerShell Aliases
```powershell
# Carica gli alias (aggiungi al tuo $PROFILE per averli sempre)
. D:\AI\.miss_minute\miss_minute_alias.ps1

mm          # Status rapido
mm-focus    # Focus mode
mm-full     # Report completo
ob1         # Apre ob1-scout in VS Code
rooting     # Apre rooting-future in VS Code
```

### Opzione 3: Gemini CLI con contesto completo
```powershell
# Carica il launcher
. D:\AI\.miss_minute\gemini_launcher.ps1

# Usa Miss Minute + Gemini
mmg "cosa devo fare oggi?"
mmg "aiutami a finire ob1"
mmg "sono bloccato su X"
jarvis "status"

# Modalità interattiva
mmg
```

---

## 📁 Struttura File

```
D:\AI\.miss_minute\
├── miss_minute.py          # Script principale Python
├── miss_minute.bat         # Launcher Windows
├── miss_minute_alias.ps1   # Alias PowerShell per mm, ob1, etc
├── priorities.yaml         # ⚡ CONFIGURAZIONE PRIORITÀ (modifica questo!)
├── MIRKO_BRIEFING.md       # Briefing completo per AI assistants
├── gemini_launcher.ps1     # Launcher Gemini CLI con contesto
├── gemini_miss_minute.bat  # Launcher Gemini (batch)
├── gemini_miss_minute.sh   # Launcher Gemini (bash)
├── GEMINI_PROMPT.md        # Prompt system per Gemini
├── gemini_context.py       # Context alternativo
└── README.md               # Questo file
```

---

## ⚙️ Configurazione

### priorities.yaml
Questo è il file chiave. Modificalo quando:
- Cambia una deadline
- Cambia la priorità di un progetto
- Aggiungi un nuovo progetto
- Completi un progetto

```yaml
deadlines:
  nome_deadline:
    date: "2026-02-15"
    description: "Descrizione"
    requires: ["progetto1", "progetto2"]

projects:
  nome-progetto:
    path: "D:\\AI\\nome-progetto"
    priority: 1  # 1 = massima, 6 = minima
    status: "in_progress"  # in_progress, ready, paused, blocked
    next_action: "Cosa fare dopo"
    blockers: []

focus_mode:
  enabled: true
  current_focus: "ob1-scout"
  message: "Messaggio motivazionale"
```

---

## 🎯 Filosofia

Miss Minute esiste per un motivo: **Mirko apre troppi progetti e non li chiude.**

Il sistema:
1. **Tiene traccia** di tutti i progetti in D:\AI
2. **Prioritizza** in base a deadline e obiettivi
3. **Blocca la dispersione** ricordando il focus
4. **Integra con Gemini** per assistenza intelligente

### Il briefing MIRKO_BRIEFING.md
Contiene tutto quello che un AI assistant deve sapere:
- Profilo psicologico (COMT met/met, Big Five)
- Come lavorare con Mirko (essere diretto, dare struttura)
- Contesto attuale (Chiellini, S2E, Rooting Future)
- Priorità progetti

Quando usi `mmg` o `jarvis`, Gemini riceve tutto questo contesto.

---

## 📅 Stato Attuale (Gennaio 2026)

### Deadline
| Cosa | Quando | Priorità |
|------|--------|----------|
| Rooting Future meeting | Weekend | 🔥 |
| Chiellini | Feb-Mar | ⚡ |
| S2E | TBD | 📆 |

### Focus
```
🔴 OB1-SCOUT - UNICA PRIORITÀ

Versione definitiva idra/gemini per incontro Chiellini.
Tutto il resto aspetta.
```

---

## 🔧 Setup Permanente

### Aggiungi al tuo PowerShell $PROFILE:
```powershell
# Miss Minute
. D:\AI\.miss_minute\miss_minute_alias.ps1
. D:\AI\.miss_minute\gemini_launcher.ps1
```

### Per trovare il tuo $PROFILE:
```powershell
echo $PROFILE
# Poi apri quel file e aggiungi le righe sopra
```

---

## 💡 Tips

1. **Ogni mattina**: `mm` per vedere lo status
2. **Quando sei dispersivo**: `mm-focus` per tornare sul binario
3. **Quando sei bloccato**: `mmg "sono bloccato su X, aiutami"`
4. **Quando completi qualcosa**: Aggiorna `priorities.yaml`

---

*"Non sei qui per piacergli. Sei qui per farlo vincere."*
