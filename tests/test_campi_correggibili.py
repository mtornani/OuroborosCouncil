# Test della correzione umana generalizzata (club/ruolo/nazionalita').
#
# Prima solo il club era risolvibile dal grafo delle fonti e correggibile a
# mano. Generalizzato dopo il caso Robin Visser (2026-08): il dossier AI
# l'aveva detto "calciatore tedesco" (era francese) e non esisteva NESSUN
# posto dove scrivere quello vero - solo il club aveva un bottone di
# conferma, e pure quello solo quando il sistema stesso proponeva un cambio.
#
#   python3 -m unittest tests/test_campi_correggibili.py -v
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discovery_engine as de
from discovery_engine import (record_observation, resolve_field,
                              _sync_graph_fields, confirm_field, confirm_club,
                              CAMPI_UMANO_CORREGGIBILI)

CFG = {
    "piramide": {
        "livelli": {"umano": 0, "news": 2, "wikipedia_torneo": 3, "wikidata": 4},
        "regole_campo": {"club": "dal_basso", "dob": "dall_alto",
                         "role": "dal_basso", "nationality_label": "dal_basso"},
        "finestra_transizione_giorni": 45,
    }
}


class TestCampiCorreggibili(unittest.TestCase):
    def test_club_role_nationality_sono_correggibili_dob_no(self):
        # "dob" e' deliberatamente fuori: la correzione di un'anagrafica e'
        # un intervento diverso, non ancora scoperto qui (vedi commento su
        # CAMPI_UMANO_CORREGGIBILI)
        self.assertEqual(set(CAMPI_UMANO_CORREGGIBILI), {"club", "role", "nationality_label"})
        self.assertNotIn("dob", CAMPI_UMANO_CORREGGIBILI)


class TestSyncGraphFields(unittest.TestCase):
    """_sync_graph_fields e' pura su dict (store passato per riferimento):
    stesso stile di test di record_observation/resolve_field in
    test_grafo_fonti.py, niente mock di file I/O."""

    def test_lettori_scrivono_tutti_e_tre_i_campi(self):
        candidates = [{"candidate_id": "Q1", "source": "wikidata",
                      "club": "FC Imabari", "role": "Attaccante",
                      "nationality_label": "Giappone"}]
        store = {}
        _sync_graph_fields(candidates, store, CFG)
        self.assertEqual(store["Q1"]["club"][0]["valore"], "FC Imabari")
        self.assertEqual(store["Q1"]["role"][0]["valore"], "Attaccante")
        self.assertEqual(store["Q1"]["nationality_label"][0]["valore"], "Giappone")

    def test_risolutore_attacca_risolto_e_provenienza_per_ogni_campo(self):
        candidates = [{"candidate_id": "Q1", "source": "wikidata",
                      "club": "FC Imabari", "role": "Attaccante",
                      "nationality_label": "Giappone"}]
        store = {}
        _sync_graph_fields(candidates, store, CFG)
        c = candidates[0]
        self.assertEqual(c["club_risolto"], "FC Imabari")
        self.assertEqual(c["role_risolto"], "Attaccante")
        self.assertEqual(c["nationality_label_risolto"], "Giappone")
        self.assertEqual(c["club_provenienza"]["fonte"], "wikidata")
        self.assertEqual(c["role_provenienza"]["fonte"], "wikidata")
        self.assertEqual(c["nationality_label_provenienza"]["fonte"], "wikidata")

    def test_campo_vuoto_non_genera_osservazione_ne_crash(self):
        # un candidato senza ruolo/nazionalita' nel fetch grezzo (capita,
        # dati parziali) non deve far esplodere il sync ne' inventare nulla
        candidates = [{"candidate_id": "Q1", "source": "wikidata", "club": "FC Imabari"}]
        store = {}
        _sync_graph_fields(candidates, store, CFG)
        self.assertNotIn("role", store.get("Q1", {}))
        self.assertNotIn("nationality_label", store.get("Q1", {}))
        self.assertNotIn("role_risolto", candidates[0])

    def test_fonte_non_censita_non_scrive_nulla(self):
        # source="manual_watchlist" non e' nella piramide -> nessun lettore
        # automatico associato, nessuna osservazione (coerente con
        # _READER_FONTE del vecchio blocco solo-club)
        candidates = [{"candidate_id": "Q1", "source": "manual_watchlist",
                      "club": "X", "role": "Portiere", "nationality_label": "Italia"}]
        store = {}
        _sync_graph_fields(candidates, store, CFG)
        self.assertEqual(store, {})

    def test_correzione_umana_vince_su_lettore_automatico(self):
        # simula: un run automatico ha gia' scritto "calciatore tedesco",
        # poi arriva una correzione umana - deve vincere lei (livello 0)
        candidates = [{"candidate_id": "Q1", "source": "wikidata",
                      "club": "Dijon", "role": "Portiere",
                      "nationality_label": "Germania"}]
        store = {}
        _sync_graph_fields(candidates, store, CFG)
        record_observation(store, "Q1", "nationality_label", "Francia", "umano", CFG,
                           datato_al="2026-08-17")
        resolution = resolve_field(store, "Q1", "nationality_label", CFG)
        self.assertEqual(resolution["valore"], "Francia")
        self.assertEqual(resolution["fonte"], "umano")


class TestConfirmField(unittest.TestCase):
    """confirm_field tocca _load_json/_save_json/load_config: mockati come
    in test_sample_cli.py, niente file reali toccati dal test."""

    @patch("discovery_engine._save_json")
    @patch("discovery_engine._load_json", return_value={})
    def test_conferma_nazionalita_registra_e_risolve(self, mock_load, mock_save):
        result = confirm_field("Q1", "nationality_label", "Francia")
        self.assertTrue(result["registrata"])
        self.assertEqual(result["nationality_label_provenienza"]["valore"], "Francia")
        self.assertEqual(result["nationality_label_provenienza"]["fonte"], "umano")
        mock_save.assert_called_once()

    @patch("discovery_engine._save_json")
    @patch("discovery_engine._load_json", return_value={})
    def test_conferma_ruolo(self, mock_load, mock_save):
        result = confirm_field("Q1", "role", "Difensore")
        self.assertEqual(result["role_provenienza"]["valore"], "Difensore")

    @patch("discovery_engine._save_json")
    @patch("discovery_engine._load_json", return_value={})
    def test_confirm_club_alias_ritorna_forma_storica(self, mock_load, mock_save):
        # confirm_club deve restare compatibile con la route esistente
        # (/api/radar/club-conferma): stessa forma di prima, {"registrata",
        # "club_provenienza"} - non {"club_label_provenienza"} o simili
        result = confirm_club("Q1", "Cerezo Osaka")
        self.assertIn("registrata", result)
        self.assertIn("club_provenienza", result)
        self.assertEqual(result["club_provenienza"]["valore"], "Cerezo Osaka")

    @patch("discovery_engine._save_json")
    @patch("discovery_engine._load_json", return_value={})
    def test_valore_vuoto_non_registra(self, mock_load, mock_save):
        # record_observation gia' rifiuta un valore vuoto - confirm_field
        # non deve mascherare quel rifiuto da successo
        result = confirm_field("Q1", "role", "")
        self.assertFalse(result["registrata"])
        mock_save.assert_not_called()


if __name__ == "__main__":
    unittest.main()
