# Test del comando "sample" (bridge Grok/runbook - vedi RUNBOOK_NOMI_GIOCATORI.md):
# fetch_candidate_pool e buzz_score sono mockati (rete vera, niente da fare nei
# test), il resto della pipeline (signal_score/fit_score/needs_more_signal/
# guardia anti-doppione) e' quello reale.
#   python3 -m unittest tests/test_sample_cli.py -v
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discovery_engine as de

CANDIDATES = [
    # saturo su un solo componente (eta' al tetto, niente altro) - deve
    # restare fuori dal dossier AI anche con --with-dossier
    {"candidate_id": "Q1", "name": "Satura Uno", "club": "Foggia Calcio",
     "role": "Attaccante", "dob": "2007-01-01", "source": "wikidata", "tier": "serie_c"},
    # eta' + buzz entrambi disponibili, non saturo - deve generare dossier
    {"candidate_id": "Q2", "name": "Normale Due", "club": "Triestina",
     "role": "Centrocampista", "dob": "2003-06-15", "source": "wikidata", "tier": "serie_c"},
]


def _fake_buzz(candidate, history, cfg):
    if candidate["candidate_id"] == "Q1":
        return {"score": None, "available": False, "reason": "primo run, nessuno storico",
                "mention_count": 0, "snapshot": {"run_at": "2026-01-01T00:00:00+00:00",
                "mention_count": 0, "publishers": [], "tier1_present": False}}
    return {"score": 0.6, "available": True, "sub_scores": {"velocity": 0.6},
            "mention_count": 3, "snapshot": {"run_at": "2026-01-01T00:00:00+00:00",
            "mention_count": 3, "publishers": ["Gazzetta"], "tier1_present": False}}


class TestSampleProfiles(unittest.TestCase):
    def setUp(self):
        self.cfg = de.load_config()

    @patch("discovery_engine._save_json")
    @patch("discovery_engine._load_json", return_value={})
    @patch("discovery_engine.buzz_score", side_effect=_fake_buzz)
    @patch("discovery_engine.fetch_candidate_pool", return_value=CANDIDATES)
    def test_forma_output_e_dati_reali_non_inventati(self, _pool, _buzz, _load, _save):
        result = de.sample_profiles(2, "tactical_profile", self.cfg, with_dossier=False)
        self.assertEqual(result["with_dossier"], False)
        names = {p["name"] for p in result["profiles"]}
        self.assertTrue(names.issubset({"Satura Uno", "Normale Due"}))
        for p in result["profiles"]:
            self.assertIn("bullets", p)
            self.assertIn("Dossier AI non generato", p["bullets"][-1])
            self.assertIsNone(p["dossier"])

    @patch("discovery_engine.run_swarm_dossier")
    @patch("discovery_engine._save_json")
    @patch("discovery_engine._load_json", return_value={})
    @patch("discovery_engine.buzz_score", side_effect=_fake_buzz)
    @patch("discovery_engine.fetch_candidate_pool", return_value=CANDIDATES)
    def test_candidato_saturo_salta_il_dossier_anche_con_with_dossier(
            self, _pool, _buzz, _load, _save, mock_dossier):
        mock_dossier.return_value = {"cronista": "x", "verificatore": "y", "scettico": "z",
                                      "giudice": {"vale_la_pena": True, "motivazione": "ok"}}
        result = de.sample_profiles(2, "tactical_profile", self.cfg, with_dossier=True)

        by_name = {p["name"]: p for p in result["profiles"]}
        # Satura Uno: solo eta', gia' al tetto -> nessuna chiamata AI spesa
        self.assertIn("skipped", by_name["Satura Uno"]["dossier"])
        # Normale Due: eta'+buzz, non saturo -> il dossier vero viene generato
        self.assertEqual(by_name["Normale Due"]["dossier"]["giudice"]["motivazione"], "ok")
        # la chiamata "costosa" e' partita SOLO per il candidato non saturo
        mock_dossier.assert_called_once()
        self.assertEqual(mock_dossier.call_args[0][0]["candidate_id"], "Q2")


if __name__ == "__main__":
    unittest.main()
