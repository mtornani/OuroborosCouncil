# SCADENZA IN LETTURA del turno.
# Il difetto che questi test bloccano: il 23 agosto 2026 il turno mostrava sei
# casi datati 22 agosto, fossili di una scansione precedente che non li aveva
# piu' toccati. Nessuno li avrebbe mai tolti: il contatore dei giri
# (_CARRY_MAX_RUNS) scorre solo per chi viene rivalutato.
# Funzioni pure su dict, niente rete/DB.
#   python tests/test_scadenza_turno.py -v
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discovery_engine import (
    caso_scaduto,
    filtra_casi_scaduti,
    load_config,
    scansioni_note,
    scansioni_saltate,
    soglia_scadenza_turno,
)

CFG = {"state_change": {"scadenza_turno_scansioni": 2}}

S1 = "2026-08-20T05:00:00+00:00"
S2 = "2026-08-22T05:01:24+00:00"
S3 = "2026-08-23T21:16:12+00:00"


def _feed(*run_ats):
    """Un feed finto: un candidato per scansione, storia di una voce."""
    return {f"Q{i}": {"history": [{"run_at": r}]} for i, r in enumerate(run_ats)}


class TestScansioniNote(unittest.TestCase):
    def test_i_run_at_distinti_sono_l_elenco_delle_scansioni(self):
        # tre candidati toccati dalla stessa scansione = UNA scansione
        feed = {"Q1": {"history": [{"run_at": S1}, {"run_at": S3}]},
                "Q2": {"history": [{"run_at": S3}]},
                "Q3": {"history": [{"run_at": S2}, {"run_at": S3}]}}
        note = scansioni_note(feed)
        self.assertEqual([s.isoformat() for s in note], [S1, S2, S3])

    def test_ordinate_dalla_piu_vecchia(self):
        note = scansioni_note(_feed(S3, S1, S2))
        self.assertEqual([s.isoformat() for s in note], [S1, S2, S3])

    def test_feed_vuoto_nessuna_scansione(self):
        self.assertEqual(scansioni_note({}), [])
        self.assertEqual(scansioni_note(None), [])

    def test_timestamp_illeggibile_non_conta_come_scansione(self):
        feed = {"Q1": {"history": [{"run_at": "ieri mattina"}, {"run_at": None}]},
                "Q2": {"history": [{"run_at": S3}]}}
        self.assertEqual(len(scansioni_note(feed)), 1)

    def test_history_vuota_o_mancante_non_esplode(self):
        self.assertEqual(scansioni_note({"Q1": {}, "Q2": {"history": []}, "Q3": None}), [])

    def test_stesso_istante_scritto_in_formati_diversi_e_una_scansione_sola(self):
        feed = {"Q1": {"history": [{"run_at": "2026-08-22T05:00:00+00:00"}]},
                "Q2": {"history": [{"run_at": "2026-08-22T05:00:00Z"}]}}
        self.assertEqual(len(scansioni_note(feed)), 1)


class TestGiroUnicoScrittoMale(unittest.TestCase):
    """Un giro solo non deve MAI diventare mille scansioni: sarebbe un turno
    che si svuota da solo, un difetto peggiore di quello corretto qui."""

    def test_microsecondi_diversi_sono_la_stessa_scansione(self):
        feed = {f"Q{i}": {"history": [{"run_at": f"2026-08-23T21:16:12.{i:06d}+00:00"}]}
                for i in range(50)}
        self.assertEqual(len(scansioni_note(feed)), 1)

    def test_un_giro_scritto_male_non_fa_scadere_nessuno(self):
        feed = {f"Q{i}": {"history": [{"run_at": f"2026-08-23T21:16:1{i}+00:00"}]}
                for i in range(9)}
        casi = [{"candidate_id": f"Q{i}", "run_at": f"2026-08-23T21:16:1{i}+00:00"}
                for i in range(9)]
        out = filtra_casi_scaduti(casi, feed, CFG)
        self.assertEqual(out["scaduti"], [])

    def test_due_scansioni_vere_restano_due(self):
        # distano ore: nessun raggruppamento le deve fondere
        self.assertEqual(len(scansioni_note(_feed(S2, S3))), 2)


class TestScansioniSaltate(unittest.TestCase):
    def setUp(self):
        self.note = scansioni_note(_feed(S1, S2, S3))

    def test_conta_solo_quelle_successive(self):
        self.assertEqual(scansioni_saltate(S1, self.note), 2)
        self.assertEqual(scansioni_saltate(S2, self.note), 1)
        self.assertEqual(scansioni_saltate(S3, self.note), 0)

    def test_illeggibile_torna_none_non_zero(self):
        self.assertIsNone(scansioni_saltate(None, self.note))
        self.assertIsNone(scansioni_saltate("boh", self.note))

    def test_senza_scansioni_note_non_ne_ha_saltata_nessuna(self):
        self.assertEqual(scansioni_saltate(S1, []), 0)


