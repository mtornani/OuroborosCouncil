# Il tabellone del /processo deve essere un fact-check nominativo:
# numeri senza nomi = finto audit. Nessuna rete, nessun DB.
#   python -m unittest tests.test_processo_roster -v
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discovery_engine import (
    _record_curve_crossing,
    _source_tier,
    _tier1_hits_from_results,
    _update_flag_ledger,
    tabellone,
)

CFG = {
    "source_tiers": {
        "tier_1": ["Gazzetta dello Sport", "Sky Sport"],
        "tier_2": ["TuttoMercatoWeb"],
    }
}


class TestTier1Hits(unittest.TestCase):
    def test_estrae_solo_le_testate_tier1_con_titolo_e_url(self):
        results = [
            {"title": "Yokoyama al Cerezo - Gazzetta dello Sport",
             "url": "https://news.google.com/yoko"},
            {"title": "Voci di mercato - Blog Locale",
             "url": "https://blog.example/x"},
            {"title": "Esordio in B - Sky Sport",
             "link": "https://news.google.com/sky"},
        ]
        hits = _tier1_hits_from_results(results, CFG)
        pubs = [h["publisher"] for h in hits]
        self.assertEqual(pubs, ["Gazzetta dello Sport", "Sky Sport"])
        self.assertEqual(hits[0]["url"], "https://news.google.com/yoko")
        self.assertEqual(hits[1]["url"], "https://news.google.com/sky")
        self.assertIn("Yokoyama", hits[0]["title"])

    def test_niente_tier1_lista_vuota(self):
        results = [{"title": "Cronaca - Il Piccolo", "url": "https://x"}]
        self.assertEqual(_tier1_hits_from_results(results, CFG), [])


class TestCrossingMemorizzaProva(unittest.TestCase):
    def test_evento_porta_nome_e_prova_fisica(self):
        ledger = {}
        record = {"history": [
            {"curve": {"phase": 3}},
            {"curve": {"phase": 4}},
        ]}
        prova = [{"publisher": "Gazzetta dello Sport",
                  "title": "Yokoyama al Cerezo - Gazzetta dello Sport",
                  "url": "https://news.google.com/yoko"}]
        changed = _record_curve_crossing(
            ledger, record,
            {"candidate_id": "Q1", "name": "Yumeki Yokoyama"},
            "2026-08-03T07:00:00+00:00",
            prova=prova,
        )
        self.assertTrue(changed)
        ev = ledger["events"][0]
        self.assertEqual(ev["name"], "Yumeki Yokoyama")
        self.assertEqual(ev["prova"], prova)
        self.assertTrue(ev["anticipato"])

    def test_senza_prova_non_inventa_una_testata(self):
        ledger = {}
        _record_curve_crossing(
            ledger, {"history": [{"curve": {"phase": 4}}]},
            {"candidate_id": "Q2", "name": "Ignoto"},
            "2026-08-03T07:00:00+00:00",
        )
        self.assertNotIn("prova", ledger["events"][0])


class TestChiusuraScommessa(unittest.TestCase):
    def test_esploso_salva_fase_e_prova(self):
        ledger = {}
        c = {"candidate_id": "Q1", "name": "Yumeki Yokoyama"}
        _update_flag_ledger(ledger, c, 3, "2026-07-01T00:00:00+00:00")
        prova = [{"publisher": "Sky Sport", "title": "T - Sky Sport", "url": "https://s"}]
        _update_flag_ledger(ledger, c, 4, "2026-08-03T00:00:00+00:00", prova=prova)
        flag = ledger["flags"][0]
        self.assertEqual(flag["outcome"], "esploso")
        self.assertEqual(flag["close_phase"], 4)
        self.assertEqual(flag["name"], "Yumeki Yokoyama")
        self.assertEqual(flag["prova"], prova)

    def test_sgonfiato_salva_fase_di_ricaduta(self):
        ledger = {}
        c = {"candidate_id": "Q9", "name": "Falso Allarme"}
        _update_flag_ledger(ledger, c, 3, "2026-07-01T00:00:00+00:00")
        _update_flag_ledger(ledger, c, 2, "2026-08-01T00:00:00+00:00")
        flag = ledger["flags"][0]
        self.assertEqual(flag["outcome"], "sgonfiato")
        self.assertEqual(flag["close_phase"], 2)
        self.assertNotIn("prova", flag)


