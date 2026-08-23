# Test di OB1-KENOBI (Layer G) - l'algoritmo dell'inefficienza.
#
#   K alman / E ffetto eta' / N ati tardi / O sservazioni / B ilancio / I nefficienza
#            "Questi non sono i giocatori che state cercando."
#
# KENOBI non stima meglio il valore: cerca dove il PREZZO e' sbagliato. Fa una
# sottrazione (valore - prezzo) e la ordina. Questi test bloccano le proprieta'
# da cui dipende il fatto che la sottrazione sia onesta:
#
#  1. NIENTE SOTTRAZIONE SENZA ENTRAMBI I TERMINI. Senza il valore non c'e'
#     arbitraggio, c'e' una scommessa al buio. Deve tacere, non indovinare.
#  2. SOLO BONUS, MAI MALUS sull'anagrafica. Declassare un individuo per una
#     statistica di gruppo e' il modo in cui questi sistemi iniziano a
#     sbagliare in modo invisibile.
#  3. AUTOCALIBRAZIONE ONESTA. Sotto campione minimo non si corregge nulla:
#     una distribuzione stimata su pochi casi parla del campione, non del calcio.
#
#   python3 -m unittest tests/test_kenobi.py -v
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from discovery_engine import (kenobi_score, misura_coorte_anagrafica,
                              sconto_anagrafico, sviluppo_fiducia,
                              _trimestre_relativo)

CFG = yaml.safe_load(open(Path(__file__).resolve().parent.parent / "radar_config.yaml",
                          encoding="utf-8"))
K = CFG["kenobi"]


def _pool(q1=0, q2=0, q3=0, q4=0):
    """Una pool sintetica con una data distribuzione di trimestri di nascita."""
    mesi = {1: "01", 2: "05", 3: "08", 4: "11"}
    out = []
    for t, n in ((1, q1), (2, q2), (3, q3), (4, q4)):
        out += [{"candidate_id": f"Q{t}_{i}", "dob": f"2007-{mesi[t]}-15"} for i in range(n)]
    return out


# la distribuzione REALE misurata sui campionati del radar (n=145):
# Q1 60 / Q2 38 / Q3 30 / Q4 17. Scalata a un campione sopra soglia.
COORTE_REALE = misura_coorte_anagrafica(_pool(240, 152, 120, 68), CFG)


def _val(punteggio, stato="validato"):
    return {"validation_score": punteggio, "stato": stato}


def _giocatore(mese="11"):
    return {"candidate_id": "Q1", "name": "Test", "dob": f"2008-{mese}-15"}


# ======================================================================
class TestTrimestri(unittest.TestCase):

    def test_anno_solare(self):
        self.assertEqual(_trimestre_relativo("2008-01-15", 1), 1)
        self.assertEqual(_trimestre_relativo("2008-12-31", 1), 4)
        self.assertEqual(_trimestre_relativo("2008-07-01", 1), 3)

    def test_taglio_configurabile_settembre(self):
        """Alcune federazioni non usano l'anno solare: chi nasce a settembre
        e' il PIU' VECCHIO della sua annata, non il piu' giovane."""
        self.assertEqual(_trimestre_relativo("2008-09-10", 9), 1)
        self.assertEqual(_trimestre_relativo("2008-08-31", 9), 4)

    def test_dob_mancante(self):
        self.assertIsNone(_trimestre_relativo(None, 1))


# ======================================================================
class TestAutocalibrazione(unittest.TestCase):
    """Il coefficiente non e' preso da un paper e incollato: lo misura la
    pool dell'utente, e si aggiorna da sola."""

    def test_sotto_campione_minimo_non_calibra(self):
        c = misura_coorte_anagrafica(_pool(10, 5, 5, 2), CFG)
        self.assertFalse(c["calibrata"])
        self.assertIn("troppo piccola", c["motivo"])

    def test_misura_la_distribuzione_reale(self):
        self.assertTrue(COORTE_REALE["calibrata"])
        self.assertEqual(COORTE_REALE["n"], 580)
        # Q1 sovra-rappresentato, Q4 sotto
        self.assertGreater(COORTE_REALE["quote"][1], 35)
        self.assertLess(COORTE_REALE["quote"][4], 15)

    def test_chi_quadro_dichiarato(self):
        """Serve a distinguere uno sbilanciamento vero dal campione che balla."""
        self.assertGreater(COORTE_REALE["chi_quadro"], 7.81)
        self.assertTrue(COORTE_REALE["significativo"])

    def test_pool_bilanciata_non_produce_sconti(self):
        """Se l'effetto non c'e', la correzione deve sparire da sola senza
        che nessuno tocchi una riga di config."""
        piatta = misura_coorte_anagrafica(_pool(150, 150, 150, 150), CFG)
        self.assertTrue(piatta["calibrata"])
        self.assertFalse(piatta["significativo"])
        for mese in ("01", "05", "08", "11"):
            s = sconto_anagrafico(f"2008-{mese}-15", piatta, CFG)
            self.assertEqual(s["sconto"], 0.0)


