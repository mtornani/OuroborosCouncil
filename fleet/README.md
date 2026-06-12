# 🐍 Ouroboros Fleet

**La tua flotta personale di agenti AI, che gira interamente sul telefono.**

Una PWA (web app installabile) senza backend: apri il sito dal telefono, lo
installi sulla home come un'app, e parli con i tuoi agenti AI personalizzati.
Le chiamate vanno **direttamente** dal tuo telefono al provider AI che scegli —
nessun server intermedio, nessun dato che passa da terzi. Le tue chiavi API
restano salvate **solo sul tuo dispositivo** (`localStorage`).

Sfrutta i **tier gratuiti ufficiali** dei provider AI: registri il tuo account,
copi la chiave, la incolli nell'app. Punto.

---

## 📲 Come averla sul telefono (3 minuti)

### Opzione A — GitHub Pages (consigliata, HTTPS automatico)
1. Su GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. Fai il push (il workflow `deploy-fleet.yml` pubblica la cartella `fleet/`).
3. Apri sul telefono l'URL che compare in Actions
   (`https://<utente>.github.io/<repo>/`).
4. **Android/Chrome:** menu ⋮ → *Installa app / Aggiungi a schermata Home*.
   **iPhone/Safari:** Condividi → *Aggiungi a Home*.
5. Ora hai l'icona 🐍 sulla home: si apre a tutto schermo come un'app vera.

### Opzione B — Provala subito sul PC
```bash
cd fleet
python3 -m http.server 8000
# apri http://localhost:8000
```
(Per usarla dal telefono sulla stessa rete: `http://IP-DEL-PC:8000`. Il service
worker richiede `https` o `localhost`; su GitHub Pages funziona tutto.)

---

## 🚀 Uso

1. **Tab Provider** → scegli un provider gratis (es. Groq o Gemini), tocca
   *"Ottieni chiave →"*, registrati, copia l'API key e incollala. Salva.
2. **Tab Flotta** → trovi 4 agenti pronti (Architetto, Analista, Tattico, Coder).
   Tocca **＋** per crearne di nuovi: nome, emoji, provider, modello, temperatura
   e **system prompt** (la personalità). Tocca un agente per chattarci.
3. **Tab Council** → seleziona più agenti e dai un task: rispondono in sequenza,
   ognuno vede cosa hanno detto i precedenti (è l'Ouroboros Council, in tasca).
4. **Tab Setup** → backup/ripristino della configurazione e pulizia chat.

---

## 🎁 Provider con tier GRATUITO (giugno 2026)

Tutti OpenAI-compatible, quindi l'app li usa con un unico client.

| Provider | Gratis | Carta? | Note |
|---|---|---|---|
| **Google Gemini** | 1.500 req/giorno, 1M contesto | No | Il più capace a costo zero |
| **Groq** | ~30 req/min, ~14.400/giorno | No | Il più veloce |
| **Cerebras** | tier gratuito, ~2000 tok/s | No | Velocissimo |
| **OpenRouter** | modelli `:free`, ~20 req/min | No | Decine di modelli, 1 chiave |
| **Mistral** | 1 mld token/mese, 2 req/min | Tel. | Tutti i modelli Mistral |
| **NVIDIA NIM** | ~1.000 crediti, 80+ modelli | No | `build.nvidia.com` |
| **GitHub Models** | ~10-15 req/min | No | Basta l'account GitHub |
| **Cohere** | ~1.000 chiamate/mese | No | Orientato a RAG |
| **Hugging Face** | crediti mensili gratis | No | Migliaia di modelli open |
| **DeepSeek** | token gratis allo signup | No | Reasoning economico |
| **Together AI** | crediti + modelli `-Free` | No | |
| **Cloudflare Workers AI** | 10.000 Neuron/giorno | No | Serve Account ID |

> ⚠️ I limiti dei tier gratuiti cambiano spesso, senza preavviso. Verifica
> sempre sui link *"Limiti/docs"* dentro l'app.

### ⚖️ Uso corretto (leggi)
- Usa **una chiave personale per provider**. Sono tier gratuiti **ufficiali**.
- **Niente** account multipli / chiavi usa-e-getta per aggirare i limiti: viola
  i Termini di Servizio dei provider e porta al ban. L'app non lo fa e non lo
  incoraggia.
- Le chiavi restano sul tuo telefono. Se fai il backup JSON, contiene le chiavi:
  custodiscilo.

---

## 🛠️ Note tecniche

- **CORS:** quasi tutti i provider accettano chiamate dirette dal browser. I due
  segnati con ⚠ (GitHub Models, Cloudflare) potrebbero bloccare il browser; in
  quel caso serve un piccolo proxy (es. una Cloudflare Worker) — non incluso per
  tenere tutto client-side.
- **Aggiungere un provider:** è una voce in `providers.js` (basta `baseUrl`
  OpenAI-compatible, `signup`, e qualche `model`).
- **Stack:** HTML/CSS/JS puro, zero dipendenze, zero build. Service worker per
  avvio offline della UI.
