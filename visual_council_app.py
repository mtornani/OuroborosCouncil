import os
import re
import json
from flask import Flask, render_template, request, jsonify

from openrouter_client import OPENROUTER_API_KEY, call_openrouter, get_available_models
import discovery_engine

app = Flask(__name__)

def inject_local_files_from_prompt(text):
    """
    Super-potere: come Claude Code, Python scansiona il prompt. 
    Se incrocia un percorso valido di Windows (es. D:\\AI\\...), 
    lo legge in automatico scavalcando il browser.
    """
    # Regex per matchare D:\qualcosa o C:/qualcosa
    paths = re.findall(r'[A-Za-z]:[\\/][\w\.\-\\/]+', text)
    if not paths:
        return text
    
    injected_data = "\n\n[IL SISTEMA BACKEND HA LETTO IN AUTOMATICO LE SEGUENTI CARTELLE/FILE DAL PC]:\n"
    for path in set(paths):
        path = os.path.normpath(path)
        if not os.path.exists(path):
            continue
            
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    injected_data += f"\n--- INIZIO FILE {path} ---\n{f.read(50000)}\n--- FINE FILE ---\n"
            except: pass
        elif os.path.isdir(path):
            injected_data += f"\n=== SCANSIONE CARTELLA: {path} ===\n"
            for root, dirs, files in os.walk(path):
                # Filtri di sicurezza e token-limit
                dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'node_modules', '.venv', 'dist', 'build']]
                for file in files:
                    if file.endswith(('.txt', '.py', '.md', '.json', '.html', '.css', '.js', '.yaml', '.csv')):
                        filepath = os.path.join(root, file)
                        try:
                            with open(filepath, 'r', encoding='utf-8') as f:
                                injected_data += f"\n--- FILE {filepath} ---\n{f.read(15000)}\n"
                        except: pass
                        
    return text + injected_data


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
            "analyst": decision.get("analyst_model", "google/gemini-2.0-flash-lite-preview-02-05:free"),
            "tactician": decision.get("tactician_model", "qwen/qwen-2.5-72b-instruct:free")
        })
    except Exception as e:
        # Fallback ultra-sicuro con modelli :free se il parser fallisce per evitare l'error 400
        return jsonify({
            "status": "error", 
            "message": str(e),
            "analyst": "google/gemini-2.0-flash-lite-preview-02-05:free",
            "tactician": "x-ai/grok-2-1212" # se si ha credito, altrimenti un free forte
        })

@app.route("/api/analyst", methods=["POST"])
def run_analyst():
    data = request.json
    try:
        # MAGIC TRICK: Se Mirko ha digitato D:\... nel topic, Python legge i file locali prima di inviare ad OpenRouter
        augmented_topic = inject_local_files_from_prompt(data["topic"])
        
        report = call_openrouter(
            data["model"], 
            "Sei l'Analista. Analizza i dati associati al topic. Sii iper-razionale e numerico (nessuna divagazione emotiva). Crea un report pulito e ben strutturato.", 
            augmented_topic
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


# ============================================================
# OB1 RADAR - discovery talenti (mobile)
# ============================================================

@app.route("/radar")
def radar_page():
    return render_template("radar.html")


@app.route("/api/radar/refresh", methods=["POST"])
def radar_refresh():
    data = request.json or {}
    profile = data.get("profile", "tactical_profile")
    try:
        result = discovery_engine.refresh_radar(profile)
        return jsonify({"status": "success", **result})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/radar/feed")
def radar_feed():
    try:
        feed = discovery_engine.latest_feed()
        results = []
        for candidate_id, record in feed.items():
            if not record.get("history"):
                continue
            last = record["history"][-1]
            results.append({
                "candidate_id": candidate_id,
                "name": record["identity"].get("name"),
                "club": record["identity"].get("club"),
                "tier": record["identity"].get("tier"),
                "source": record["identity"].get("source"),
                "signal_score": last.get("signal_score"),
                "components": last.get("components"),
                "fit_score": last.get("fit_score"),
                "partial_data": last.get("partial_data"),
                "profile_used": last.get("profile_used"),
                "run_at": last.get("run_at"),
                "dossier": record.get("dossier"),
            })
        results.sort(key=lambda r: r["fit_score"] if r["fit_score"] is not None else -1, reverse=True)
        return jsonify({"status": "success", "results": results})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/radar/config")
def radar_config():
    """Sottoinsieme di radar_config.yaml serializzabile in JSON, cosi' il
    client puo' ricalcolare il Fit Score al volo quando si cambia profilo
    (chip) senza rilanciare tutta la pipeline (~30s) a ogni tap."""
    try:
        cfg = discovery_engine.load_config()
        return jsonify({
            "status": "success",
            "signal_score_weights": cfg["signal_score_weights"],
            "purpose_profiles": cfg["purpose_profiles"],
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=True, threaded=True)