# ======================================================================
class TestScontoAnagrafico(unittest.TestCase):

    def test_nato_tardi_prende_lo_sconto(self):
        s = sconto_anagrafico("2008-11-15", COORTE_REALE, CFG)
        self.assertGreater(s["sconto"], 0)
        self.assertEqual(s["trimestre"], 4)
        self.assertIn("piu' raro", s["motivo"])

    def test_nato_presto_non_e_penalizzato(self):
        """SOLO BONUS, MAI MALUS: mai un malus per il mese di nascita."""
        s = sconto_anagrafico("2008-01-15", COORTE_REALE, CFG)
        self.assertEqual(s["sconto"], 0.0)
        self.assertGreaterEqual(s["sconto"], 0.0)
        self.assertIn("ne' a favore ne' contro", s["motivo"])

    def test_lo_sconto_cresce_col_trimestre(self):
        sconti = [sconto_anagrafico(f"2008-{m}-15", COORTE_REALE, CFG)["sconto"]
                  for m in ("01", "05", "08", "11")]
        self.assertEqual(sconti, sorted(sconti), f"lo sconto non e' monotono: {sconti}")

    def test_senza_dob_nessuna_correzione(self):
        s = sconto_anagrafico(None, COORTE_REALE, CFG)
        self.assertEqual(s["sconto"], 0.0)
        self.assertFalse(s["disponibile"])

    def test_coorte_non_calibrata_non_corregge(self):
        piccola = misura_coorte_anagrafica(_pool(3, 2, 1, 1), CFG)
        s = sconto_anagrafico("2008-11-15", piccola, CFG)
        self.assertEqual(s["sconto"], 0.0)
        self.assertFalse(s["disponibile"])


# ======================================================================
class TestLaSottrazione(unittest.TestCase):
    """edge = valore - prezzo. Il cuore Moneyball."""

    def _k(self, signal, validazione, mese="06"):
        return kenobi_score(_giocatore(mese), signal, validazione, COORTE_REALE, None, CFG)

    def test_valore_alto_prezzo_basso_e_una_occasione(self):
        r = self._k(10, _val(75))
        self.assertEqual(r["stato"], "occasione")
        self.assertEqual(r["tag"], "SOTTOVALUTATO")
        self.assertGreater(r["kenobi_score"], K["bilancio"]["soglia_occasione"])

    def test_prezzo_alto_valore_basso_e_prezzo_in_fuga(self):
        r = self._k(90, _val(None, "non_corroborato"))
        self.assertEqual(r["stato"], "sopravvalutato")
        self.assertEqual(r["tag"], "PREZZO IN FUGA")

    def test_valore_e_prezzo_allineati(self):
        r = self._k(55, _val(55))
        self.assertEqual(r["stato"], "allineato")

    def test_senza_valore_non_esiste_sottrazione(self):
        """LA REGOLA. Senza il valore non c'e' arbitraggio, c'e' una
        scommessa al buio - e questo layer non ne fa."""
        r = self._k(95, _val(None, "non_validabile"))
        self.assertEqual(r["stato"], "non_calcolabile")
        self.assertIsNone(r["kenobi_score"])
        self.assertNotEqual(r["stato"], "sopravvalutato")

    def test_senza_prezzo_non_esiste_sottrazione(self):
        r = self._k(None, _val(80))
        self.assertEqual(r["stato"], "non_calcolabile")
        self.assertIsNone(r["kenobi_score"])

    def test_non_corroborato_vale_zero_ed_e_onesto(self):
        """L'unico zero legittimo: NON viene da un dato mancante, viene da
        una lettura andata a buon fine che non ha trovato nulla."""
        r = self._k(50, _val(None, "non_corroborato"))
        self.assertIsNotNone(r["kenobi_score"])
        self.assertEqual(r["valore"], 0.0)

    def test_zero_zero_non_e_un_mercato_allineato(self):
        """REGRESSIONE da un caso REALE. Valore ~0 e prezzo ~0 danno edge 0,
        che sulla scala finale e' 50 = "mercato allineato". Ma un giocatore
        su cui non sappiamo nulla E di cui non parla nessuno non e' equamente
        prezzato: e' invisibile. In una classifica per scarto quel 50 lo
        spingeva SOPRA giocatori con riscontri veri e prezzo onesto."""
        r = self._k(0, _val(None, "non_corroborato"))
        self.assertIsNone(r["kenobi_score"])
        self.assertEqual(r["stato"], "informazione_insufficiente")

    def test_uno_dei_due_termini_leggibile_basta_a_calcolare(self):
        """La guardia deve scattare SOLO quando tacciono entrambi."""
        solo_prezzo = self._k(60, _val(None, "non_corroborato"))
        self.assertIsNotNone(solo_prezzo["kenobi_score"])
        solo_valore = self._k(0, _val(70))
        self.assertIsNotNone(solo_valore["kenobi_score"])

    def test_invisibile_non_scavalca_chi_ha_riscontri(self):
        invisibile = self._k(2, _val(None, "non_corroborato"))
        con_riscontri = self._k(55, _val(50))
        self.assertIsNone(invisibile["kenobi_score"])
        self.assertIsNotNone(con_riscontri["kenobi_score"])

    def test_ogni_punteggio_si_spiega_da_solo(self):
        r = self._k(20, _val(70), mese="11")
        self.assertTrue(r["spiegazione"])
        self.assertTrue(any("Bilancio" in x for x in r["spiegazione"]))