class TestCasoScaduto(unittest.TestCase):
    def setUp(self):
        self.note = scansioni_note(_feed(S1, S2, S3))

    def test_il_caso_dell_ultima_scansione_resta(self):
        self.assertFalse(caso_scaduto(S3, self.note, CFG))

    def test_una_scansione_persa_si_perdona(self):
        # la pool si ricostruisce a ogni giro: un buco singolo non e' un fossile
        self.assertFalse(caso_scaduto(S2, self.note, CFG))

    def test_due_scansioni_saltate_lo_fanno_scadere(self):
        self.assertTrue(caso_scaduto(S1, self.note, CFG))

    def test_soglia_zero_disattiva_la_scadenza(self):
        spento = {"state_change": {"scadenza_turno_scansioni": 0}}
        self.assertFalse(caso_scaduto(S1, self.note, spento))

    def test_radar_fermo_non_fa_scadere_niente(self):
        # nessuna scansione dopo: non e' invecchiato nulla, e' fermo tutto
        self.assertFalse(caso_scaduto(S1, scansioni_note(_feed(S1)), CFG))

    def test_run_at_illeggibile_si_mostra_non_si_condanna(self):
        # assenza di dato non e' una prova di vecchiaia (regola di casa)
        self.assertFalse(caso_scaduto(None, self.note, CFG))
        self.assertFalse(caso_scaduto("2026/08/20", self.note, CFG))


class TestSogliaDichiarata(unittest.TestCase):
    def test_letta_dalla_configurazione_vera(self):
        soglia = soglia_scadenza_turno(load_config())
        self.assertGreaterEqual(soglia, 1)
        self.assertLessEqual(soglia, 20)

    def test_config_assente_usa_il_default_non_esplode(self):
        self.assertGreaterEqual(soglia_scadenza_turno(None), 1)
        self.assertGreaterEqual(soglia_scadenza_turno({}), 1)

    def test_valore_non_numerico_non_rompe_il_turno(self):
        self.assertGreaterEqual(
            soglia_scadenza_turno({"state_change": {"scadenza_turno_scansioni": "due"}}), 1)


class TestFiltroDelTurno(unittest.TestCase):
    def setUp(self):
        # la fotografia del 23 agosto 2026: sei fossili + i casi della scansione nuova
        self.casi = ([{"candidate_id": f"F{i}", "run_at": S1} for i in range(6)]
                     + [{"candidate_id": f"N{i}", "run_at": S3} for i in range(6)])
        self.feed = _feed(S1, S2, S3)

    def test_toglie_i_fossili_e_tiene_i_nuovi(self):
        out = filtra_casi_scaduti(self.casi, self.feed, CFG)
        self.assertEqual([c["candidate_id"] for c in out["casi"]],
                         [f"N{i}" for i in range(6)])
        self.assertEqual(len(out["scaduti"]), 6)

    def test_dichiara_soglia_e_ultima_scansione(self):
        out = filtra_casi_scaduti(self.casi, self.feed, CFG)
        self.assertEqual(out["soglia_scansioni"], 2)
        self.assertEqual(out["ultima_scansione"], S3)

    def test_non_tocca_lo_storico(self):
        prima = repr(self.feed)
        filtra_casi_scaduti(self.casi, self.feed, CFG)
        self.assertEqual(repr(self.feed), prima)

    def test_radar_fermo_non_svuota_il_turno(self):
        # tutti i casi dell'unica scansione avvenuta: la lista resta intera
        fermi = [{"candidate_id": "A", "run_at": S1}, {"candidate_id": "B", "run_at": S1}]
        out = filtra_casi_scaduti(fermi, _feed(S1), CFG)
        self.assertEqual(len(out["casi"]), 2)
        self.assertEqual(out["scaduti"], [])

    def test_due_scansioni_ravvicinate_non_fanno_strage(self):
        # stesso pomeriggio, due giri: chi era della scansione precedente
        # NON e' un fossile solo perche' l'orologio segna poche ore
        vicine = ["2026-08-23T14:00:00+00:00", "2026-08-23T14:40:00+00:00"]
        casi = [{"candidate_id": "A", "run_at": vicine[0]}]
        out = filtra_casi_scaduti(casi, _feed(*vicine), CFG)
        self.assertEqual(len(out["casi"]), 1)

    def test_lista_vuota_o_nulla(self):
        for casi in ([], None):
            out = filtra_casi_scaduti(casi, self.feed, CFG)
            self.assertEqual(out["casi"], [])
            self.assertEqual(out["scaduti"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
