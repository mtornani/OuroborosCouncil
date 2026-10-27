# Date di nascita implausibili da Wikidata (es. Omar Arellano "2020" -> 6 anni)
import sys, unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import discovery_engine as de


def row(dob, prec="11"):
    return {"dob": {"value": dob + "T00:00:00Z"}, "dobPrecision": {"value": prec}}


class TestDobPlausibile(unittest.TestCase):
    def test_bambino_scartato(self):
        self.assertIsNone(de._precise_dob(row("2020-06-18")))

    def test_futura_scartata(self):
        futuro = (datetime.now(timezone.utc) + timedelta(days=400)).strftime("%Y-%m-%d")
        self.assertIsNone(de._precise_dob(row(futuro)))

    def test_giovane_vero_tenuto(self):
        self.assertEqual(de._precise_dob(row("2008-03-01")), "2008-03-01")

    def test_precisione_anno_resta_scartata(self):
        self.assertIsNone(de._precise_dob(row("2005-01-01", "9")))


if __name__ == "__main__":
    unittest.main()
