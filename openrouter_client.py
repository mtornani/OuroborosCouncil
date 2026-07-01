"""Client HTTP condiviso verso OpenRouter.

Estratto da visual_council_app.py cosi' sia il Council (Analista/Tattico)
sia il motore di discovery (radar) usano la stessa plumbing senza duplicarla.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "https://mirko-tornani-ai-lab.com",
    "X-Title": "Mirko Ouroboros Council",
    "Content-Type": "application/json",
}


def get_available_models():
    """Recupera e filtra i modelli live su OpenRouter (solo :free, solo testo).

    Verificato dal vivo prima di fidarsene: tra i modelli ":free" c'erano
    anche generatori musicali/audio (es. google/lyria-3-pro-preview, output
    modality "audio") che rispondevano con testo senza senso a un prompt di
    chat normale. Il filtro su output_modalities == ["text"] li esclude -
    23 modelli testuali su 25 "free" nel campione verificato."""
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", headers=HEADERS, timeout=15)
        if res.status_code != 200:
            return []
        models_data = res.json().get("data", [])
        filtered_free = []
        for m in models_data:
            mid = m["id"]
            is_free = ":free" in mid or m.get("pricing", {}).get("prompt") == "0"
            is_text_only = m.get("architecture", {}).get("output_modalities") == ["text"]
            if is_free and is_text_only:
                filtered_free.append({"id": mid, "context_length": m.get("context_length", 0)})
        return sorted(filtered_free, key=lambda x: x["context_length"], reverse=True)[:30]
    except Exception:
        return []


def call_openrouter(model, system_prompt, user_message, chat_history=None):
    if not chat_history:
        chat_history = []
    messages = [{"role": "system", "content": system_prompt}] + chat_history + [
        {"role": "user", "content": user_message}
    ]
    data = {"model": model, "messages": messages, "temperature": 0.5}
    res = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=HEADERS,
        data=json.dumps(data),
        timeout=60,
    )
    if res.status_code == 200:
        return res.json()["choices"][0]["message"]["content"]

    error_msg = res.text
    try:
        err_data = res.json()
        if "error" in err_data and "message" in err_data["error"]:
            error_msg = err_data["error"]["message"]
    except Exception:
        pass
    raise Exception(f"HTTP {res.status_code} - {error_msg}")
