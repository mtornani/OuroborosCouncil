"""Client HTTP verso NVIDIA NIM (integrate.api.nvidia.com) - API compatibile
OpenAI, endpoint e autenticazione diversi da OpenRouter (chiave "nvapi-...").

Verificato dal vivo prima di scriverlo: non tutti i modelli del catalogo
(121 visibili via /v1/models) sono abilitati per ogni account - alcuni
danno 404 "Not found for account" anche se compaiono nel catalogo. Tenere
qui solo modelli confermati funzionanti con una vera chiamata di chat, non
l'intero catalogo.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NVIDIA_API_KEY}",
    "Content-Type": "application/json",
}

# Confermati con una chiamata di chat reale (non solo presenti nel catalogo
# /v1/models, che include anche modelli non abilitati per questo account).
VERIFIED_MODELS = [
    "meta/llama-3.1-8b-instruct",
    "meta/llama-3.1-70b-instruct",
]


def get_available_models():
    if not NVIDIA_API_KEY:
        return []
    return [{"id": m, "context_length": 0} for m in VERIFIED_MODELS]


def call_nvidia(model, system_prompt, user_message, chat_history=None):
    if not chat_history:
        chat_history = []
    messages = [{"role": "system", "content": system_prompt}] + chat_history + [
        {"role": "user", "content": user_message}
    ]
    data = {"model": model, "messages": messages, "temperature": 0.5}
    # 45s: vedi commento gemello in openrouter_client - nel fallback un
    # modello morto costa un timeout intero prima di passare al prossimo
    res = requests.post(
        f"{NVIDIA_BASE_URL}/chat/completions",
        headers=HEADERS,
        data=json.dumps(data),
        timeout=45,
    )
    if res.status_code == 200:
        return res.json()["choices"][0]["message"]["content"]

    error_msg = res.text
    try:
        err_data = res.json()
        if "detail" in err_data:
            error_msg = err_data["detail"]
    except Exception:
        pass
    raise Exception(f"HTTP {res.status_code} - {error_msg}")
