# Fix tabellone/archivio: alias senza 404, cache breve delle API pesanti,
# invalidazione su scrittura, errori non memorizzati. Niente rete/DB reali.
#   python3 -m unittest tests/test_tabellone_radar.py -v
import importlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
ROOT = Path(__file__).resolve().parent.parent


class TestTabelloneRadar(unittest.TestCase):
    def setUp(self):
        os.environ.pop("RADAR_ACCESS_KEY", None)
        os.environ.pop("RADAR_GUEST_KEY", None)
        import visual_council_app
        importlib.reload(visual_council_app)
        self.m = visual_council_app
        self.c = self.m.app.test_client()
        de = self.m.discovery_engine
        self.patches = [
            mock.patch.object(de, "track_record_summary", return_value={"flagged": 1}),
            mock.patch.object(de, "validation_coverage_summary", return_value={}),
            mock.patch.object(de, "kenobi_summary", return_value={}),
            mock.patch.object(de, "precisione_turno", return_value={}),
            mock.patch.object(de, "latest_feed", return_value={}),
            mock.patch.object(de, "load_config", return_value={}),
            mock.patch.object(de, "get_watchlist", return_value=set()),
        ]
        self.mocks = [p.start() for p in self.patches]

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def test_alias_non_danno_404(self):
        for src, dst in [("/archivio", "/radar"), ("/avvocato", "/processo"), ("/tabellone", "/processo")]:
            r = self.c.get(src)
            self.assertEqual(r.status_code, 302, src)
            self.assertTrue(r.headers["Location"].endswith(dst), src)

    def test_processo_calcolato_una_volta_poi_cache(self):
        a = self.c.get("/api/radar/processo").get_json()
        b = self.c.get("/api/radar/processo").get_json()
        self.assertEqual(a["status"], "success")
        self.assertEqual(a, b)
        self.assertEqual(self.mocks[0].call_count, 1)

    def test_feed_in_cache(self):
        self.assertEqual(self.c.get("/api/radar/feed").get_json()["status"], "success")
        self.c.get("/api/radar/feed")
        self.assertEqual(self.mocks[4].call_count, 1)

    def test_errore_non_memorizzato(self):
        self.mocks[0].side_effect = RuntimeError("db giu'")
        self.assertEqual(self.c.get("/api/radar/processo").get_json()["status"], "error")
        self.mocks[0].side_effect = None
        self.assertEqual(self.c.get("/api/radar/processo").get_json()["status"], "success")

    def test_scrittura_svuota_cache(self):
        self.c.get("/api/radar/processo")
        with mock.patch.object(self.m.discovery_engine, "set_watchlisted", create=True):
            self.c.post("/api/radar/watchlist", json={"candidate_id": "Q1", "watchlisted": True})
        self.c.get("/api/radar/processo")
        self.assertEqual(self.mocks[0].call_count, 2)

    def test_frontend_ha_timeout_e_errore_visibile(self):
        proc = (ROOT / "templates/processo.html").read_text()
        radar = (ROOT / "templates/radar.html").read_text()
        self.assertIn("AbortController", proc)
        self.assertIn("AbortController", radar)
        self.assertIn("archivio non caricato", radar)


if __name__ == "__main__":
    unittest.main()
