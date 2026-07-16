# Test del GRAFO DELLE FONTI (osservazioni con provenienza + risolutore).
# Funzioni pure su dict: niente rete, niente filesystem, niente DB.
#   python3 -m unittest tests/test_grafo_fonti.py -v
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discovery_engine import (record_observation, resolve_field, _buzz_queries,
                              _build_buzz_pool, _looks_like_tool_markup,
                              _reject_tool_markup, _sanitize_dossier,
                              _AI_VOICE_UNAVAILABLE, _assert_no_duplicate_candidate_ids)

CFG = {
    "piramide": {
        "livelli": {"umano": 0, "news": 2, "wikipedia_torneo": 3, "wikidata": 4},
        "regole_campo": {"club": "dal_basso", "dob": "dall_alto"},
        "finestra_transizione_giorni": 45,
    }
}


class TestRecordObservation(unittest.TestCase):
    def test_registra_e_deduplica(self):
        store = {}
        self.assertTrue(record_observation(store, "Q1", "club", "FC Imabari", "wikidata", CFG))
        self.assertEqual(len(store["Q1"]["club"]), 1)
        # stessa fonte, stesso valore -> conferma, non riga nuova
        self.assertTrue(record_observation(store, "Q1", "club", "FC Imabari", "wikidata", CFG))
        self.assertEqual(len(store["Q1"]["club"]), 1)
        # stessa fonte, valore NUOVO -> riga nuova (lo storico non si riscrive)
        self.assertTrue(record_observation(store, "Q1", "club", "Cerezo Osaka", "wikidata", CFG))
        self.assertEqual(len(store["Q1"]["club"]), 2)

    def test_fonte_non_censita_rifiutata(self):
        store = {}
        self.assertFalse(record_observation(store, "Q1", "club", "X", "fonte_inventata", CFG))
        self.assertEqual(store, {})

    def test_valore_vuoto_rifiutato(self):
        store = {}
        self.assertFalse(record_observation(store, "Q1", "club", "  ", "wikidata", CFG))

    def test_bound_crescita(self):
        store = {}
        for i in range(80):
            record_observation(store, "Q1", "club", f"Club {i}", "news", CFG)
        self.assertLessEqual(len(store["Q1"]["club"]), 30)


class TestResolveField(unittest.TestCase):
    def test_grafo_vuoto_usa_fallback_dichiarato(self):
        res = resolve_field({}, "Q1", "club", CFG, fallback="FC Imabari")
        self.assertEqual(res["valore"], "FC Imabari")
        self.assertIn("nessuna osservazione", res["spiegazione"])
        self.assertIsNone(resolve_field({}, "Q1", "club", CFG))

    def test_accordo_pieno(self):
        store = {}
        record_observation(store, "Q1", "club", "Benfica B", "wikidata", CFG)
        record_observation(store, "Q1", "club", "Benfica B", "news", CFG)
        res = resolve_field(store, "Q1", "club", CFG)
        self.assertEqual(res["valore"], "Benfica B")
        self.assertFalse(res["conflitto"])
        self.assertIn("concordano", res["spiegazione"])

    def test_club_dal_basso_news_datata_batte_wikidata_non_datata(self):
        # LO SCENARIO YOKOYAMA (caso reale, audit 2026-07): Wikidata dice
        # ancora Imabari (P54 senza fine), la stampa datata dice Cerezo.
        store = {}
        record_observation(store, "Q1", "club", "FC Imabari", "wikidata", CFG)
        record_observation(store, "Q1", "club", "Cerezo Osaka", "news", CFG,
                           datato_al="2026-06-28", url="https://esempio/articolo")
        res = resolve_field(store, "Q1", "club", CFG)
        self.assertEqual(res["valore"], "Cerezo Osaka")
        self.assertEqual(res["fonte"], "news")
        self.assertTrue(res["conflitto"])
        self.assertEqual(res["alternativa"], "FC Imabari")
        self.assertIn("datata", res["spiegazione"].lower())

    def test_club_dal_basso_senza_date_vince_il_livello_basso(self):
        store = {}
        record_observation(store, "Q1", "club", "River Plate", "wikipedia_torneo", CFG)
        record_observation(store, "Q1", "club", "Real Madrid", "news", CFG)
        res = resolve_field(store, "Q1", "club", CFG)
        self.assertEqual(res["valore"], "Real Madrid")  # news (L2) < torneo (L3)
        self.assertTrue(res["conflitto"])

    def test_dob_dall_alto_wikidata_batte_news(self):
        # regola d'inversione: sull'anagrafica vince la fonte consolidata
        store = {}
        record_observation(store, "Q1", "dob", "2008-06-03", "wikidata", CFG)
        record_observation(store, "Q1", "dob", "2007-01-01", "news", CFG,
                           datato_al="2026-07-01")
        res = resolve_field(store, "Q1", "dob", CFG)
        self.assertEqual(res["valore"], "2008-06-03")
        self.assertEqual(res["fonte"], "wikidata")
        self.assertTrue(res["conflitto"])

    def test_umano_batte_tutti_e_sopravvive(self):
        store = {}
        record_observation(store, "Q1", "club", "FC Imabari", "wikidata", CFG)
        record_observation(store, "Q1", "club", "Cerezo Osaka", "news", CFG,
                           datato_al="2026-06-28")
        record_observation(store, "Q1", "club", "Cerezo Osaka", "umano", CFG)
        res = resolve_field(store, "Q1", "club", CFG)
        self.assertEqual(res["fonte"], "umano")
        self.assertIn("confermato a mano", res["spiegazione"])
        # ...e una RI-emissione da Wikidata stantia non lo ribalta (la falla
        # vecchia: la correzione moriva alla riscrittura successiva)
        record_observation(store, "Q1", "club", "FC Imabari", "wikidata", CFG)
        res = resolve_field(store, "Q1", "club", CFG)
        self.assertEqual(res["valore"], "Cerezo Osaka")
        self.assertEqual(res["fonte"], "umano")

    def test_deterministico(self):
        store = {}
        record_observation(store, "Q1", "club", "A", "wikidata", CFG)
        record_observation(store, "Q1", "club", "B", "news", CFG, datato_al="2026-01-01")
        r1 = resolve_field(store, "Q1", "club", CFG)
        r2 = resolve_field(store, "Q1", "club", CFG)
        self.assertEqual(r1, r2)


