import hmac
import os
import time
import threading
from flask import Flask, render_template, request, redirect, jsonify

import discovery_engine

app = Flask(__name__)

# ============================================================
# ACCESSO - chiave condivisa opzionale
# ============================================================
# Il servizio Cloud Run e' pubblico (--allow-unauthenticated): senza questo
# gate chiunque trovi l'URL puo' lanciare scansioni a raffica (bruciando le
# quote giornaliere free di Gemini/OpenRouter/NVIDIA) o modificare la
# watchlist. Opt-in per non rompere nulla: finche' RADAR_ACCESS_KEY non e'
# impostata nell'ambiente, il comportamento e' identico a prima. Quando e'
# impostata: si apre l'app UNA volta con ?key=LACHIAVE, il browser riceve un
# cookie e da li' in poi tutto (pagine, API, PWA) funziona come sempre.
RADAR_ACCESS_KEY = os.getenv("RADAR_ACCESS_KEY", "")
_ACCESS_COOKIE = "radar_key"


@app.before_request
def _access_gate():
    if not RADAR_ACCESS_KEY:
        return  # gate spento: nessun cambiamento rispetto a prima
    # compare_digest, non ==: confronto in tempo costante, una chiave non si
    # indovina misurando i tempi di risposta
    if hmac.compare_digest(request.cookies.get(_ACCESS_COOKIE, ""), RADAR_ACCESS_KEY):
        return
    # header per i client programmatici (Cloud Scheduler, curl), query param
    # per il primo accesso dal browser
    supplied = request.headers.get("X-Radar-Key", "") or request.args.get("key", "")
    if hmac.compare_digest(supplied, RADAR_ACCESS_KEY):
        if request.path.startswith("/api/"):
            return  # chiamata API autenticata: niente redirect ne' cookie
        resp = redirect(request.path)  # togli la chiave dalla URL visibile
        resp.set_cookie(
            _ACCESS_COOKIE, RADAR_ACCESS_KEY,
            max_age=180 * 24 * 3600, httponly=True, samesite="Lax",
            secure=request.is_secure,
        )
        return resp
    return jsonify({"status": "error", "message": "Accesso negato: apri l'app con ?key=LACHIAVE."}), 401


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

@app.route("/")
def index():
    # La home del prodotto e' IL TURNO (SENTINEL / OB1 Radar). Il vecchio
    # "Council" (chat Analista/Tattico) e' stato rimosso: / manda al turno.
    return redirect("/turno", code=302)


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
_radar_job = {"status": "idle", "result": None, "message": None, "started_at": None,
              "progress": None, "feed_ready": False}

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


def _radar_progress(stage, done=None, total=None, feed_ready=None):
    """Callback passato al motore: aggiorna lo stato leggibile del job cosi'
    il polling mostra 'dossier 3/8' invece di un contatore muto di secondi.
    feed_ready segnala al client che i punteggi sono gia' salvati e puo'
    ricaricare il feed senza aspettare i dossier."""
    with _radar_job_lock:
        _radar_job["progress"] = {"stage": stage, "done": done, "total": total}
        if feed_ready:
            _radar_job["feed_ready"] = True


def _run_radar_job(profile):
    try:
        result = discovery_engine.refresh_radar(profile, progress_cb=_radar_progress)
        # niente lista "results" nello stato del job: il client a fine
        # scansione ricarica comunque /api/radar/feed (gia' cappato a 300),
        # mentre qui la lista completa - migliaia di schede coi dossier -
        # restava pinnata in memoria e usciva INTERA dal polling di
        # /api/radar/refresh/status, proprio il payload che il cap del feed
        # era nato per evitare su mobile. Del risultato servono solo i
        # contatori e run_at.
        result.pop("results", None)
        with _radar_job_lock:
            _radar_job["status"] = "done"
            _radar_job["result"] = result
            _radar_job["message"] = None
    except Exception as e:
        with _radar_job_lock:
            _radar_job["status"] = "error"
            _radar_job["result"] = None
            _radar_job["message"] = str(e)


# Tetto della modalita' sincrona (?wait): sotto il --timeout 570 di gunicorn,
# cosi' e' sempre l'app a rispondere con uno stato leggibile, mai il worker
# ucciso a meta' risposta.
_WAIT_MAX_SECONDS = 540


@app.route("/api/radar/refresh", methods=["POST"])
def radar_refresh():
    data = request.json or {}
    profile = data.get("profile", "tactical_profile")
    # wait=true: la risposta arriva a scansione FINITA. Serve a Cloud
    # Scheduler (la scansione mattutina automatica): tenere la richiesta
    # aperta obbliga Cloud Run a tenere viva l'istanza (e la CPU) per tutta
    # la durata - un fire-and-forget senza polling successivo lascerebbe il
    # thread di sfondo in balia del reclaim dell'istanza. Dal browser non si
    # usa: li' il polling dello status fa lo stesso lavoro senza bloccare.
    wait = bool(data.get("wait"))
    started = False
    with _radar_job_lock:
        if _radar_job["status"] == "running" and not _radar_job_is_stale(_radar_job):
            if not wait:
                return jsonify({"status": "already_running"})
            # in wait mode ci si accoda alla scansione gia' in corso: per lo
            # Scheduler l'esito conta piu' di chi l'ha lanciata
        else:
            _radar_job["status"] = "running"
            _radar_job["result"] = None
            _radar_job["message"] = None
            _radar_job["started_at"] = time.time()
            _radar_job["progress"] = None
            _radar_job["feed_ready"] = False
            started = True
    if started:
        threading.Thread(target=_run_radar_job, args=(profile,), daemon=True).start()
    if not wait:
        return jsonify({"status": "started"})

    deadline = time.time() + _WAIT_MAX_SECONDS
    while time.time() < deadline:
        time.sleep(2)
        with _radar_job_lock:
            if _radar_job["status"] in ("done", "error"):
                break
    with _radar_job_lock:
        job = dict(_radar_job)
    if job["status"] == "done":
        return jsonify({"status": "success", **(job["result"] or {})})
    if job["status"] == "error":
        return jsonify({"status": "error", "message": job["message"]})
    # oltre il tetto: il job continua in background, lo dice chiaramente
    return jsonify({"status": "running", "message": "scansione ancora in corso oltre il tetto di attesa"})


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
    if job["status"] == "running":
        # progresso leggibile ("dossier 3/8") + feed_ready: i punteggi sono
        # gia' salvati (fase 1 del refresh), il client puo' mostrarli senza
        # aspettare i dossier
        prog = job.get("progress") or {}
        label = prog.get("stage")
        if label and prog.get("total"):
            label = f"{label} {prog.get('done') or 0}/{prog['total']}"
        return jsonify({"status": "running", "progress": label,
                        "feed_ready": bool(job.get("feed_ready"))})
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
