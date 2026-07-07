import os
import re
import json
import time
import threading
from flask import Flask, render_template, request, jsonify

from openrouter_client import OPENROUTER_API_KEY, call_openrouter, get_available_models
import discovery_engine

app = Flask(__name__)


@app.after_request
def no_html_cache(resp):
    """Le pagine (turno/radar/mappa/processo) non vanno tenute in cache dal
    browser: da mobile Chrome serviva la copia vecchia del template anche
    dopo un deploy nuovo, facendo "sparire" le modifiche appena messe online
    (verificato dal vivo: il contraddittorio non compariva perche' il
    turno.html era quello cachato di un round precedente). no-store forza il
    browser a riscaricare l'HTML ogni volta - le pagine sono piccole, e le
    risposte JSON delle API non sono toccate."""
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store, max-age=0"
    return resp

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


@app.route("/turno")
def turno_page():
    return render_template("turno.html")


@app.route("/mappa")
def mappa_page():
    return render_template("mappa.html")


@app.route("/processo")
def processo_page():
    return render_template("processo.html")


@app.route("/sw.js")
def service_worker():
    # servito dalla ROOT (non da /static) apposta: un service worker controlla
    # solo il suo scope e quello di sotto - da /static/sw.js non governerebbe
    # le pagine dell'app. Da qui lo scope e' "/", copre tutto.
    resp = app.send_static_file("sw.js")
    resp.headers["Content-Type"] = "application/javascript"
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


# Una scansione completa (Wikidata + Wikipedia + buzz + fino a 15 dossier AI
# a 4 chiamate sequenziali ciascuno) puo' richiedere diversi minuti - troppo
# per stare dentro una singola request HTTP sincrona: il worker gunicorn
# (--timeout 120) la ammazza a meta', il client vede la connessione cadere e
# fetch() lo riporta come "TypeError: Failed to fetch" anche se il codice
# funziona (verificato dal vivo: curl sulla stessa route restava appeso
# senza risposta oltre i 150s). Girare il refresh in un thread di sfondo e
# far fare polling al client elimina il limite di tempo della request.
_radar_job_lock = threading.Lock()
_radar_job = {"status": "idle", "result": None, "message": None, "started_at": None}

# Una scansione sana finisce in minuti, non in ore. Se il flag "running"
# resta appeso oltre questo limite la scansione va considerata morta -
# tipicamente un thread di sfondo affamato di CPU su Cloud Run (revisione
# senza --no-cpu-throttling) o un'istanza riciclata a meta' turno. Senza
# questa scadenza il flag bloccato in memoria impedisce IN ETERNO ogni nuova
# scansione (verificato dal vivo: 19h a "running" con zero scritture, e ogni
# nuovo Aggiorna respinto con "already_running" finche' non si riavvia il
# container).
_RADAR_JOB_MAX_SECONDS = 15 * 60


def _radar_job_is_stale(job):
    return (
        job["status"] == "running"
        and job.get("started_at") is not None
        and (time.time() - job["started_at"]) > _RADAR_JOB_MAX_SECONDS
    )


def _run_radar_job(profile):
    try:
        result = discovery_engine.refresh_radar(profile)
        with _radar_job_lock:
            _radar_job["status"] = "done"
            _radar_job["result"] = result
            _radar_job["message"] = None
    except Exception as e:
        with _radar_job_lock:
            _radar_job["status"] = "error"
            _radar_job["result"] = None
            _radar_job["message"] = str(e)


