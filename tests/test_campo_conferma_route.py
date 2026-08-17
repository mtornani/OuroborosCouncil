# Test della route /api/radar/campo-conferma (correzione umana libera:
# club/ruolo/nazionalita' - vedi tests/test_campi_correggibili.py per la
# generalizzazione del grafo sottostante).
# Flask test_client, discovery_engine.confirm_field mockato: niente
# file/DB reali toccati, questo file testa solo la route.
#   python3 -m unittest tests/test_campo_conferma_route.py -v
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import visual_council_app as app_mod


class TestCampoConfermaRoute(unittest.TestCase):
    def client(self):
        return app_mod.app.test_client()

    def test_campo_fuori_allowlist_rifiutato_esplicitamente(self):
        # "dob" non e' in CAMPI_UMANO_CORREGGIBILI: deve fallire con un
        # messaggio chiaro, non scrivere silenziosamente nel grafo un'
        # osservazione che nessun lettore/UI rileggera' mai
        r = self.client().post("/api/radar/campo-conferma",
                               json={"candidate_id": "Q1", "campo": "dob", "valore": "2006-01-01"})
        data = r.get_json()
        self.assertEqual(data["status"], "error")
        self.assertIn("dob", data["message"])

    def test_campo_inventato_rifiutato(self):
        r = self.client().post("/api/radar/campo-conferma",
                               json={"candidate_id": "Q1", "campo": "altezza_cm", "valore": "180"})
        self.assertEqual(r.get_json()["status"], "error")

    def test_candidate_id_mancante_rifiutato(self):
        r = self.client().post("/api/radar/campo-conferma",
                               json={"campo": "role", "valore": "Portiere"})
        self.assertEqual(r.get_json()["status"], "error")

    def test_valore_vuoto_rifiutato(self):
        r = self.client().post("/api/radar/campo-conferma",
                               json={"candidate_id": "Q1", "campo": "role", "valore": "  "})
        self.assertEqual(r.get_json()["status"], "error")

    @patch("discovery_engine.confirm_field")
    def test_campo_valido_chiama_confirm_field(self, mock_confirm):
        mock_confirm.return_value = {"registrata": True,
                                     "nationality_label_provenienza": {"valore": "Francia", "fonte": "umano"}}
        r = self.client().post("/api/radar/campo-conferma",
                               json={"candidate_id": "Q1", "campo": "nationality_label", "valore": "Francia"})
        data = r.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["campo"], "nationality_label")
        self.assertEqual(data["nationality_label_provenienza"]["valore"], "Francia")
        mock_confirm.assert_called_once_with("Q1", "nationality_label", "Francia")

    @patch("discovery_engine.confirm_field", side_effect=RuntimeError("DB giu'"))
    def test_eccezione_diventa_errore_leggibile_non_500(self, mock_confirm):
        r = self.client().post("/api/radar/campo-conferma",
                               json={"candidate_id": "Q1", "campo": "role", "valore": "Portiere"})
        self.assertEqual(r.status_code, 200)  # la route la intercetta, non fa 500
        self.assertEqual(r.get_json()["status"], "error")

    @patch("discovery_engine.confirm_field")
    def test_caso_robin_visser_nazionalita_corretta_end_to_end(self, mock_confirm):
        # il caso concreto che ha motivato questa route: il dossier AI aveva
        # scritto "calciatore tedesco" per un giocatore francese, e non
        # esisteva un modo di correggerlo prima di questa route
        mock_confirm.return_value = {"registrata": True,
                                     "nationality_label_provenienza": {
                                         "valore": "Francia", "fonte": "umano",
                                         "spiegazione": "confermato a mano il 2026-08-17",
                                     }}
        r = self.client().post("/api/radar/campo-conferma", json={
            "candidate_id": "Q124745247", "campo": "nationality_label", "valore": "Francia",
        })
        data = r.get_json()
        self.assertEqual(data["status"], "success")
        self.assertEqual(data["nationality_label_provenienza"]["fonte"], "umano")


if __name__ == "__main__":
    unittest.main()
