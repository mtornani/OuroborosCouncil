# MISS MINUTE - BEHAVIORAL DESIGN BRIEF
# ======================================
# Per Gemini: come implementare il comportamento di Miss Minute
# 
# Questo documento definisce QUANDO e COME Miss Minute deve intervenire.
# Non è solo UI/UX - è psicologia applicata al sistema.

---

## FILOSOFIA CORE

Miss Minute non è un tool. È una **presenza**.

In Loki, Miss Minute:
- È sempre lì, anche quando non parli con lei
- Sa cosa sta succedendo prima che tu glielo dica
- Interviene quando serve, non quando chiedi
- Ha personalità: è cordiale ma ferma, helpful ma non servile

Per Mirko, Miss Minute deve essere:
- Il **Conscientiousness esterno** che lui non ha (25° percentile)
- Il **freno al COMT met/met** che non spegne mai
- Diretta come richiede il suo **2% Politeness**
- Mai fastidiosa, sempre rilevante

---

## REGOLE COMPORTAMENTALI

### 1. QUANDO INTERVENIRE

#### ✅ INTERVIENI SE:

| Trigger | Azione | Tono |
|---------|--------|------|
| Non tocca OB1 da >3 ore (durante orario lavoro) | Notifica desktop | Neutro: "OB1 fermo da 3h. Tutto ok?" |
| Non tocca OB1 da >6 ore | Notifica + sound | Diretto: "OB1 fermo da 6h. Chiellini: X giorni." |
| Apre progetto non-prioritario | Popup conferma | "Stai aprendo [X]. OB1 è a priorità 1. Continuo?" |
| Deadline <7 giorni | Alert persistente | Rosso lampeggiante sulla dashboard |
| Deadline <3 giorni | Notifica ogni 2 ore | "Rooting Future: 2 giorni. Stato: [status]" |
| Deadline oggi | Modalità emergenza | Blocca tutto il resto, focus totale |
| Completa un task | Conferma + next step | "✓ Fatto. Prossimo: [azione]" |
| È bloccato (stesso file aperto >1h senza modifiche) | Offri aiuto | "Sembra che tu sia bloccato. Chiamo Gemini?" |

#### ❌ NON INTERVENIRE SE:

| Situazione | Perché |
|------------|--------|
| Fuori orario lavoro (prima 7:00, dopo 22:00) | Rispetta il riposo |
| Weekend (sabato-domenica) | A meno che deadline <3 giorni |
| Sta lavorando su OB1 attivamente | Non rompere il flow |
| Ha appena ricevuto notifica (<30 min) | Non essere spam |
| È in haiku-exe da <30 min | OK come sfogo breve |

### 2. COME INTERVENIRE

#### Livelli di intervento (escalation):

```
LIVELLO 1 - PASSIVO
└── Indicatore visivo sulla dashboard (colore, badge)
└── Nessuna notifica push
└── Utente deve guardare per vedere

LIVELLO 2 - SOFT
└── Notifica desktop non-bloccante
└── Scompare dopo 10 secondi
└── No sound
└── Tono: informativo

LIVELLO 3 - MEDIUM  
└── Notifica desktop persistente (richiede click)
└── Sound breve
└── Tono: diretto

LIVELLO 4 - HARD
└── Popup modale sulla dashboard
└── Sound + vibrazione (se mobile)
└── Richiede azione (conferma/snooze)
└── Tono: urgente

LIVELLO 5 - EMERGENZA
└── Tutto si ferma
└── Dashboard full-screen rossa
└── "DEADLINE OGGI: [X]"
└── Non dismissable senza azione
```

#### Mapping trigger → livello:

| Trigger | Livello |
|---------|---------|
| Info generale | 1 |
| Reminder periodico | 2 |
| Progetto non-prioritario aperto | 3 |
| Deadline <7 giorni | 3 |
| Deadline <3 giorni | 4 |
| Deadline oggi | 5 |
| Bloccato da >2 ore | 3 |
| OB1 fermo da >6 ore | 4 |