@app.route("/api/radar/refresh", methods=["POST"])
def radar_refresh():
    data = request.json or {}
    profile = data.get("profile", "tactical_profile")
    with _radar_job_lock:
        if _radar_job["status"] == "running" and not _radar_job_is_stale(_radar_job):
            return jsonify({"status": "already_running"})
        _radar_job["status"] = "running"
        _radar_job["result"] = None
        _radar_job["message"] = None
        _radar_job["started_at"] = time.time()
    threading.Thread(target=_run_radar_job, args=(profile,), daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/api/radar/refresh/status")
def radar_refresh_status():
    with _radar_job_lock:
        if _radar_job_is_stale(_radar_job):
            # scansione appesa oltre il limite: la si dichiara fallita, cosi'
            # il client smette di girare a vuoto e l'utente puo' rilanciare
            # subito (invece di restare bloccato su "already_running").
            _radar_job["status"] = "error"
            _radar_job["message"] = ("La scansione precedente si e' bloccata oltre il limite "
                                     "di tempo ed e' stata annullata. Premi Aggiorna per riprovare.")
            _radar_job["started_at"] = None
        job = dict(_radar_job)
    if job["status"] == "done":
        return jsonify({"status": "success", **job["result"]})
    if job["status"] == "error":
        return jsonify({"status": "error", "message": job["message"]})
    return jsonify({"status": job["status"]})


@app.route("/api/radar/feed")
def radar_feed():
    try:
        feed = discovery_engine.latest_feed()
        cfg = discovery_engine.load_config()
        watchlist = discovery_engine.get_watchlist()
        results = []
        for candidate_id, record in feed.items():
            if not record or not record.get("history"):
                continue
            last = record["history"][-1]
            identity = record.get("identity") or {}
            results.append({
                "candidate_id": candidate_id,
                "name": identity.get("name"),
                "club": identity.get("club"),
                "role": identity.get("role"),
                "dob": identity.get("dob"),
                "tier": identity.get("tier"),
                "nationality_label": identity.get("nationality_label"),
                "source": identity.get("source"),
                "signal_score": last.get("signal_score"),
                "components": last.get("components"),
                "fit_score": last.get("fit_score"),
                "partial_data": last.get("partial_data"),
                "profile_used": last.get("profile_used"),
                "run_at": last.get("run_at"),
                "curve": last.get("curve"),
                "caveats": discovery_engine.player_caveats(
                    last, discovery_engine.bayesian_estimate(record["history"], cfg), identity, cfg),
                "dossier": record.get("dossier"),
                "bayesian": discovery_engine.bayesian_estimate(record["history"], cfg),
                "watchlisted": candidate_id in watchlist,
            })
        total = len(results)
        # Cap del payload: la pool e' nell'ordine delle migliaia (3400+), ma
        # spedire e disegnare tutte le schede su mobile blocca il telefono e
        # fa fallire il fetch su connessioni ballerine. Si ordina per signal
        # score (oggettivo, indipendente dal profilo, cosi' nessun profilo
        # resta svantaggiato dal taglio) e si tengono i primi N - il resto e'
        # coda lunga (spesso "dati parziali" senza dossier) non azionabile.
        # ?limit=all per chi vuole tutto (uso da desktop, non da campo).
        limit_arg = (request.args.get("limit") or "").strip()
        results.sort(key=lambda r: r["signal_score"] if r["signal_score"] is not None else -1, reverse=True)
        if limit_arg != "all":
            try:
                limit = int(limit_arg)
            except ValueError:
                limit = 300
            results = results[:max(1, limit)]
        return jsonify({
            "status": "success",
            "results": results,
            "total_count": total,
            "shown_count": len(results),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/radar/turno")
def radar_turno():
    """IL TURNO: solo i candidati con un cambiamento di stato rilevato
    nell'ultimo refresh (discovery_engine.detect_state_change), non l'intera
    pool - vedi radar_config.yaml sezione state_change. Chi non ha nulla di
    cambiato resta silenzioso in archivio (conteggiato in skipped_count, mai
    restituito)."""
    try:
        feed = discovery_engine.latest_feed()
        cfg = discovery_engine.load_config()
        watchlist = discovery_engine.get_watchlist()
        cases = []
        skipped = 0
        for candidate_id, record in feed.items():
            if not record or not record.get("history"):
                continue
            last = record["history"][-1]
            change = last.get("state_change")
            if not change:
                skipped += 1
                continue
            identity = record.get("identity") or {}
            giudice = (record.get("dossier") or {}).get("giudice") or {}
            cases.append({
                "candidate_id": candidate_id,
                "name": identity.get("name"),
                "club": identity.get("club"),
                "role": identity.get("role"),
                "dob": identity.get("dob"),
                "tier": identity.get("tier"),
                "nationality_label": identity.get("nationality_label"),
                "signal_score": last.get("signal_score"),
                "components": last.get("components"),
                "fit_score": last.get("fit_score"),
                "partial_data": last.get("partial_data"),
                "run_at": last.get("run_at"),
                "bayesian": discovery_engine.bayesian_estimate(record["history"], cfg),
                "change": change,
                "curve": last.get("curve"),
                # il percorso reale delle fasi nel tempo: rende la salita
                # leggibile e animabile, invece di un pallino fermo
                "curve_trail": discovery_engine.phase_trail(record),
                # IL CONTRADDITTORIO: motivi oggettivi per dubitare di questo
                # segnale, calcolati dai dati del giocatore (non dall'AI)
                "caveats": discovery_engine.player_caveats(
                    last, discovery_engine.bayesian_estimate(record["history"], cfg), identity, cfg),
                # la voce scettica dello swarm su questo giocatore, se c'e'
                "scettico": (record.get("dossier") or {}).get("scettico"),
                "watchlisted": candidate_id in watchlist,
                "verdict": {
                    "vale_la_pena": giudice.get("vale_la_pena"),
                    "confidence": giudice.get("confidence"),
                    "motivazione": giudice.get("motivazione"),
                },
            })
        # priorita': il decollo imminente (Layer E) e' IL caso per cui il
        # radar esiste e apre sempre il turno; poi i fatti verificati (club)
        # e gli eventi di finestra (crossing/velocity), le chiusure spiegate,
        # poi le statistiche
        priority = {"takeoff": 0, "club": 1, "mainstream": 2, "early": 2,
                    "closed_crossed": 3, "closed_faded": 3, "closed_stale": 3,
                    "verdict": 4, "resolved": 5, "rising": 6, "falling": 6, "new": 7}
        cases.sort(key=lambda c: (priority.get(c["change"]["type"], 9), -(c["signal_score"] or 0)))
        return jsonify({
            "status": "success",
            "cases": cases,
            "skipped_count": skipped,
            "total_count": len(feed),
            # registro di validazione retroattiva: quanti passaggi al
            # mainstream sono stati registrati finora, e quanti il radar
            # aveva anticipato con un "decollo imminente" - l'onesta' del
            # rilevatore misurata sui fatti, mostrata in home
            "curve_validation": discovery_engine.curve_validation_summary(),
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/radar/mappa")
def radar_mappa():
    """LA MAPPA: posizione sulla curva di adozione di tutti i giocatori con
    storico sufficiente, per la vista d'insieme del portale. Chi non ha
    ancora abbastanza scansioni non viene posizionato (solo contato) - vedi
    discovery_engine.curve_map_snapshot."""
    try:
        return jsonify({"status": "success", **discovery_engine.curve_map_snapshot()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/radar/processo")
def radar_processo():
    """IL PROCESSO / l'avvocato del diavolo: il tabellone onesto del
    rilevatore (precisione e richiamo, fallimenti compresi) - vedi
    discovery_engine.track_record_summary. Le obiezioni sono contenuto
    statico nel template, non dati a runtime."""
    try:
        return jsonify({"status": "success", **discovery_engine.track_record_summary()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/radar/health")
def radar_health():
    """Controllo di persistenza: dice se lo storico vive davvero su Postgres
    (durevole) o su file effimero - vedi discovery_engine.persistence_status.
    Aprilo una volta dopo il deploy per confermare che Neon riceve i dati."""
    try:
        return jsonify({"status": "success", "persistence": discovery_engine.persistence_status()})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/api/radar/watchlist", methods=["POST"])
def radar_watchlist():
    """Aggiunge/toglie un candidato dalla watchlist persistita - l'azione
    vive sulla scheda del giocatore (bottone "segna"), non in un file di
    config da editare a mano. Distinta da candidate_sources.manual_watchlist
    in radar_config.yaml, che resta per la curatela statica di Mirko."""
    data = request.json or {}
    candidate_id = data.get("candidate_id")
    watchlisted = bool(data.get("watchlisted"))
    if not candidate_id:
        return jsonify({"status": "error", "message": "candidate_id mancante"})
    try:
        discovery_engine.set_watchlisted(candidate_id, watchlisted)
        return jsonify({"status": "success", "candidate_id": candidate_id, "watchlisted": watchlisted})
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
