# ESTRATTO DEL GIORNO — building in public, senza inventare niente.
# Funzioni pure su dict, niente rete/DB (leggi_run_di_oggi e' l'unico punto
# di I/O del file e non e' testato qui per lo stesso motivo).
#   python tests/test_estratto_del_giorno.py -v
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from estratto_del_giorno import (
    LIMITE_CARATTERI,
    bozza_caso_reale,
    bozza_limite_onesto,
    bozza_numero_onesto,
    costruisci_bozze,
    eta_anni,
    registra_pubblicazione,
    stato_streak,
)

OGGI = datetime(2026, 8, 24, tzinfo=timezone.utc)


class TestEtaAnni(unittest.TestCase):
    def test_calcola_eta_corretta(self):
        # nato il 24/08/2008 -> esattamente 18 anni oggi
        self.assertAlmostEqual(eta_anni("2008-08-24", OGGI), 18.0, places=1)

    def test_minorenne(self):
        self.assertLess(eta_anni("2010-01-01", OGGI), 18.0)

    def test_nessuna_data_nessuna_eta_indovinata(self):
        self.assertIsNone(eta_anni(None, OGGI))
        self.assertIsNone(eta_anni("", OGGI))

    def test_data_illeggibile_non_esplode(self):
        self.assertIsNone(eta_anni("non e' una data", OGGI))
        self.assertIsNone(eta_anni("2010/01/01", OGGI))  # formato non ISO: dichiarato illeggibile, non riparato


class TestBozzaCasoReale(unittest.TestCase):
    """La regola di sicurezza piu' importante del file: mai un minorenne,
    mai un'eta' indovinata. Questi test devono restare rossi se qualcuno
    allenta la condizione in bozza_caso_reale."""

    def _turno(self, cases):
        return {"cases": cases}

    def test_esclude_minorenni(self):
        turno = self._turno([{
            "name": "Ragazzo Minorenne", "club": "X", "dob": "2010-01-01",
            "change": {"lead": "sta emergendo"}, "candidate_id": "Q1",
        }])
        self.assertIsNone(bozza_caso_reale(turno, OGGI))

    def test_esclude_eta_non_calcolabile(self):
        turno = self._turno([{
            "name": "Data Sconosciuta", "club": "X", "dob": None,
            "change": {"lead": "sta emergendo"}, "candidate_id": "Q2",
        }])
        self.assertIsNone(bozza_caso_reale(turno, OGGI))

    def test_include_adulto_verificato(self):
        turno = self._turno([{
            "name": "Giocatore Adulto", "club": "FC Esempio", "dob": "2005-01-01",
            "change": {"lead": "tendenza in salita"}, "candidate_id": "Q3",
        }])
        bozza = bozza_caso_reale(turno, OGGI)
        self.assertIsNotNone(bozza)
        self.assertIn("Giocatore Adulto", bozza["testo"])
        self.assertIn("FC Esempio", bozza["testo"])

    def test_salta_il_minorenne_e_prende_il_prossimo_adulto(self):
        turno = self._turno([
            {"name": "Minore", "club": "X", "dob": "2011-01-01",
             "change": {"lead": "y"}, "candidate_id": "Q4"},
            {"name": "Adulto", "club": "Y", "dob": "2003-01-01",
             "change": {"lead": "z"}, "candidate_id": "Q5"},
        ])
        bozza = bozza_caso_reale(turno, OGGI)
        self.assertIsNotNone(bozza)
        self.assertIn("Adulto", bozza["testo"])
        self.assertNotIn("Minore", bozza["testo"])

    def test_lista_vuota_nessuna_bozza(self):
        self.assertIsNone(bozza_caso_reale(self._turno([]), OGGI))

    def test_caso_senza_lead_escluso(self):
        turno = self._turno([{
            "name": "Senza Motivo", "club": "X", "dob": "2000-01-01",
            "change": {}, "candidate_id": "Q6",
        }])
        self.assertIsNone(bozza_caso_reale(turno, OGGI))

    def test_rispetta_il_limite_di_caratteri(self):
        lead_lunghissimo = "y " * 200
        turno = self._turno([{
            "name": "Nome Lungo", "club": "Club Con Nome Molto Lungo Davvero",
            "dob": "2000-01-01", "change": {"lead": lead_lunghissimo}, "candidate_id": "Q7",
        }])
        bozza = bozza_caso_reale(turno, OGGI)
        self.assertLessEqual(len(bozza["testo"]), LIMITE_CARATTERI)


