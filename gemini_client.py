"""Client HTTP verso Gemini (Google AI Studio, free tier) - usa l'endpoint
OpenAI-compatibile di Google cosi' il formato richiesta/risposta e' identico
a openrouter_client.py/nvidia_client.py (verificato dal vivo prima di
scriverlo, stessa disciplina degli altri due provider).

Verificato dal vivo anche quali modelli sono davvero abilitati su questo
account: gemini-2.0-flash e gemini-2.0-flash-lite hanno dato 429 con
"limit: 0" (free tier non abilitata per quei modelli su questo progetto,
non un rate limit temporaneo), gemini-1.5-flash e' deprecato (404). Solo
gemini-2.5-flash risponde per davvero - stessa regola di NVIDIA_MODELS:
tenere solo cio' che una vera chiamata ha confermato.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"
HEADERS = {
    "Authorization": f"Bearer {GEMINI_API_KEY}",
    "Content-Type": "application/json",
}

VERIFIED_MODELS = [
    "gemini-2.5-flash",
]


def get_available_models():
    if not GEMINI_API_KEY:
        return []
    return [{"id": m, "context_length": 0} for m in VERIFIED_MODELS]


def call_gemini(model, system_prompt, user_message, chat_history=None):
    if not chat_history:
        chat_history = []
    messages = [{"role": "system", "content": system_prompt}] + chat_history + [
        {"role": "user", "content": user_message}
    ]
    data = {"model": model, "messages": messages, "temperature": 0.5}
    # 45s: vedi commento gemello in openrouter_client - nel fallback un
    # modello morto costa un timeout intero prima di passare al prossimo
    res = requests.post(
        f"{GEMINI_BASE_URL}/chat/completions",
        headers=HEADERS,
        data=json.dumps(data),
        timeout=45,
    )
    if res.status_code == 200:
        return res.json()["choices"][0]["message"]["content"]

    error_msg = res.text
    try:
        err_data = res.json()
        if "error" in err_data:
            error_msg = err_data["error"].get("message", error_msg)
    except Exception:
        pass
    raise Exception(f"HTTP {res.status_code} - {error_msg}")