class TestBuzzQueries(unittest.TestCase):
    def test_query_sul_club_risolto_non_su_quello_grezzo(self):
        c = {"name": "Yumeki Yokoyama", "club": "FC Imabari",
             "club_risolto": "Cerezo Osaka"}
        qs = _buzz_queries(c)
        self.assertEqual(qs, ['"Yumeki Yokoyama" "Cerezo Osaka"'])

    def test_doppia_query_in_finestra_di_transizione(self):
        c = {"name": "Yumeki Yokoyama", "club": "FC Imabari",
             "club_risolto": "Cerezo Osaka", "club_alternativo": "FC Imabari"}
        qs = _buzz_queries(c)
        self.assertEqual(len(qs), 2)
        self.assertIn('"Yumeki Yokoyama" "Cerezo Osaka"', qs)
        self.assertIn('"Yumeki Yokoyama" "FC Imabari"', qs)

    def test_senza_club_nome_nudo(self):
        self.assertEqual(_buzz_queries({"name": "Moussa Cissé"}), ['"Moussa Cissé"'])


class TestBuzzPool(unittest.TestCase):
    """Il bug della curva mancante nel TURNO: i casi attivi (con dossier AI
    vero) devono avere il posto garantito nel giro dei controlli stampa,
    anche se la testa della classifica-eta' e' occupata dai saturi a 1.0."""

    def test_caso_attivo_entra_anche_fuori_classifica(self):
        # 5 saturi in testa, pool di 3: senza la regola, Yokoyama (attivo,
        # age piu' basso) resterebbe fuori per sempre
        saturi = [{"candidate_id": f"Q{i}"} for i in range(5)]
        yokoyama = {"candidate_id": "Q123575819"}
        rest = saturi + [yokoyama]
        feed = {"Q123575819": {"dossier": {"giudice": {"vale_la_pena": False}}}}
        pool = _build_buzz_pool([], rest, feed, pool_size=3)
        ids = [c["candidate_id"] for c in pool]
        self.assertIn("Q123575819", ids)
        # i posti a classifica restano per i primi 3 saturi
        self.assertEqual(ids, ["Q123575819", "Q0", "Q1", "Q2"])

    def test_dossier_skip_o_errore_non_compra_il_posto(self):
        rest = [{"candidate_id": f"Q{i}"} for i in range(4)]
        feed = {
            "Q3": {"dossier": {"skipped": "segnale singolo"}},   # non attivo
            "Q2": {"dossier": {"error": "AI giu'"}},              # non attivo
        }
        pool = _build_buzz_pool([], rest, feed, pool_size=2)
        self.assertEqual([c["candidate_id"] for c in pool], ["Q0", "Q1"])

    def test_watchlist_sempre_prima(self):
        wl = [{"candidate_id": "W1"}]
        rest = [{"candidate_id": "Q0"}]
        pool = _build_buzz_pool(wl, rest, {}, pool_size=1)
        self.assertEqual([c["candidate_id"] for c in pool], ["W1", "Q0"])


