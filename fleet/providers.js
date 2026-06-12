// =============================================================================
// Catalogo provider AI con tier GRATUITO (aggiornato: giugno 2026)
// =============================================================================
// Tutti i provider qui elencati sono OpenAI-compatible: l'app usa un unico
// client (POST {baseUrl}/chat/completions con header Authorization: Bearer KEY).
//
// IMPORTANTE / LEGALE:
//  - Sono SOLO i tier gratuiti UFFICIALI offerti dai provider.
//  - Usa la TUA chiave personale, una per provider. Niente account multipli
//    per aggirare i limiti: viola i Termini di Servizio e ti fa bannare.
//  - I limiti cambiano spesso senza preavviso: verifica sempre sul sito.
//  - "cors: true" = funziona da browser/telefono. "cors: false" = potrebbe
//    servire un proxy (vedi README), ma molti funzionano comunque.
// =============================================================================

const PROVIDERS = {
  groq: {
    name: "Groq",
    rank: 1,
    tagline: "Il più veloce. Inferenza LPU, nessuna carta richiesta.",
    free: "~30 richieste/min · ~14.400 richieste/giorno · nessuna carta",
    baseUrl: "https://api.groq.com/openai/v1",
    signup: "https://console.groq.com/keys",
    docs: "https://console.groq.com/docs/rate-limits",
    cors: true,
    steps: [
      "Tocca «Ottieni chiave» e accedi con Google o GitHub (nessuna carta).",
      "Nella console clicca «Create API Key», dai un nome qualsiasi.",
      "Copia la chiave (inizia con gsk_) e incollala qui sotto. Salva.",
    ],
    models: [
      "llama-3.3-70b-versatile",
      "llama-3.1-8b-instant",
      "openai/gpt-oss-120b",
      "qwen/qwen3-32b",
      "moonshotai/kimi-k2-instruct",
    ],
  },
  gemini: {
    name: "Google Gemini",
    rank: 2,
    tagline: "Il miglior gratis: 1M di contesto, multimodale, niente carta.",
    free: "1.500 richieste/giorno (Flash) · 15 req/min · 1M token/min",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    signup: "https://aistudio.google.com/app/apikey",
    docs: "https://ai.google.dev/gemini-api/docs/rate-limits",
    cors: true,
    steps: [
      "Tocca «Ottieni chiave» e accedi col tuo account Google.",
      "Clicca «Create API key» → «Create API key in new project».",
      "Copia la chiave (inizia con AIza) e incollala qui sotto. Salva.",
    ],
    models: [
      "gemini-2.5-flash",
      "gemini-2.5-flash-lite",
      "gemini-flash-latest",
    ],
  },
  openrouter: {
    name: "OpenRouter",
    rank: 3,
    tagline: "Decine di modelli con una sola chiave. Cerca il suffisso :free.",
    free: "Modelli :free gratis · ~20 req/min · ~50-1000 req/giorno",
    baseUrl: "https://openrouter.ai/api/v1",
    signup: "https://openrouter.ai/keys",
    docs: "https://openrouter.ai/models?max_price=0",
    cors: true,
    steps: [
      "Tocca «Ottieni chiave» e accedi con Google/GitHub (nessuna carta).",
      "Clicca «Create Key», dai un nome e conferma.",
      "Copia la chiave (inizia con sk-or-v1-) e incollala qui sotto. Salva.",
    ],
    models: [
      "deepseek/deepseek-r1:free",
      "deepseek/deepseek-chat-v3.1:free",
      "qwen/qwen3-coder:free",
      "meta-llama/llama-3.3-70b-instruct:free",
      "openai/gpt-oss-120b:free",
    ],
  },
  cerebras: {
    name: "Cerebras",
    tagline: "Fino a ~2000 token/sec. Velocissimo, tier gratis senza scadenza.",
    free: "Tier gratuito generoso · nessuna carta",
    baseUrl: "https://api.cerebras.ai/v1",
    signup: "https://cloud.cerebras.ai/",
    docs: "https://inference-docs.cerebras.ai/support/rate-limits",
    cors: true,
    models: [
      "llama-3.3-70b",
      "llama3.1-8b",
      "qwen-3-235b-a22b-instruct-2507",
    ],
  },
  mistral: {
    name: "Mistral",
    tagline: "Tier 'Experiment' gratuito su tutti i modelli. Verifica telefono.",
    free: "2 req/min · 500K token/min · 1 miliardo token/mese",
    baseUrl: "https://api.mistral.ai/v1",
    signup: "https://console.mistral.ai/api-keys/",
    docs: "https://docs.mistral.ai/deployment/laplateforme/tier/",
    cors: true,
    models: [
      "mistral-small-latest",
      "mistral-large-latest",
      "codestral-latest",
    ],
  },
  nvidia: {
    name: "NVIDIA NIM",
    tagline: "80+ modelli gratis su build.nvidia.com. Crediti allo signup.",
    free: "~1.000 crediti allo signup (fino a 5.000 a richiesta) · ~40 req/min",
    baseUrl: "https://integrate.api.nvidia.com/v1",
    signup: "https://build.nvidia.com/settings/api-keys",
    docs: "https://build.nvidia.com/models",
    cors: true,
    models: [
      "meta/llama-3.3-70b-instruct",
      "deepseek-ai/deepseek-r1",
      "qwen/qwen2.5-coder-32b-instruct",
    ],
  },
  github: {
    name: "GitHub Models",
    tagline: "Gratis con un account GitHub. GPT, Llama, Mistral e altri.",
    free: "~10-15 req/min · ~50-150 req/giorno (in base al piano)",
    baseUrl: "https://models.github.ai/inference",
    signup: "https://github.com/settings/tokens",
    docs: "https://github.com/marketplace/models",
    cors: false,
    models: [
      "openai/gpt-4o-mini",
      "meta/Llama-3.3-70B-Instruct",
      "mistral-ai/Mistral-Small-2503",
    ],
  },
  cohere: {
    name: "Cohere",
    tagline: "Trial gratuito orientato a RAG. Endpoint OpenAI-compatible.",
    free: "~1.000 chiamate/mese (reset mensile) · nessuna carta",
    baseUrl: "https://api.cohere.ai/compatibility/v1",
    signup: "https://dashboard.cohere.com/api-keys",
    docs: "https://docs.cohere.com/docs/rate-limits",
    cors: true,
    models: [
      "command-r-08-2024",
      "command-r-plus-08-2024",
    ],
  },
  huggingface: {
    name: "Hugging Face",
    tagline: "Inference router su migliaia di modelli open. Niente carta.",
    free: "Crediti mensili gratuiti · rate-limited",
    baseUrl: "https://router.huggingface.co/v1",
    signup: "https://huggingface.co/settings/tokens",
    docs: "https://huggingface.co/docs/inference-providers",
    cors: true,
    models: [
      "meta-llama/Llama-3.3-70B-Instruct",
      "Qwen/Qwen2.5-Coder-32B-Instruct",
    ],
  },
  deepseek: {
    name: "DeepSeek",
    tagline: "Token gratuiti allo signup, poi il prezzo più basso del mercato.",
    free: "Token gratuiti iniziali allo signup",
    baseUrl: "https://api.deepseek.com",
    signup: "https://platform.deepseek.com/api_keys",
    docs: "https://api-docs.deepseek.com/",
    cors: true,
    models: ["deepseek-chat", "deepseek-reasoner"],
  },
  together: {
    name: "Together AI",
    tagline: "Crediti gratis allo signup + alcuni modelli endpoint :free.",
    free: "Crediti gratuiti iniziali · modelli '-Free'",
    baseUrl: "https://api.together.xyz/v1",
    signup: "https://api.together.ai/settings/api-keys",
    docs: "https://docs.together.ai/docs/rate-limits",
    cors: true,
    models: [
      "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
      "deepseek-ai/DeepSeek-R1-Distill-Llama-70B-free",
    ],
  },
  cloudflare: {
    name: "Cloudflare Workers AI",
    tagline: "10.000 Neuron/giorno gratis. Richiede Account ID + token.",
    free: "10.000 Neuron/giorno (reset 00:00 UTC)",
    baseUrl: "https://api.cloudflare.com/client/v4/accounts/{account}/ai/v1",
    signup: "https://dash.cloudflare.com/profile/api-tokens",
    docs: "https://developers.cloudflare.com/workers-ai/",
    cors: false,
    needsAccount: true,
    models: [
      "@cf/meta/llama-3.3-70b-instruct-fp8-fast",
      "@cf/qwen/qwen2.5-coder-32b-instruct",
    ],
  },
};

// Nota: i tier gratuiti cambiano spesso. Verifica i limiti reali sui link "docs".
