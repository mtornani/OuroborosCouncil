# Contratto umano: SENTINEL priorizza, l'occhio decide.
# Funzioni pure su dict, niente rete/DB.
#   python tests/test_human_decisions.py -v
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from discovery_engine import (
    HUMAN_STATUSES,
    da_verificare_cards,
    record_human_decision,
    split_human_workload,
)


class TestRecordDecision(unittest.TestCase):
    def test_registra_status_e_nome(self):
        store = {}
        rec = record_human_decision(
            store, "Q1", "in_verifica",
            at="2026-08-15T07:00:00+00:00",
            name="Yumeki Yokoyama", club="Cerezo Osaka",
        )
        self.assertEqual(rec["status"], "in_verifica")
        self.assertEqual(rec["name"], "Yumeki Yokoyama")
        self.assertEqual(store["Q1"]["status"], "in_verifica")

    def test_status_illegale_rifiutato(self):
        store = {}
        with self.assertRaises(ValueError):
            record_human_decision(store, "Q1", "forse", at="2026-08-15T07:00:00+00:00")
        self.assertEqual(store, {})

    def test_nota_opzionale_e_storico(self):
        store = {}
        record_human_decision(store, "Q1", "in_verifica", at="2026-08-15T07:00:00+00:00")
        record_human_decision(
            store, "Q1", "tiene",
            at="2026-08-16T07:00:00+00:00",
            note="piede sinistro vero",
        )
        rec = store["Q1"]
        self.assertEqual(rec["status"], "tiene")
        self.assertEqual(rec["note"], "piede sinistro vero")
        self.assertEqual(rec["history"][0]["status"], "in_verifica")
        self.assertIn("in_verifica", HUMAN_STATUSES)


class TestSplitWorkload(unittest.TestCase):
    def _case(self, cid, run_at="2026-08-15T07:00:00+00:00"):
        return {"candidate_id": cid, "run_at": run_at, "name": cid}

    def test_senza_decisione_resta_nel_turno(self):
        cases = [self._case("Q1")]
        split = split_human_workload(cases, {})
        self.assertEqual([c["candidate_id"] for c in split["turno"]], ["Q1"])
        self.assertEqual(split["da_verificare_ids"], [])

    def test_in_verifica_esce_dal_turno_entra_nella_coda(self):
        store = {}
        record_human_decision(store, "Q1", "in_verifica", at="2026-08-15T08:00:00+00:00")
        split = split_human_workload([self._case("Q1")], store)
        self.assertEqual(split["turno"], [])
        self.assertEqual(split["da_verificare_ids"], ["Q1"])

    def test_scarto_nasconde_finche_non_arriva_un_segnale_nuovo(self):
        store = {}
        record_human_decision(store, "Q1", "scarto", at="2026-08-15T08:00:00+00:00")
        same = split_human_workload([self._case("Q1", "2026-08-15T07:00:00+00:00")], store)
        self.assertEqual(same["turno"], [])
        newer = split_human_workload([self._case("Q1", "2026-08-16T07:00:00+00:00")], store)
        self.assertEqual([c["candidate_id"] for c in newer["turno"]], ["Q1"])

    def test_passo_riappare_alla_scan_successiva(self):
        store = {}
        record_human_decision(store, "Q1", "passo", at="2026-08-15T08:00:00+00:00")
        same = split_human_workload([self._case("Q1", "2026-08-15T07:00:00+00:00")], store)
        self.assertEqual(same["turno"], [])
        later = split_human_workload([self._case("Q1", "2026-08-16T07:00:00+00:00")], store)
        self.assertEqual([c["candidate_id"] for c in later["turno"]], ["Q1"])

    def test_tiene_resta_chiuso_finche_il_segnale_non_si_muove(self):
        store = {}
        record_human_decision(store, "Q1", "tiene", at="2026-08-15T08:00:00+00:00")
        same = split_human_workload([self._case("Q1", "2026-08-15T07:00:00+00:00")], store)
        self.assertEqual(same["turno"], [])
        moved = split_human_workload([self._case("Q1", "2026-08-20T07:00:00+00:00")], store)
        self.assertEqual([c["candidate_id"] for c in moved["turno"]], ["Q1"])


