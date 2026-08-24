#!/usr/bin/env python3
"""SMOKE TEST - "la situazione", in un comando solo.

    python3 smoke_test.py              # tutto, rete inclusa
    python3 smoke_test.py --offline    # salta le fonti esterne

Non sostituisce i test unitari (quelli stanno in tests/ e verificano le
REGOLE). Questo verifica che l'IMPIANTO stia in piedi: che i sette layer si
parlino, che la pipeline arrivi fino all'API, che le rotte rispondano, che le
fonti esterne siano vive. E' il controllo da fare prima di un deploy, o il
giorno che qualcosa non torna e non sai da che parte guardare.

REGOLA DI LETTURA, che e' la stessa del resto del progetto:
  OK        funziona
  DEGRADATO una fonte esterna non risponde. NON e' un bug: il radar e'
            progettato per continuare senza. Si segnala, non si fallisce.
  ROTTO     invariante violata. Questo si', e' un bug.
"""
import argparse
import os
import sys
import traceback
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ESITI = {"ok": 0, "degradato": 0, "rotto": 0}
_ROTTURE = []


def check(nome, fn, degradabile=False):
    """degradabile=True: un fallimento e' 'fonte non disponibile', non un bug."""
    try:
        dettaglio = fn()
        print(f"  \033[32mOK\033[0m        {nome}" + (f"  ({dettaglio})" if dettaglio else ""))
        ESITI["ok"] += 1
    except Exception as e:
        if degradabile:
            print(f"  \033[33mDEGRADATO\033[0m {nome}  ({type(e).__name__}: {str(e)[:70]})")
            ESITI["degradato"] += 1
        else:
            print(f"  \033[31mROTTO\033[0m     {nome}")
            print(f"            {type(e).__name__}: {str(e)[:200]}")
            ESITI["rotto"] += 1
            _ROTTURE.append((nome, traceback.format_exc()))


