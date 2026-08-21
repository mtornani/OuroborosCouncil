# Test del GATE SENZA AI: la sonda di cambiamento di stato usata per decidere
# CHI merita un dossier, prima di spendere una chiamata AI.
#
# L'assunto portante del gate (vedi refresh_radar, fase 1) e' che chiamare
# detect_state_change con i due argomenti "dossier" a None dia esattamente la
# parte di sonda che non dipende dall'AI - senza duplicare la logica e senza
# riordinare i motivi. Questi test lo bloccano: se qualcuno un domani rende
# un motivo dipendente dal dossier, o viceversa, il gate cambia significato in
# silenzio e qui deve rompersi.
#
#   python3 -m unittest tests/test_gate_senza_ai.py -v
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discovery_engine import detect_state_change

CFG = {"state_change": {
    "shock_z_threshold": 2.5,
    "cusum_k": 0.5,
    "cusum_threshold": 4.0,
    "early_velocity_threshold": 0.4,
}}
NO_CUSUM = {"pos": 0.0, "neg": 0.0}
# un'entry di storico qualunque: serve solo a non far scattare "nuovo
# ingresso" (motivo 6), che altrimenti coprirebbe tutti gli altri casi
PREV = {"signal_score": 50, "partial_data": False}


def _probe(**kw):
    """La sonda come la chiama il gate: senza dossier, ne' vecchio ne' nuovo."""
    base = dict(candidate={"name": "X"}, previous_last_entry=PREV,
                previous_dossier=None, current_dossier=None,
                current_partial_data=False, bayes=None, cusum_state=NO_CUSUM,
                cfg=CFG, buzz_detail=None, curve=None)
    base.update(kw)
    return detect_state_change(**base)


class TestMotiviDisponibiliSenzaAI(unittest.TestCase):
    """Questi motivi devono restare rilevabili a costo zero: sono loro che
    riempiono la finestra swarm quando il gate e' attivo."""

    def test_decollo_imminente(self):
        curve = {"phase": 3, "factors": {"a": {"active": True, "detail": "menzioni in crescita"}}}
        self.assertEqual(_probe(curve=curve)["type"], "takeoff")

    def test_finestra_precoce(self):
        buzz = {"sub_scores": {"velocity": 0.8}, "snapshot": {"tier1_present": False}}
        self.assertEqual(_probe(buzz_detail=buzz)["type"], "early")

    def test_diventato_mainstream(self):
        buzz = {"sub_scores": {"geographic_crossing": 1.0}}
        self.assertEqual(_probe(buzz_detail=buzz)["type"], "mainstream")

    def test_dati_completati(self):
        change = _probe(previous_last_entry={"partial_data": True}, current_partial_data=False)
        self.assertEqual(change["type"], "resolved")

    def test_salto_anomalo(self):
        self.assertEqual(_probe(bayes={"last_innovation_z": 3.1})["type"], "rising")
        self.assertEqual(_probe(bayes={"last_innovation_z": -3.1})["type"], "falling")

    def test_deriva_sostenuta(self):
        self.assertEqual(_probe(cusum_state={"pos": 5.0, "neg": 0.0})["type"], "rising")
        self.assertEqual(_probe(cusum_state={"pos": 0.0, "neg": 5.0})["type"], "falling")

    def test_nuovo_ingresso(self):
        # e' il motivo che al primo run scatta per TUTTI: e' esattamente il
        # caso per cui max_dossiers_per_run non e' opzionale
        self.assertEqual(_probe(previous_last_entry=None)["type"], "new")

    def test_niente_da_segnalare_non_spende(self):
        # il caso piu' importante di tutti: un candidato che non si e' mosso
        # non deve costare una chiamata AI
        self.assertIsNone(_probe())


class TestMotiviCheRichiedonoAI(unittest.TestCase):
    """Questi due devono AUTOESCLUDERSI quando i dossier sono None: e' cio'
    che rende il gate una sonda 'senza AI' senza codice duplicato."""

    def test_verdetto_ribaltato_non_scatta_senza_dossier(self):
        # con i dossier presenti scatterebbe...
        acceso = detect_state_change(
            candidate={"name": "X"}, previous_last_entry=PREV,
            previous_dossier={"giudice": {"vale_la_pena": False}},
            current_dossier={"giudice": {"vale_la_pena": True}},
            current_partial_data=False, bayes=None, cusum_state=NO_CUSUM, cfg=CFG)
        self.assertEqual(acceso["type"], "verdict")
        # ...ma il gate non ha dossier da confrontare: nessun falso motivo
        self.assertIsNone(_probe())

    def test_club_dal_giudice_non_scatta_senza_dossier(self):
        # web_search_tool_available: True -> il Cronista aveva davvero la
        # ricerca in questa generazione, quindi il club_aggiornato del
        # Giudice e' fondato (vedi anche TestClubDalGiudiceRichiedeGrounding
        # sotto per il caso in cui NON lo e')
        acceso = detect_state_change(
            candidate={"name": "X", "club": "FC Imabari"}, previous_last_entry=PREV,
            previous_dossier=None,
            current_dossier={"giudice": {"club_aggiornato": "Cerezo Osaka"},
                             "web_search_tool_available": True},
            current_partial_data=False, bayes=None, cusum_state=NO_CUSUM, cfg=CFG)
        self.assertEqual(acceso["type"], "club")
        self.assertIsNone(_probe())