class TestDaVerificareCards(unittest.TestCase):
    def test_coda_usa_snapshot_anche_senza_caso_nel_turno(self):
        store = {}
        record_human_decision(
            store, "Q9", "in_verifica",
            at="2026-08-15T08:00:00+00:00",
            name="Ignoto", club="Foggia",
        )
        cards = da_verificare_cards(store, feed={})
        self.assertEqual(len(cards), 1)
        self.assertEqual(cards[0]["name"], "Ignoto")
        self.assertEqual(cards[0]["club"], "Foggia")
        self.assertEqual(cards[0]["change"]["type"], "verifica")

    def test_coda_arricchisce_dal_feed_se_c_e(self):
        store = {}
        record_human_decision(store, "Q1", "in_verifica", at="2026-08-15T08:00:00+00:00", name="Vecchio")
        feed = {
            "Q1": {
                "identity": {"name": "Yumeki Yokoyama", "club": "Cerezo Osaka", "role": "Centrocampista"},
                "history": [{"run_at": "2026-08-15T07:00:00+00:00", "signal_score": 71,
                             "state_change": {"type": "takeoff", "tag": "STA PER ESPLODERE", "lead": "x"}}],
            }
        }
        cards = da_verificare_cards(store, feed)
        self.assertEqual(cards[0]["name"], "Yumeki Yokoyama")
        self.assertEqual(cards[0]["signal_score"], 71)
        self.assertEqual(cards[0]["change"]["type"], "takeoff")


if __name__ == "__main__":
    unittest.main()


# ======================================================================
class TestPrecisioneTurno(unittest.TestCase):
    """QUANTO VALE LA LISTA GIORNALIERA, per tipo di segnalazione.

    I dati c'erano gia' tutti: per ogni caso mostrato nel turno viene
    registrata una decisione (in_verifica/passo/scarto/tiene/non_tiene).
    Nessuno li stava contando. Incrociandoli col motivo per cui il caso era
    in lista si scopre quali allarmi si guadagnano il posto nel turno."""

    def _feed(self, cid, motivo, run_at="2026-08-01T10:00:00+00:00"):
        return {cid: {"identity": {"name": cid},
                      "history": [{"run_at": run_at,
                                   "state_change": {"type": motivo, "tag": motivo.upper()}}]}}

    def _dec(self, cid, status, at="2026-08-02T10:00:00+00:00"):
        return {cid: {"status": status, "updated_at": at}}

    def test_conta_aperture_per_motivo(self):
        from discovery_engine import precisione_turno
        feed, dec = {}, {}
        for i in range(4):                      # takeoff: 4 mostrati, 4 aperti
            feed.update(self._feed(f"T{i}", "takeoff"))
            dec.update(self._dec(f"T{i}", "in_verifica"))
        for i in range(10):                     # rising: 10 mostrati, 1 aperto
            feed.update(self._feed(f"R{i}", "rising"))
            dec.update(self._dec(f"R{i}", "in_verifica" if i == 0 else "passo"))
        r = precisione_turno(dec, feed)
        self.assertEqual(r["per_motivo"]["takeoff"]["tasso_apertura"], 100.0)
        self.assertEqual(r["per_motivo"]["rising"]["tasso_apertura"], 10.0)
        # il piu' utile in cima
        self.assertEqual(list(r["per_motivo"])[0], "takeoff")

    def test_non_tiene_conta_come_apertura_riuscita(self):
        """Il turno ha fatto BENE a mostrarlo: l'hai guardato. Che il
        giocatore non abbia retto e' un giudizio sul giocatore, non sulla
        lista. La lista propone, l'occhio dispone."""
        from discovery_engine import precisione_turno
        r = precisione_turno(self._dec("A", "non_tiene"), self._feed("A", "takeoff"))
        self.assertEqual(r["per_motivo"]["takeoff"]["aperti"], 1)

    def test_decisione_senza_storico_contata_a_parte(self):
        """La history tiene 30 controlli: le decisioni vecchie non sono piu'
        ricostruibili. Vanno dichiarate, non fatte sparire."""
        from discovery_engine import precisione_turno
        r = precisione_turno(self._dec("X", "passo"), {"X": {"history": []}})
        self.assertEqual(r["decisioni_totali"], 1)
        self.assertEqual(r["senza_motivo"], 1)
        self.assertEqual(r["ricostruite"], 0)

    def test_usa_lo_stato_mostrato_AL_MOMENTO_della_decisione(self):
        """Non l'ultimo motivo in assoluto: quello che avevi davanti quando
        hai deciso. Altrimenti si attribuisce l'apertura al motivo sbagliato."""
        from discovery_engine import precisione_turno
        feed = {"A": {"history": [
            {"run_at": "2026-08-01T00:00:00", "state_change": {"type": "takeoff"}},
            {"run_at": "2026-08-05T00:00:00", "state_change": {"type": "rising"}},
        ]}}
        r = precisione_turno(self._dec("A", "in_verifica", at="2026-08-02T00:00:00"), feed)
        self.assertIn("takeoff", r["per_motivo"])
        self.assertNotIn("rising", r["per_motivo"])

    def test_senza_decisioni_dice_non_lo_so(self):
        from discovery_engine import precisione_turno
        r = precisione_turno({}, {})
        self.assertEqual(r["decisioni_totali"], 0)
        self.assertIsNone(r["tasso_apertura_complessivo"])
        self.assertIn("niente da misurare", r["obiezione"])