class TestTabelloneNominativo(unittest.TestCase):
    def test_espone_i_casi_per_nome_non_solo_i_conteggi(self):
        ledger = {
            "flags": [
                {"candidate_id": "Q1", "name": "Aperto Uno",
                 "flagged_at": "2026-08-01T00:00:00+00:00",
                 "outcome": "pending", "resolved_at": None},
                {"candidate_id": "Q2", "name": "Esploso Due",
                 "flagged_at": "2026-06-01T00:00:00+00:00",
                 "resolved_at": "2026-07-15T00:00:00+00:00",
                 "outcome": "esploso", "close_phase": 4,
                 "prova": [{"publisher": "Gazzetta dello Sport",
                            "title": "Due sui grandi - Gazzetta dello Sport",
                            "url": "https://g"}]},
                {"candidate_id": "Q3", "name": "Sgonfiato Tre",
                 "flagged_at": "2026-05-01T00:00:00+00:00",
                 "resolved_at": "2026-06-01T00:00:00+00:00",
                 "outcome": "sgonfiato", "close_phase": 1},
            ],
            "events": [
                {"candidate_id": "Q2", "name": "Esploso Due",
                 "crossed_at": "2026-07-15T00:00:00+00:00",
                 "anticipato": True,
                 "prova": [{"publisher": "Gazzetta dello Sport",
                            "title": "Due sui grandi - Gazzetta dello Sport",
                            "url": "https://g"}]},
                {"candidate_id": "Q4", "name": "Scappato Quattro",
                 "crossed_at": "2026-07-20T00:00:00+00:00",
                 "anticipato": False,
                 "prova": [{"publisher": "Sky Sport",
                            "title": "Quattro in prima - Sky Sport",
                            "url": "https://sky"}]},
            ],
        }
        feed = {
            "Q1": {"identity": {"name": "Aperto Uno", "club": "Foggia"}},
            "Q2": {"identity": {"name": "Esploso Due", "club": "Cerezo Osaka"}},
        }
        d = tabellone(ledger, feed=feed, cfg=CFG)

        self.assertEqual(d["esplosi"], 1)
        self.assertEqual(d["sgonfiati"], 1)
        self.assertEqual(d["pending"], 1)

        self.assertEqual([c["name"] for c in d["casi_aperti"]], ["Aperto Uno"])
        self.assertEqual(d["casi_aperti"][0]["club"], "Foggia")

        self.assertEqual([c["name"] for c in d["casi_esplosi"]], ["Esploso Due"])
        self.assertEqual(d["casi_esplosi"][0]["prova"][0]["publisher"],
                         "Gazzetta dello Sport")
        self.assertEqual(d["casi_esplosi"][0]["club"], "Cerezo Osaka")

        self.assertEqual([c["name"] for c in d["casi_sgonfiati"]], ["Sgonfiato Tre"])
        self.assertEqual(d["casi_sgonfiati"][0]["close_phase"], 1)

        self.assertEqual([c["name"] for c in d["casi_scappati"]], ["Scappato Quattro"])
        self.assertFalse(d["casi_scappati"][0]["anticipato"])
        self.assertEqual(d["casi_scappati"][0]["prova"][0]["publisher"], "Sky Sport")

    def test_prova_ricostruita_dallo_storico_buzz_se_manca_nel_ledger(self):
        # ledger vecchio: nomi sì, testata no. Il fact-check deve comunque
        # dire CHI e, se lo snapshot buzz c'è, QUALE testata.
        ledger = {
            "flags": [{
                "candidate_id": "Q1", "name": "Vecchio Caso",
                "flagged_at": "2026-06-01T00:00:00+00:00",
                "resolved_at": "2026-07-01T00:00:00+00:00",
                "outcome": "esploso",
            }],
            "events": [{
                "candidate_id": "Q1", "name": "Vecchio Caso",
                "crossed_at": "2026-07-01T00:00:00+00:00",
                "anticipato": True,
            }],
        }
        buzz = {
            "Q1": {"runs": [
                {"run_at": "2026-06-01T00:00:00+00:00", "publishers": ["Il Piccolo"],
                 "tier1_present": False},
                {"run_at": "2026-07-01T00:00:00+00:00",
                 "publishers": ["Gazzetta dello Sport", "Blog X"],
                 "tier1_present": True},
            ]},
        }
        d = tabellone(ledger, buzz_history=buzz, cfg=CFG)
        prova = d["casi_esplosi"][0]["prova"]
        self.assertEqual(prova[0]["publisher"], "Gazzetta dello Sport")
        self.assertIsNone(prova[0].get("url"))  # snapshot vecchio: solo il nome

    def test_tabellone_vuoto_liste_vuote_non_percentuali(self):
        d = tabellone({}, cfg=CFG)
        self.assertEqual(d["casi_aperti"], [])
        self.assertEqual(d["casi_esplosi"], [])
        self.assertEqual(d["casi_sgonfiati"], [])
        self.assertEqual(d["casi_scappati"], [])
        self.assertIsNone(d["precision"])
        self.assertIsNone(d["recall"])


class TestSourceTierAncoraStabile(unittest.TestCase):
    def test_gazzetta_e_tier1(self):
        self.assertEqual(_source_tier("Gazzetta dello Sport", CFG), 1)


if __name__ == "__main__":
    unittest.main()