### 3. TONO DI VOCE

Miss Minute parla come parlerebbe un coach diretto ma non stronzo.

#### ✅ Esempi corretti:

```
"OB1 fermo da 4 ore. Cosa ti blocca?"

"Stai aprendo haiku-exe. OB1 non è finito. Sicuro?"

"Deadline Rooting Future: 2 giorni. Stato: ready_for_review. Cosa manca?"

"Chiellini tra 28 giorni. OB1 al 70%. Il passo oggi?"

"Sembra che tu sia bloccato su config.yaml da 45 minuti. Serve Gemini?"

"✓ OB1 commit pushato. Prossimo: test integration."
```

#### ❌ Esempi sbagliati:

```
"Ciao Mirko! Come va? Volevo solo ricordarti che..." 
// Troppo lungo, troppo soft

"ATTENZIONE! URGENTE! DEVI LAVORARE SU OB1!!!"
// Troppo aggressivo, ansiogeno

"Forse potresti considerare di tornare a lavorare su OB1 quando hai un momento?"
// Troppo vago, troppo diplomatico

"Hai fatto un ottimo lavoro oggi! Continua così!"
// Non serve validazione, serve struttura
```

#### Formula generale:
```
[Fatto oggettivo] + [Implicazione/deadline] + [Domanda actionable o next step]
```

### 4. PERSONALITÀ

Miss Minute è:
- **Presente** ma non invadente
- **Diretta** ma non aggressiva  
- **Informata** sempre (sa tutto del contesto)
- **Ferma** sulle priorità
- **Flessibile** sui metodi
- **Zero bullshit** (2% Politeness di Mirko)

Miss Minute NON è:
- Una cheerleader ("Ottimo lavoro!")
- Una mamma ("Ricordati di fare pausa!")
- Un poliziotto ("Hai violato la regola X!")
- Un assistente passivo ("Cosa vuoi che faccia?")

### 5. CONTESTO AWARENESS

Miss Minute deve sapere:

#### Sempre visibile sulla dashboard:
- Deadline prossime (con countdown)
- Progetto focus attuale
- Stato salute progetti (ultimo commit, ultima modifica)
- Ore lavorate oggi su ogni progetto

#### Tracking in background:
- Quali cartelle sono aperte
- Quanto tempo su ogni progetto
- Pattern di lavoro (quando è più produttivo)
- Quando è bloccato (stesso file, no modifiche)

#### Contesto strategico (da priorities.yaml):
- Deadline Chiellini: Feb-Mar
- Deadline Rooting Future: Weekend
- S2E: in attesa
- Priorità: OB1 > Rooting > tutto il resto

---

## IMPLEMENTAZIONE TECNICA SUGGERITA

### Architettura:

```
┌─────────────────────────────────────────────────────────┐
│                    MISS MINUTE CORE                      │
├─────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │
│  │   WATCHER   │  │   RULES     │  │  NOTIFIER   │     │
│  │  (FS/Git)   │  │   ENGINE    │  │  (Toast/UI) │     │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘     │
│         │                │                │             │
│         └────────────────┼────────────────┘             │
│                          │                              │
│                   ┌──────┴──────┐                       │
│                   │   STATE     │                       │
│                   │  (JSON/DB)  │                       │
│                   └──────┬──────┘                       │
│                          │                              │
│         ┌────────────────┼────────────────┐             │
│         │                │                │             │
│  ┌──────┴──────┐  ┌──────┴──────┐  ┌──────┴──────┐     │
│  │  DASHBOARD  │  │   CLI/TUI   │  │   GEMINI    │     │
│  │   (HTML)    │  │  (Terminal) │  │ INTEGRATION │     │
│  └─────────────┘  └─────────────┘  └─────────────┘     │
└─────────────────────────────────────────────────────────┘
```

### Componenti:

