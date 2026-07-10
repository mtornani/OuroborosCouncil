# Test del gate d'accesso (chiave vera + chiave ospite di sola lettura).
# Usa Flask test_client, niente rete/DB reali.
#   python3 -m unittest tests/test_access_gate.py -v
import importlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestAccessGate(unittest.TestCase):
    def setUp(self):
        os.environ["RADAR_ACCESS_KEY"] = "vera123"
        os.environ["RADAR_GUEST_KEY"] = "ospite456"
        global app_mod
        import visual_council_app as app_mod
        importlib.reload(app_mod)
        self.app_mod = app_mod

    def tearDown(self):
        os.environ.pop("RADAR_ACCESS_KEY", None)
        os.environ.pop("RADAR_GUEST_KEY", None)

    def client(self):
        return self.app_mod.app.test_client()

    def test_nessuna_chiave_nega(self):
        self.assertEqual(self.client().get("/turno").status_code, 401)

    def test_chiave_vera_apre_e_mette_cookie(self):
        r = self.client().get("/turno?key=vera123")
        self.assertEqual(r.status_code, 302)

    def test_chiave_vera_permette_scritture(self):
        c = self.client()
        c.get("/turno?key=vera123")
        r = c.post("/api/radar/watchlist", json={"candidate_id": "Q1", "watchlisted": True})
        self.assertEqual(r.status_code, 200)

    def test_chiave_ospite_apre_pagine(self):
        for path in ("/radar", "/mappa", "/processo"):
            with self.subTest(path=path):
                c = self.client()
                c.get("/turno?guest_key=ospite456")
                self.assertEqual(c.get(path).status_code, 200)

    def test_chiave_ospite_legge_api(self):
        r = self.client().get("/api/radar/health?guest_key=ospite456")
        self.assertEqual(r.status_code, 200)

    def test_chiave_ospite_NON_puo_lanciare_scansione(self):
        r = self.client().post("/api/radar/refresh?guest_key=ospite456", json={})
        self.assertEqual(r.status_code, 403)

    def test_chiave_ospite_NON_puo_confermare_club(self):
        r = self.client().post("/api/radar/club-conferma?guest_key=ospite456",
                               json={"candidate_id": "Q1", "club": "X"})
        self.assertEqual(r.status_code, 403)

    def test_cookie_ospite_persiste_ma_resta_sola_lettura(self):
        c = self.client()
        c.get("/turno?guest_key=ospite456")  # imposta il cookie
        r = c.post("/api/radar/watchlist", json={"candidate_id": "Q1", "watchlisted": True})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(c.get("/radar").status_code, 200)

    def test_chiave_ospite_sbagliata_nega(self):
        r = self.client().get("/turno?guest_key=nonequellagiusta")
        self.assertEqual(r.status_code, 401)

    def test_senza_guest_key_configurata_il_parametro_non_apre_nulla(self):
        os.environ["RADAR_GUEST_KEY"] = ""
        importlib.reload(self.app_mod)
        r = self.app_mod.app.test_client().get("/turno?guest_key=qualsiasi")
        self.assertEqual(r.status_code, 401)


if __name__ == "__main__":
    unittest.main()