class TestGuardiaAntiDoppioneSwarm(unittest.TestCase):
    """Blocco strutturale contro il rischio di raddoppiare le chiamate AI
    dello swarm (es. un futuro dossier bilingue che ri-lancia Cronista/
    Verificatore/Scettico/Giudice una volta per lingua). Deve bloccare
    PRIMA di spendere la chiamata, non dopo averla scoperta a posteriori."""

    def test_nessun_doppione_passa(self):
        _assert_no_duplicate_candidate_ids(["Q1", "Q2", "Q3"], "test")  # non solleva

    def test_lista_vuota_passa(self):
        _assert_no_duplicate_candidate_ids([], "test")  # non solleva

    def test_doppione_blocca_prima_della_chiamata(self):
        with self.assertRaises(RuntimeError) as ctx:
            _assert_no_duplicate_candidate_ids(["Q1", "Q2", "Q1"], "finestra swarm")
        self.assertIn("Q1", str(ctx.exception))
        self.assertIn("finestra swarm", str(ctx.exception))


class TestToolMarkupNelleVoci(unittest.TestCase):
    """Un modello free puo' 'rispondere' emettendo la sintassi di una
    chiamata strumento come testo. Caso reale mostrato sulla card di Leandro
    Santos: la voce dello Scettico era letteralmente il markup del tool."""

    # il testo ESATTO comparso sulla card in produzione (2026-07-08)
    REALE = ('<tool_call> <function=openrouter_web_search> <parameter=query> '
             '"Leandro Santos" 2005 calciatore Brasile Portogallo omonimo '
             '</parameter> </function> </tool_call>')

    def test_riconosce_il_caso_reale(self):
        self.assertTrue(_looks_like_tool_markup(self.REALE))

    def test_varianti(self):
        self.assertTrue(_looks_like_tool_markup("bla <tool_call>x</tool_call>"))
        self.assertTrue(_looks_like_tool_markup("[TOOL_CALL] cerca [/TOOL_CALL]"))
        self.assertTrue(_looks_like_tool_markup("<function=search>"))

    def test_testo_normale_passa(self):
        for ok in ("Prospetto 19enne con esordi in Primeira Liga",
                   "il segnale e' debole, funzione del contesto",  # 'funzione' parola normale
                   "parametri di crescita interessanti", "", None):
            self.assertFalse(_looks_like_tool_markup(ok), ok)

    def test_reject_sostituisce_con_nota_onesta(self):
        self.assertEqual(_reject_tool_markup(self.REALE), _AI_VOICE_UNAVAILABLE)
        self.assertEqual(_reject_tool_markup("testo sano"), "testo sano")

    def test_sanitize_dossier_pulisce_anche_i_salvati(self):
        # il dossier di Leandro era GIA' su Neon: la pulizia in lettura deve
        # sistemarlo senza rigenerare niente
        dossier = {"cronista": "ok", "verificatore": "ok",
                   "scettico": self.REALE,
                   "giudice": {"motivazione": self.REALE}}
        _sanitize_dossier(dossier)
        self.assertEqual(dossier["scettico"], _AI_VOICE_UNAVAILABLE)
        self.assertEqual(dossier["giudice"]["motivazione"], _AI_VOICE_UNAVAILABLE)
        self.assertEqual(dossier["cronista"], "ok")


class TestScenarioYokoyamaEndToEnd(unittest.TestCase):
    """La prova su carta completa: da tre osservazioni discordi al club
    risolto in card e alla query buzz giusta - il percorso che prima
    falliva (query sul club vecchio nel momento esatto del salto)."""

    def test_percorso_completo(self):
        store = {}
        # run 1: il lettore Wikidata emette il club stantio
        record_observation(store, "Q123575819", "club", "Football Club Imabari", "wikidata", CFG)
        res = resolve_field(store, "Q123575819", "club", CFG)
        self.assertEqual(res["valore"], "Football Club Imabari")  # unica voce

        # run 2: il Cronista trova il club nuovo via ricerca web (datato)
        record_observation(store, "Q123575819", "club", "Cerezo Osaka", "news", CFG,
                           datato_al="2026-07-07", nota="Cronista via ricerca web")
        res = resolve_field(store, "Q123575819", "club", CFG)
        self.assertEqual(res["valore"], "Cerezo Osaka")
        self.assertTrue(res["conflitto"])

        # la query buzz ora cerca con ENTRAMBI i club (finestra transizione)
        candidate = {"name": "Yumeki Yokoyama", "club": "Football Club Imabari",
                     "club_risolto": res["valore"],
                     "club_alternativo": res["alternativa"]}
        self.assertEqual(len(_buzz_queries(candidate)), 2)

        # run 3: Wikidata RI-emette il club vecchio (la scheda non e' stata
        # corretta) - il risolutore NON regredisce
        record_observation(store, "Q123575819", "club", "Football Club Imabari", "wikidata", CFG)
        res = resolve_field(store, "Q123575819", "club", CFG)
        self.assertEqual(res["valore"], "Cerezo Osaka")

        # il tap di conferma chiude il caso
        record_observation(store, "Q123575819", "club", "Cerezo Osaka", "umano", CFG)
        res = resolve_field(store, "Q123575819", "club", CFG)
        self.assertEqual(res["fonte"], "umano")


if __name__ == "__main__":
    unittest.main()