def sezione(titolo):
    print(f"\n\033[1m{titolo}\033[0m")
    print("  " + "-" * (len(titolo) + 2))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="salta i controlli di rete")
    args = ap.parse_args()

    os.environ.pop("DATABASE_URL", None)  # smoke test su file locali, mai sul DB di produzione
    print("\033[1m" + "=" * 68)
    print(" SENTINEL / OB1 - SMOKE TEST")
    print("=" * 68 + "\033[0m")

    # ------------------------------------------------------------------
    sezione("1. IMPIANTO — import e configurazione")
    import discovery_engine as de
    cfg = {}

    def _cfg():
        cfg.update(de.load_config())
        return f"{len(cfg)} sezioni"
    check("radar_config.yaml si carica", _cfg)

    def _chiavi():
        attese = ["piramide", "candidate_sources", "age_reference", "signal_score_weights",
                  "buzz_weights", "purpose_profiles", "bayesian", "state_change",
                  "adoption_curve", "validazione_tecnica", "kenobi"]
        mancanti = [k for k in attese if k not in cfg]
        if mancanti:
            raise AssertionError(f"sezioni mancanti: {mancanti}")
        return f"tutte le {len(attese)} sezioni presenti"
    check("tutti i layer hanno la loro configurazione", _chiavi)

    def _pesi():
        vt = cfg["validazione_tecnica"]
        # invariante: cio' che il buzz misura non entra MAI nella validazione
        assert vt["costo_segnale"]["menzione_stampa"] == 0.0, "la stampa e' entrata nella validazione"
        assert vt["quadranti"]["soglia_validazione"] > 0
        assert cfg["kenobi"]["solo_bonus"] is True, "il malus anagrafico e' stato riattivato"
        return f"{len(vt['competizioni'])} leghe mappate"
    check("invarianti di configurazione (no doppio conteggio, no malus)", _pesi)

    def _persistenza():
        st = de.persistence_status()
        return f"modalita' {st['mode']}, durevole={st['durable']}"
    check("stato persistenza dichiarato", _persistenza)

    # ------------------------------------------------------------------
    sezione("2. LAYER A–E — attenzione (funzioni pure)")
    OGGI = datetime.now()
    dob17 = (OGGI - timedelta(days=17.3 * 365.25)).strftime("%Y-%m-%d")
    cand = {"candidate_id": "Q1", "name": "Smoke", "dob": dob17, "tier": "serie_c", "club": "X"}

    check("Layer A — eta' relativa al livello",
          lambda: f"score={de.age_vs_level_score(cand, cfg):.2f}")

    def _signal():
        r = de.signal_score(cand, cfg, {"score": 0.6, "available": True, "sub_scores": {}})
        assert r["signal_score"] is not None
        return f"signal={r['signal_score']}"
    check("Layer A — Signal Score combinato", _signal)

    def _dati_mancanti():
        r = de.signal_score(cand, cfg, None)
        assert not r["excluded"], "un buzz non controllato ha escluso il candidato"
        assert r["partial_data"] is True, "dati parziali non segnalati"
        return "buzz assente -> 'dati parziali', mai uno zero inventato"
    check("Layer A — un dato mancante non diventa mai zero", _dati_mancanti)

    def _bayes():
        h = [{"signal_score": v, "partial_data": False} for v in (40, 45, 50, 70)]
        b = de.bayesian_estimate(h, cfg)
        assert b and b["confidence_band"][0] < b["estimate"] < b["confidence_band"][1]
        return f"stima={b['estimate']} banda={b['confidence_band']} z={b['last_innovation_z']}"
    check("Layer C — filtro di Kalman", _bayes)

    def _cusum():
        st = {"pos": 0.0, "neg": 0.0}
        for _ in range(6):
            st = de._update_cusum(st, 1.2, cfg)
        assert st["pos"] > cfg["state_change"]["cusum_threshold"]
        return f"deriva accumulata pos={st['pos']}"
    check("Layer D — CUSUM accumula la deriva lenta", _cusum)

    def _sonda():
        ev = de.detect_state_change(
            candidate=cand, previous_last_entry=None, previous_dossier=None,
            current_dossier=None, current_partial_data=False, bayes=None,
            cusum_state={"pos": 0.0, "neg": 0.0}, cfg=cfg)
        assert ev and ev["type"] == "new"
        return f"nuovo ingresso -> '{ev['tag']}'"
    check("Layer D — sonda di cambiamento di stato", _sonda)

    # ------------------------------------------------------------------
    sezione("3. LAYER F — validazione (il segnale costoso)")

    def carriera(mem, stato="ok"):
        return {"memberships": mem, "fonte": "wikidata",
                "letto_il": OGGI.strftime("%Y-%m-%d"), "stato_lettura": stato}

    club = {"team": "Schalke", "team_qid": "Q32494", "league_qid": "Q82595", "apps": 11,
            "start": (OGGI - timedelta(days=400)).strftime("%Y-%m-%dT00:00:00Z"),
            "end": None, "is_national": False}
    naz = {"team": "Nazionale Under-17 di calcio della Germania", "team_qid": "Q319699",
           "league_qid": None, "apps": 17,
           "start": (OGGI - timedelta(days=700)).strftime("%Y-%m-%dT00:00:00Z"),
           "end": None, "is_national": True}

    v_validato = de.validation_score(cand, carriera([club, naz]), cfg)
    v_vuoto = de.validation_score(cand, carriera([dict(club, apps=None)]), cfg)
    v_muto = de.validation_score(cand, None, cfg)

    def _validato():
        assert v_validato["stato"] == "validato", v_validato["stato"]
        assert v_validato["prove"], "nessuna prova allegata al punteggio"
        return f"score={v_validato['validation_score']} prove={len(v_validato['prove'])}"
    check("caso reale (11 pres. in 1a divisione a 17 anni + U17)", _validato)

    def _tre_stati():
        stati = {v_validato["stato"], v_vuoto["stato"], v_muto["stato"]}
        assert stati == {"validato", "non_corroborato", "non_validabile"}, stati
        assert v_vuoto["validation_score"] is None and v_muto["validation_score"] is None
        return "validato / non_corroborato / non_validabile restano distinti"
    check("i tre stati non collassano", _tre_stati)

    def _monotonia():
        base = de.validation_score(cand, carriera([club]), cfg)["validation_score"]
        piu = de.validation_score(cand, carriera([club, naz]), cfg)["validation_score"]
        assert piu >= base, f"aggiungere una prova ha ABBASSATO il punteggio: {base} -> {piu}"
        return f"{base} -> {piu} aggiungendo una convocazione"
    check("REGOLA CARDINALE — aggiungere evidenza non abbassa mai", _monotonia)

    def _quadranti():
        silenzioso = de.evidence_quadrant(10, v_validato, cfg)["quadrante"]
        rumore = de.evidence_quadrant(90, v_vuoto, cfg)["quadrante"]
        muto = de.evidence_quadrant(95, v_muto, cfg)["quadrante"]
        assert silenzioso == "tesoro_silenzioso", silenzioso
        assert rumore == "solo_rumore", rumore
        assert muto == "indeterminato", f"un dato mancante e' diventato un'accusa: {muto}"
        return "tesoro / rumore / indeterminato"
    check("quadranti — e un 'non so' non diventa mai un'accusa", _quadranti)

    # ------------------------------------------------------------------
    sezione("4. LAYER G — OB1-KENOBI (l'inefficienza)")

    def _pool(q1, q2, q3, q4):
        mesi = {1: "01", 2: "05", 3: "08", 4: "11"}
        return [{"candidate_id": f"Q{t}_{i}", "dob": f"2007-{mesi[t]}-15"}
                for t, n in ((1, q1), (2, q2), (3, q3), (4, q4)) for i in range(n)]

    coorte = de.misura_coorte_anagrafica(_pool(240, 152, 120, 68), cfg)

    def _coorte():
        assert coorte["calibrata"], coorte.get("motivo")
        assert coorte["significativo"], "l'effetto eta' non risulta significativo sul campione noto"
        return (f"n={coorte['n']} chi2={coorte['chi_quadro']} "
                f"Q1={coorte['quote'][1]}% Q4={coorte['quote'][4]}%")
    check("autocalibrazione sulla coorte reale", _coorte)

    def _piatta():
        p = de.misura_coorte_anagrafica(_pool(150, 150, 150, 150), cfg)
        s = de.sconto_anagrafico("2008-11-15", p, cfg)
        assert s["sconto"] == 0.0, "corregge anche quando l'effetto non c'e'"
        return "pool bilanciata -> correzione zero, da sola"
    check("se l'effetto sparisce, la correzione sparisce", _piatta)

    def _no_malus():
        s = de.sconto_anagrafico("2008-01-15", coorte, cfg)
        assert s["sconto"] == 0.0 and s["sconto"] >= 0.0
        return "nato a gennaio: nessun bonus, ma nemmeno un malus"
    check("SOLO BONUS, MAI MALUS sull'anagrafica", _no_malus)

    g_tardi = de.kenobi_score({"dob": "2008-11-15"}, 15, v_validato, coorte, None, cfg)
    g_presto = de.kenobi_score({"dob": "2008-01-15"}, 15, v_validato, coorte, None, cfg)
    g_caro = de.kenobi_score({"dob": "2008-06-15"}, 92, v_vuoto, coorte, None, cfg)
    g_cieco = de.kenobi_score({"dob": "2008-06-15"}, 95, v_muto, coorte, None, cfg)

    def _sottrazione():
        assert g_tardi["stato"] == "occasione", g_tardi["stato"]
        assert g_caro["stato"] == "sopravvalutato", g_caro["stato"]
        return f"sottovalutato={g_tardi['kenobi_score']}  prezzo in fuga={g_caro['kenobi_score']}"
    check("la sottrazione valore-prezzo separa i casi opposti", _sottrazione)

    def _rae_paga():
        assert g_tardi["kenobi_score"] > g_presto["kenobi_score"]
        return (f"nato in nov {g_tardi['kenobi_score']} vs nato in gen "
                f"{g_presto['kenobi_score']} (tutto il resto identico)")
    check("l'effetto eta' relativa muove davvero la classifica", _rae_paga)

    def _tace():
        assert g_cieco["kenobi_score"] is None, "ha fatto la sottrazione senza il valore"
        assert g_cieco["stato"] == "non_calcolabile"
        return "senza il valore non c'e' arbitraggio -> tace"
    check("niente sottrazione senza entrambi i termini", _tace)

    def _derivata():
        h = [{"validation_score": v, "signal_score": 50} for v in (20, 25, 30, 70)]
        s = de.sviluppo_fiducia(h, None, cfg)
        assert s["direzione"] == "salita", s["direzione"]
        corta = de.sviluppo_fiducia(h[:1], None, cfg)
        assert not corta["leggibile"], "ha letto una traiettoria da una sola osservazione"
        return f"fiducia in {s['direzione']} (z={s['z']}), storia corta -> 'non leggibile'"
    check("derivata della fiducia (Kalman/CUSUM sulla validazione)", _derivata)

    # ------------------------------------------------------------------
    sezione("5. PIPELINE — dal record all'API")
    import json
    import tempfile
    from pathlib import Path

    tmp = Path(tempfile.mkdtemp())
    orig_feed, orig_coorte = de.FEED_FILE, de.COORTE_FILE
    orig_decisioni = de.DECISIONS_FILE
    de.FEED_FILE, de.COORTE_FILE = tmp / "radar_feed.json", tmp / "coorte_anagrafica.json"
    # anche le decisioni umane su file temporaneo: senza, lo smoke test
    # leggerebbe quelle vere di chi lo lancia e non sarebbe ripetibile
    de.DECISIONS_FILE = tmp / "human_decisions.json"
    try:
        casi = {"Q_tesoro": (v_validato, 12, "2008-11-15"),
                "Q_rumore": (v_vuoto, 90, "2008-02-15"),
                "Q_muto": (v_muto, 88, "2008-06-15")}
        feed = {}
        for qid, (val, sig, dob) in casi.items():
            c = {"candidate_id": qid, "name": qid, "dob": dob, "tier": "serie_c", "club": "X"}
            quad = de.evidence_quadrant(sig, val, cfg)
            ken = de.kenobi_score(c, sig, val, coorte, None, cfg)
            feed[qid] = {"identity": c, "validazione": val, "quadrante": quad, "kenobi": ken,
                         "history": [{"run_at": de._now_iso(), "signal_score": sig,
                                      "components": {"buzz": 0.9}, "partial_data": False,
                                      "fit_score": sig, "profile_used": "tactical_profile",
                                      "curve": None, "validation_score": val.get("validation_score"),
                                      "validation_stato": val["stato"],
                                      "quadrante": quad["quadrante"],
                                      "kenobi_score": ken.get("kenobi_score"),
                                      "state_change": {"type": "new", "tag": "NUOVO INGRESSO", "lead": "x"}}]}
        de._save_json(de.FEED_FILE, feed)
        de._save_json(de.COORTE_FILE, coorte)

        def _copertura():
            s = de.validation_coverage_summary()
            assert s["considerati"] == 3, s
            assert s["tesori_silenziosi"] == 1, s["quadranti"]
            return f"copertura={s['copertura_pct']}% tesori={s['tesori_silenziosi']}"
        check("/processo — il Layer F dichiara la sua copertura", _copertura)

        def _kenobi_sum():
            s = de.kenobi_summary()
            assert s["considerati"] == 3
            assert s["occasioni"] >= 1, s["stati"]
            assert s["coorte"]["calibrata"]
            return f"calcolabili={s['calcolabili']}/3 occasioni={s['occasioni']}"
        check("/processo — KENOBI dichiara la sua copertura", _kenobi_sum)

        def _caveat():
            cav = de.player_caveats(feed["Q_muto"]["history"][-1], None,
                                    feed["Q_muto"]["identity"], cfg,
                                    validazione=feed["Q_muto"]["validazione"])
            testo = " ".join(cav)
            assert "ne' a favore ne' contro" in testo, testo
            assert "falso positivo" not in testo, "un dato mancante e' diventato un'accusa"
            return "il 'non so' resta un non so, anche con buzz 88"
        check("contraddittorio — nessuna accusa su un dato mancante", _caveat)

        import visual_council_app as app_mod
        app_mod.discovery_engine = de
        client = app_mod.app.test_client()

        def _rotte_api():
            fuori = []
            for r in ("/api/radar/feed", "/api/radar/turno", "/api/radar/processo",
                      "/api/radar/mappa", "/api/radar/config", "/api/version"):
                resp = client.get(r)
                if resp.status_code != 200 or resp.get_json().get("status") == "error":
                    fuori.append((r, resp.status_code, (resp.get_json() or {}).get("message")))
            if fuori:
                raise AssertionError(f"rotte KO: {fuori}")
            return "6 rotte API a 200"
        check("tutte le rotte API rispondono", _rotte_api)

        def _payload():
            row = next(r for r in client.get("/api/radar/feed").get_json()["results"]
                       if r["candidate_id"] == "Q_tesoro")
            for campo in ("validazione", "quadrante", "kenobi", "caveats"):
                assert row.get(campo) is not None, f"'{campo}' non arriva all'API"
            assert row["quadrante"]["quadrante"] == "tesoro_silenzioso"
            assert row["kenobi"]["kenobi_score"] is not None
            return f"quadrante={row['quadrante']['quadrante']} kenobi={row['kenobi']['kenobi_score']}"
        check("i layer F e G arrivano fino alla scheda", _payload)

        def _pagine():
            for r in ("/turno", "/radar", "/mappa", "/processo"):
                resp = client.get(r)
                assert resp.status_code == 200, f"{r} -> {resp.status_code}"
                assert len(resp.data) > 5000, f"{r} sospettosamente corta"
            return "4 pagine renderizzate"
        check("le pagine HTML si disegnano", _pagine)

        def _fossile():
            # un caso rimasto indietro di due scansioni: e' il difetto visto
            # in produzione il 23 agosto 2026 (sei casi del 22 fermi in cima
            # al turno). Deve uscire dalla lista ED essere dichiarato, non
            # sparire in silenzio.
            from datetime import datetime, timedelta, timezone
            adesso = datetime.now(timezone.utc)
            def _copia(qid, quando):
                rec = dict(feed[qid])
                voce = dict(rec["history"][-1])
                voce["run_at"] = quando.isoformat()
                rec["history"] = [voce]
                return rec
            # due scansioni precedenti, nessuna delle quali ha toccato il fossile
            finto = {**feed,
                     "Q_fossile": _copia("Q_rumore", adesso - timedelta(days=3)),
                     "Q_ieri": _copia("Q_muto", adesso - timedelta(days=1))}
            de._save_json(de.FEED_FILE, finto)
            try:
                turno = client.get("/api/radar/turno").get_json()
                ids = {c["candidate_id"] for c in turno["cases"]}
                assert "Q_fossile" not in ids, "un caso vecchio di due scansioni e' ancora nel turno"
                assert "Q_ieri" in ids, "una scansione persa non deve bastare a far scadere un caso"
                assert "Q_tesoro" in ids, "la scadenza si e' portata via anche i casi freschi"
                assert turno["scaduti_count"] == 1, turno["scaduti_count"]

                # e il numero dichiarato deve dire la verita': un fossile che
                # avevi GIA' deciso non l'avresti visto comunque, quindi non
                # conta come "uscito dalla lista". Visto in produzione il 24
                # agosto 2026: 10 dichiarati contro 6 davvero tolti.
                finto["Q_fossile_deciso"] = _copia("Q_muto", adesso - timedelta(days=3))
                de._save_json(de.FEED_FILE, finto)
                de._save_json(de.DECISIONS_FILE, {"Q_fossile_deciso": {
                    "status": "scarto", "updated_at": adesso.isoformat(),
                    "note": None, "name": "x", "club": "y", "history": []}})
                turno = client.get("/api/radar/turno").get_json()
                assert "Q_fossile_deciso" not in {c["candidate_id"] for c in turno["cases"]}
                assert turno["scaduti_count"] == 1, (
                    f"un caso gia' deciso e' stato contato come scaduto: {turno['scaduti_count']}")
                return f"1 fossile fuori dalla lista, dichiarato (soglia {turno['scadenza_scansioni']} scansioni)"
            finally:
                de._save_json(de.FEED_FILE, feed)
                de._save_json(de.DECISIONS_FILE, {})
        check("il turno non propone fossili", _fossile)
    finally:
        de.FEED_FILE, de.COORTE_FILE = orig_feed, orig_coorte
        de.DECISIONS_FILE = orig_decisioni

    # ------------------------------------------------------------------
    sezione("6. FONTI ESTERNE" + ("  (saltata: --offline)" if args.offline else ""))
    if not args.offline:
        import urllib.request

        def _wikidata():
            rosa = de._sparql_current_squad("Q607965")
            if not rosa:
                raise RuntimeError("nessuna riga (WDQS puo' essere sotto rate-limit)")
            return f"{len(rosa)} righe dalla rosa Serie C"
        check("Wikidata SPARQL (pool candidati)", _wikidata, degradabile=True)

        def _carriera():
            r = de._sparql_career_batch(["Q114825245"], cfg["validazione_tecnica"])
            if r is None:
                raise RuntimeError("fonte muta")
            mem = r.get("Q114825245") or []
            naz = sum(1 for m in mem if m["is_national"])
            return f"{len(mem)} membership, {naz} nazionali riconosciute"
        check("Wikidata SPARQL (carriera, Layer F)", _carriera, degradabile=True)

        def _news():
            from monitor.web_monitor import search_google_news
            res = search_google_news('"Serie C" calcio', max_results=3)
            res = [x for x in res if "error" not in x]
            if not res:
                raise RuntimeError("nessun risultato")
            return f"{len(res)} titoli"
        check("Google News RSS (buzz)", _news, degradabile=True)

    # ------------------------------------------------------------------
    print("\n" + "\033[1m" + "=" * 68)
    tot = sum(ESITI.values())
    print(f" ESITO: {ESITI['ok']}/{tot} ok"
          + (f", {ESITI['degradato']} degradati" if ESITI["degradato"] else "")
          + (f", \033[31m{ESITI['rotto']} ROTTI\033[0m\033[1m" if ESITI["rotto"] else ""))
    print("=" * 68 + "\033[0m")

    if ESITI["degradato"]:
        print("\nI 'degradati' sono fonti esterne che non hanno risposto. Il radar e'")
        print("progettato per continuare senza: i candidati coinvolti risultano")
        print("'non validabili' (che NON e' un voto basso) e nient'altro cambia.")
    if ESITI["rotto"]:
        print("\nDettaglio delle rotture:")
        for nome, tb in _ROTTURE:
            print(f"\n--- {nome} ---\n{tb}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