class TestBozzaNumeroOnesto(unittest.TestCase):
    def test_preferisce_il_tasso_di_apertura(self):
        processo = {
            "precisione_turno": {"decisioni_totali": 77, "tasso_apertura_complessivo": 67.5},
            "validazione_copertura": {"considerati": 3750, "copertura_pct": 3.8},
        }
        bozza = bozza_numero_onesto(processo)
        self.assertIn("67.5", bozza["testo"])
        self.assertIn("77 decisioni", bozza["testo"])

    def test_cade_sulla_copertura_senza_decisioni(self):
        processo = {
            "precisione_turno": {"decisioni_totali": 0, "tasso_apertura_complessivo": None},
            "validazione_copertura": {"considerati": 3750, "copertura_pct": 3.8},
        }
        bozza = bozza_numero_onesto(processo)
        self.assertIsNotNone(bozza)
        self.assertIn("3750", bozza["testo"])

    def test_niente_dati_niente_bozza_inventata(self):
        self.assertIsNone(bozza_numero_onesto({}))


class TestBozzaLimiteOnesto(unittest.TestCase):
    def test_scaduti_oggi(self):
        processo = {}
        turno = {"scaduti_count": 6, "scadenza_scansioni": 2}
        bozza = bozza_limite_onesto(processo, turno)
        self.assertIn("6", bozza["testo"])

    def test_singolare_corretto(self):
        turno = {"scaduti_count": 1, "scadenza_scansioni": 2}
        bozza = bozza_limite_onesto({}, turno)
        self.assertIn("1 caso e'", bozza["testo"])

    def test_cade_sul_tabellone_senza_scaduti(self):
        processo = {"esplosi": 0, "sgonfiati": 23}
        bozza = bozza_limite_onesto(processo, {"scaduti_count": 0})
        self.assertIn("0 scommesse esplose su 23", bozza["testo"])

    def test_niente_materiale_niente_bozza(self):
        self.assertIsNone(bozza_limite_onesto({}, {"scaduti_count": 0}))


class TestCostruisciBozze(unittest.TestCase):
    def test_fino_a_tre_bozze_categorie_diverse(self):
        run = {
            "turno": {
                "scaduti_count": 6, "scadenza_scansioni": 2,
                "cases": [{"name": "Adulto Vero", "club": "FC Test", "dob": "2003-01-01",
                          "change": {"lead": "tendenza in salita"}, "candidate_id": "Q1"}],
            },
            "processo": {
                "precisione_turno": {"decisioni_totali": 77, "tasso_apertura_complessivo": 67.5},
            },
        }
        bozze = costruisci_bozze(run, OGGI)
        self.assertEqual(len(bozze), 3)
        self.assertEqual({b["categoria"] for b in bozze}, {"numero", "limite", "caso"})

    def test_giorno_povero_meno_di_tre_bozze_mai_inventate(self):
        run = {"turno": {"scaduti_count": 0, "cases": []}, "processo": {}}
        self.assertEqual(costruisci_bozze(run, OGGI), [])


class TestStreak(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()) / "streak.json"

    def test_registra_e_rilegge(self):
        registra_pubblicazione("2026-08-24", self.tmp)
        self.assertEqual(stato_streak(["2026-08-24"], OGGI)["consecutivi"], 1)

    def test_consecutivi_reali(self):
        date_iso = ["2026-08-22", "2026-08-23", "2026-08-24"]
        stato = stato_streak(date_iso, OGGI)
        self.assertEqual(stato["consecutivi"], 3)
        self.assertEqual(stato["totale"], 3)
        self.assertIsNone(stato["ultimo_buco"])

    def test_streak_ancora_valido_se_ieri(self):
        # oggi non hai ancora pubblicato: lo streak di ieri non e' "rotto"
        # finche' non finisce la giornata di oggi
        stato = stato_streak(["2026-08-22", "2026-08-23"], OGGI)
        self.assertEqual(stato["consecutivi"], 2)

    def test_buco_dichiarato_non_nascosto(self):
        date_iso = ["2026-08-20", "2026-08-24"]
        stato = stato_streak(date_iso, OGGI)
        self.assertEqual(stato["consecutivi"], 1)  # solo oggi conta, il buco ha spezzato la catena
        self.assertEqual(stato["totale"], 2)
        self.assertIsNotNone(stato["ultimo_buco"])
        self.assertEqual(stato["ultimo_buco"]["giorni_saltati"], 3)

    def test_nessuna_pubblicazione_mai(self):
        stato = stato_streak([], OGGI)
        self.assertEqual(stato, {"consecutivi": 0, "totale": 0, "ultimo_buco": None})

    def test_file_non_creato_finche_non_serve(self):
        self.assertFalse(self.tmp.exists())
        registra_pubblicazione("2026-08-24", self.tmp)
        self.assertTrue(self.tmp.exists())

    def test_registrare_due_volte_lo_stesso_giorno_non_duplica(self):
        registra_pubblicazione("2026-08-24", self.tmp)
        date_iso = registra_pubblicazione("2026-08-24", self.tmp)
        self.assertEqual(date_iso.count("2026-08-24"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