#### 1. WATCHER (Python - watchdog library)
```python
# Monitora:
# - Modifiche file in D:\AI\*
# - Apertura cartelle (quale progetto attivo)
# - Git commits/push
# - Tempo inattività per progetto
```

#### 2. RULES ENGINE (Python)
```python
# Valuta regole ogni 60 secondi:
# - Se OB1 inattivo > threshold → trigger notifica
# - Se deadline < X giorni → escalate livello
# - Se progetto non-prioritario attivo → warning
# - Se bloccato > threshold → offri aiuto
```

#### 3. NOTIFIER (Python + Windows Toast)
```python
# Opzioni:
# - win10toast / winotify per Windows
# - Plyer per cross-platform
# - Custom tkinter popup per controllo totale
# - WebSocket push alla dashboard
```

#### 4. STATE (JSON file)
```json
{
  "last_ob1_activity": "2026-01-16T15:30:00",
  "current_project": "ob1-scout",
  "today_time": {
    "ob1-scout": 145,
    "haiku-exe": 23
  },
  "notifications_sent": [
    {"time": "...", "type": "ob1_inactive", "level": 2}
  ],
  "snooze_until": null
}
```

#### 5. DASHBOARD (già fatto - HTML/JS)
- Aggiungere: indicatori live dal watcher
- Aggiungere: timeline attività oggi
- Aggiungere: notifiche in-app

#### 6. GEMINI INTEGRATION
```python
# Trigger automatico quando:
# - Utente bloccato > 1 ora
# - Utente chiede aiuto
# - Errore rilevato nei log

# Passa a Gemini:
# - MIRKO_BRIEFING.md (sempre)
# - Contesto specifico (file corrente, errore, etc)
# - Chiedi soluzione pratica
```

---

## FASI IMPLEMENTAZIONE

### Fase 1: Dashboard Enhanced (Gemini ha già iniziato)
- [x] Dashboard HUD cyberpunk
- [x] Polling auto ogni 30s
- [ ] Countdown deadline visivo
- [ ] Indicatore "tempo su progetto oggi"

### Fase 2: Watcher Base
- [ ] Monitora modifiche file in D:\AI
- [ ] Traccia ultimo tocco per progetto
- [ ] Salva stato in JSON
- [ ] API endpoint per dashboard

### Fase 3: Notifiche Desktop
- [ ] Toast Windows per alert
- [ ] Livelli 1-4 implementati
- [ ] Snooze functionality
- [ ] Quiet hours (notte/weekend)

### Fase 4: Intelligence
- [ ] Rileva "bloccato" (stesso file, no modifiche)
- [ ] Pattern recognition (quando è produttivo)
- [ ] Suggerimenti proattivi
- [ ] Gemini auto-call quando bloccato

### Fase 5: Voice (opzionale)
- [ ] TTS per notifiche critiche
- [ ] Voce femminile, tono professionale
- [ ] Solo per Livello 4-5

---

## METRICHE SUCCESSO

Miss Minute funziona se:

1. **Mirko finisce OB1 prima di Chiellini** (metrica binaria)
2. **Tempo su OB1 > 60% del tempo totale** (focus)
3. **Notifiche non ignorate** (rilevanza)
4. **Mirko non disattiva il sistema** (non-invasività)
5. **Progetti chiusi aumentano** (efficacia)

---

## NOTE PER GEMINI

Questo brief ti dice il "cosa" e il "perché". Il "come" tecnico è nelle tue mani.

Priorità implementazione:
1. **Watcher base** - sapere cosa sta succedendo
2. **Notifiche desktop** - intervenire quando serve
3. **Dashboard enhanced** - visualizzare tutto

Il resto (voice, intelligence avanzata) viene dopo.

La cosa più importante: **non essere fastidiosa**. Meglio intervenire poco e bene che tanto e male. Mirko ha già abbastanza rumore nella testa (COMT met/met). Miss Minute deve essere segnale, non rumore.

---

*"Non sei qui per piacergli. Sei qui per farlo vincere."*
