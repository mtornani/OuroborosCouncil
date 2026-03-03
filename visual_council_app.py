import os
import json
import requests
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
HEADERS = {
    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
    "HTTP-Referer": "https://mirko-tornani-ai-lab.com",
    "X-Title": "Mirko Ouroboros Council",
    "Content-Type": "application/json"
}

def get_available_models():
    """Recupera e filtra i modelli live su OpenRouter."""
    try:
        res = requests.get("https://openrouter.ai/api/v1/models", headers=HEADERS)
        if res.status_code == 200:
            models_data = res.json().get('data', [])
            # Prendiamo SOLO i modelli gratuiti per aggirare il problema del credito
            filtered_free = []
            for m in models_data:
                mid = m['id']
                if ":free" in mid or m.get('pricing', {}).get('prompt') == "0":
                    filtered_free.append({"id": mid, "context_length": m.get('context_length', 0)})
            
            sorted_models = sorted(filtered_free, key=lambda x: x['context_length'], reverse=True)[:30]
            return sorted_models
        return []
    except:
        return []

def call_openrouter(model, system_prompt, user_message, chat_history=None):
    if not chat_history: chat_history = []
    messages = [{"role": "system", "content": system_prompt}] + chat_history + [{"role": "user", "content": user_message}]
    data = {"model": model, "messages": messages, "temperature": 0.5}
    res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=HEADERS, data=json.dumps(data))
    if res.status_code == 200:
        return res.json()['choices'][0]['message']['content']
    else:
        # Tenta di restituire il JSON di errore se presente
        error_msg = res.text
        try:
            err_data = res.json()
            if 'error' in err_data and 'message' in err_data['error']:
                error_msg = err_data['error']['message']
        except: pass
        raise Exception(f"HTTP {res.status_code} - {error_msg}")

@app.route("/")
def index():
    if not OPENROUTER_API_KEY:
        return "<h1>Errore: Chiave API OpenRouter mancante nel file .env.</h1>", 500
    return render_template("council.html")

@app.route("/api/orchestrate", methods=["POST"])
def orchestrate():
    data = request.json
    topic = data.get("topic", "")
    
    models = get_available_models()
    if not models:
        return jsonify({
            "status": "error", 
            "message": "Nessun modello :free trovato online o errore API.",
        })
        
    model_list_text = "\n".join([f"- {m['id']} (Ctx: {m['context_length']})" for m in models])
    
    # Costringo l'Architetto a usare un modello gratis noto se non si fida, per non bloccarsi
    orchestrator_model = "google/gemini-2.0-flash-lite-preview-02-05:free" 
    sys_prompt = '''Sei l'ARCHITETTO del sistema. Scegli due modelli (analyst_model e tactician_model) dalla lista. 
Analyst: perfetto per calcoli rigidi. Tactician: forte su analisi logico/spaziale e ragionamento profondo.
Rispondi SOLO in JSON con gli ESATTI ID forniti: {"analyst_model": "...", "tactician_model": "..."}'''
    
    user_prompt = f"TASK: {topic}\n\nMODELLI ATTUALMENTE ONLINE:\n{model_list_text}"
    
    try:
        res = call_openrouter(orchestrator_model, sys_prompt, user_prompt)
        clean_json = res.replace("```json", "").replace("```", "").strip()
        decision = json.loads(clean_json)
        return jsonify({
            "status": "success",
            "analyst": decision.get("analyst_model", "google/gemini-1.5-pro"),
            "tactician": decision.get("tactician_model", "anthropic/claude-3.5-sonnet")
        })
    except Exception as e:
        # Fallback se le API vanno in errore / credito esaurito, ecc...
        return jsonify({
            "status": "error", 
            "message": str(e),
            "analyst": "google/gemini-1.5-pro",
            "tactician": "anthropic/claude-3.5-sonnet"
        })

@app.route("/api/analyst", methods=["POST"])
def run_analyst():
    data = request.json
    try:
        report = call_openrouter(
            data["model"], 
            "Sei l'Analista. Analizza i dati associati al topic. Sii iper-razionale e numerico (nessuna divagazione emotiva). Crea un report pulito e ben strutturato.", 
            data["topic"]
        )
        return jsonify({"status": "success", "report": report})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/tactician", methods=["POST"])
def run_tactician():
    data = request.json
    try:
        prompt = f"Report dell'Analista sul topic '{data['topic']}':\n\n{data['analyst_report']}\n\nCerca i punti deboli o le considerazioni mancanti nell'analisi. Dammi un verdetto tattico duro e diretto."
        report = call_openrouter(
            data["model"], 
            "Sei il Tattico (L'Avvocato del Diavolo). Smonta le certezze del report e trova le implicazioni collaterali o strategiche di alto livello. Usa punti elenco.", 
            prompt
        )
        return jsonify({"status": "success", "report": report})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route("/api/correct", methods=["POST"])
def correct_tactician():
    data = request.json
    try:
        chat_history = [{"role": "assistant", "content": data["old_report"]}]
        prompt = f"Il Direttore Mirko (Man-in-the-Loop) ha rifiutato la tua ultima analisi e ORDINA: '{data['feedback']}'. Adeguati istantaneamente e rifai le conclusioni seguendo la direttiva applicandola ai dati originali."
        report = call_openrouter(
            data["model"], 
            "Sei il Tattico (L'Avvocato del Diavolo). Segui ciecamente gli ordini del tuo Direttore.", 
            prompt,
            chat_history
        )
        return jsonify({"status": "success", "report": report})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

if __name__ == "__main__":
    import socket
    app.run(host="0.0.0.0", port=8081, debug=True)