# ======================================================================
class TestCorrezioneAnagraficaSulValore(unittest.TestCase):
    """Lo sconto corregge il VALORE, non il punteggio finale: non dice
    'merita punti perche' e' nato a dicembre', dice 'il livello raggiunto
    sottostima la sua qualita' perche' il filtro era piu' duro'."""

    def test_nato_tardi_batte_nato_presto_a_parita_di_tutto(self):
        presto = kenobi_score(_giocatore("01"), 30, _val(60), COORTE_REALE, None, CFG)
        tardi = kenobi_score(_giocatore("11"), 30, _val(60), COORTE_REALE, None, CFG)
        self.assertGreater(tardi["kenobi_score"], presto["kenobi_score"])

    def test_la_correzione_non_puo_sfondare_il_massimo(self):
        r = kenobi_score(_giocatore("11"), 0, _val(100), COORTE_REALE, None, CFG)
        self.assertLessEqual(r["valore_corretto"], 1.0)
        self.assertLessEqual(r["kenobi_score"], 100.0)

    def test_la_correzione_non_abbassa_mai(self):
        """Stessa regola cardinale del Layer F."""
        for mese in ("01", "05", "08", "11"):
            r = kenobi_score(_giocatore(mese), 40, _val(60), COORTE_REALE, None, CFG)
            self.assertGreaterEqual(r["valore_corretto"], r["valore"])


# ======================================================================
class TestDerivataSviluppo(unittest.TestCase):
    """La domanda 'come si sviluppera'?' non ha risposta onesta. Quella che
    ce l'ha e': 'la fiducia di chi rischia sta salendo o scendendo?'"""

    def _hist(self, valori):
        return [{"run_at": f"2026-0{i+1}-01", "validation_score": v, "signal_score": 50}
                for i, v in enumerate(valori)]

    def test_storia_corta_non_e_leggibile(self):
        s = sviluppo_fiducia(self._hist([40]), None, CFG)
        self.assertFalse(s["leggibile"])
        self.assertEqual(s["direzione"], "ignota")
        self.assertIn("non ancora leggibile", s["motivo"])

    def test_niente_history_non_esplode(self):
        s = sviluppo_fiducia([], None, CFG)
        self.assertFalse(s["leggibile"])

    def test_fiducia_in_crescita(self):
        s = sviluppo_fiducia(self._hist([20, 25, 30, 70]), None, CFG)
        self.assertTrue(s["leggibile"])
        self.assertEqual(s["direzione"], "salita")

    def test_fiducia_in_calo(self):
        s = sviluppo_fiducia(self._hist([80, 75, 70, 20]), None, CFG)
        self.assertEqual(s["direzione"], "discesa")
        self.assertIn("Non significa che sia peggiorato", s["motivo"])

    def test_fiducia_stabile(self):
        s = sviluppo_fiducia(self._hist([50, 51, 50, 50]), None, CFG)
        self.assertEqual(s["direzione"], "stabile")

    def test_deriva_lenta_via_cusum(self):
        """Nessun salto singolo la giustificherebbe: la vede solo il CUSUM."""
        soglia = CFG["state_change"]["cusum_threshold"]
        s = sviluppo_fiducia(self._hist([50, 51, 52, 53]), {"pos": soglia + 1, "neg": 0.0}, CFG)
        self.assertEqual(s["direzione"], "salita")

    def test_le_entry_senza_validazione_non_gonfiano_il_conteggio(self):
        """Sulla history molte entry hanno validation_score a None: contarle
        direbbe 'visto 20 volte' per 2 misure vere."""
        h = self._hist([30, 40, 50])
        h += [{"run_at": "2026-09-01", "signal_score": 50}] * 10   # nessuna validazione
        s = sviluppo_fiducia(h, None, CFG)
        self.assertEqual(s["n_osservazioni"], 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