class TestClubDalGiudiceRichiedeGrounding(unittest.TestCase):
    """Bug reale trovato dal vivo (Alex Marchal, 2026-08, config di default
    swarm.web_search_grounding: false): il Cronista non aveva ricerca web in
    quella generazione, ma il Giudice ha comunque ripetuto lo STESSO club
    gia' in archivio come "club_aggiornato" (un modello economico che non
    rispetta "altrimenti null") - la card CLUB DA CORREGGERE confrontava un
    valore con se stesso ("risultava a X, la stampa dice X")."""

    def test_giudice_senza_grounding_non_scatta_anche_se_diverso(self):
        # senza web_search_tool_available, club_aggiornato non e' fondato su
        # nulla - non conta nemmeno se propone un nome DIVERSO, l'assenza di
        # ricerca vera lo rende un'invenzione, non una correzione
        change = detect_state_change(
            candidate={"name": "X", "club": "FC Imabari"}, previous_last_entry=PREV,
            previous_dossier=None,
            current_dossier={"giudice": {"club_aggiornato": "Cerezo Osaka"},
                             "web_search_tool_available": False},
            current_partial_data=False, bayes=None, cusum_state=NO_CUSUM, cfg=CFG)
        self.assertIsNone(change)

    def test_giudice_ripete_lo_stesso_club_non_scatta_anche_con_grounding(self):
        # il caso esatto di Alex Marchal: grounding disponibile, ma il
        # modello ha ripetuto lo stesso club invece di rispettare
        # "altrimenti null" - vecchio e nuovo identici, nessuna correzione
        change = detect_state_change(
            candidate={"name": "X", "club": "Real Sociedad de Futbol B"},
            previous_last_entry=PREV, previous_dossier=None,
            current_dossier={"giudice": {"club_aggiornato": "Real Sociedad de Futbol B"},
                             "web_search_tool_available": True},
            current_partial_data=False, bayes=None, cusum_state=NO_CUSUM, cfg=CFG)
        self.assertIsNone(change)

    def test_giudice_senza_flag_dossier_non_scatta(self):
        # dossier senza la chiave web_search_tool_available (dossier vecchi,
        # generati prima di questa guardia): trattato come non fondato, non
        # come "vero per default" - degrada al sicuro
        change = detect_state_change(
            candidate={"name": "X", "club": "FC Imabari"}, previous_last_entry=PREV,
            previous_dossier=None,
            current_dossier={"giudice": {"club_aggiornato": "Cerezo Osaka"}},
            current_partial_data=False, bayes=None, cusum_state=NO_CUSUM, cfg=CFG)
        self.assertIsNone(change)


class TestClubDalGrafo(unittest.TestCase):
    """Il cambio club scoperto dal GRAFO (news_reader) deve essere rilevabile
    senza AI: e' la strada che vale per l'intera pool invece che per i soli
    candidati che arrivano al dossier."""

    def test_club_da_grafo_scatta_senza_dossier(self):
        candidate = {
            "name": "X", "club": "FC Imabari",
            "club_provenienza": {"valore": "Cerezo Osaka", "fonte": "news",
                                 "datato_al": "2026-07-01", "url": "http://x/1",
                                 "spiegazione": "titolo stampa"},
        }
        change = _probe(candidate=candidate)
        self.assertEqual(change["type"], "club")
        self.assertEqual(change["club_vecchio"], "FC Imabari")
        self.assertEqual(change["club_nuovo"], "Cerezo Osaka")
        self.assertEqual(change["club_fonte_url"], "http://x/1")
        self.assertIn("2026-07-01", change["lead"])

    def test_club_da_grafo_uguale_all_archivio_non_scatta(self):
        candidate = {
            "name": "X", "club": "FC Imabari",
            "club_provenienza": {"valore": "FC Imabari", "fonte": "news"},
        }
        self.assertIsNone(_probe(candidate=candidate))

    def test_correzione_gia_segnalata_non_si_ripresenta(self):
        # evento puntuale: si mostra una volta. Altrimenti il tag tornerebbe
        # identico a ogni scansione finche' Wikidata non si aggiorna,
        # rioccupando il turno di revisione all'infinito.
        candidate = {
            "name": "X", "club": "FC Imabari",
            "_club_risolto_precedente": "Cerezo Osaka",
            "club_provenienza": {"valore": "Cerezo Osaka", "fonte": "news"},
        }
        self.assertIsNone(_probe(candidate=candidate))

    def test_seconda_correzione_diversa_si_mostra(self):
        # ma se la stampa cambia di nuovo idea, quello e' un fatto nuovo
        candidate = {
            "name": "X", "club": "FC Imabari",
            "_club_risolto_precedente": "Cerezo Osaka",
            "club_provenienza": {"valore": "Sporting CP", "fonte": "news"},
        }
        self.assertEqual(_probe(candidate=candidate)["club_nuovo"], "Sporting CP")

    def test_club_risolto_da_wikidata_non_e_una_correzione(self):
        # solo la fonte "news" segnala un trasferimento: il risolutore che
        # conferma Wikidata non e' una notizia
        candidate = {
            "name": "X", "club": "FC Imabari",
            "club_provenienza": {"valore": "Cerezo Osaka", "fonte": "wikidata"},
        }
        self.assertIsNone(_probe(candidate=candidate))


class TestPrecedenzaMotivi(unittest.TestCase):
    def test_club_batte_decollo(self):
        # il club sbagliato invalida tutto il resto: va mostrato per primo
        candidate = {"name": "X", "club": "FC Imabari",
                     "club_provenienza": {"valore": "Cerezo Osaka", "fonte": "news"}}
        curve = {"phase": 3, "factors": {"a": {"active": True, "detail": "d"}}}
        self.assertEqual(_probe(candidate=candidate, curve=curve)["type"], "club")

    def test_decollo_batte_shock(self):
        curve = {"phase": 3, "factors": {"a": {"active": True, "detail": "d"}}}
        self.assertEqual(_probe(curve=curve, bayes={"last_innovation_z": 9.0})["type"], "takeoff")


if __name__ == "__main__":
    unittest.main()
