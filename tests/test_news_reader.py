# Test del LETTORE "NEWS" del grafo delle fonti (grounding deterministico
# del club dai titoli stampa, senza AI e senza tool a pagamento).
# Funzioni pure su dict/stringhe: niente rete, niente filesystem, niente DB.
#   python3 -m unittest tests/test_news_reader.py -v
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from news_reader import (build_club_lexicon, extract_club_observations,
                         normalize_club)

# lessico costruito dalla pool, come in produzione
POOL = [
    {"club": "Cerezo Osaka"},
    {"club": "FC Imabari"},
    {"club": "Juventus Next Gen"},
    {"club": "Palermo FC"},
    {"club": "Estudiantes de La Plata"},
    {"club": "Sporting CP"},
]
LEX = build_club_lexicon(POOL)


def _item(title, date="Mon, 01 Jul 2026 10:00:00 GMT", url="http://x/1"):
    return {"title": title, "date": date, "url": url}


class TestLessico(unittest.TestCase):
    def test_costruito_dalla_pool(self):
        self.assertEqual(LEX[normalize_club("Cerezo Osaka")], "Cerezo Osaka")
        self.assertIn(normalize_club("Juventus Next Gen"), LEX)

    def test_club_troppo_corti_esclusi(self):
        # sigle e nomi brevi collidono con parole comuni nei titoli: fuori
        lex = build_club_lexicon([{"club": "Bari"}, {"club": "Lens"}, {"club": "AS"}])
        self.assertEqual(lex, {})

    def test_prima_squadra_e_riserve_restano_distinte(self):
        # la differenza che il radar non puo' permettersi di appiattire
        lex = build_club_lexicon([{"club": "Juventus"}, {"club": "Juventus Next Gen"}])
        self.assertEqual(len(lex), 2)

    def test_accumula_dal_grafo_delle_osservazioni(self):
        # un trasferimento porta quasi sempre a un club FUORI dalla pool
        # candidati (il ragazzo sale di livello): senza i club gia' osservati
        # nel grafo il lettore sarebbe cieco proprio sui casi che contano
        osservazioni = {"Q9": {"club": [{"valore": "Borussia Dortmund", "fonte": "news"}]}}
        lex = build_club_lexicon([{"club": "Palermo FC"}], osservazioni)
        self.assertIn(normalize_club("Borussia Dortmund"), lex)
        obs = extract_club_observations(
            [_item("Marco Rossi signs for Borussia Dortmund - Bild")],
            known_clubs={"Palermo FC"}, lexicon=lex)
        self.assertEqual([o["valore"] for o in obs], ["Borussia Dortmund"])

    def test_grafo_assente_non_esplode(self):
        self.assertEqual(build_club_lexicon([], None), {})

    def test_legge_anche_club_risolto_e_alternativo(self):
        lex = build_club_lexicon([{"club_risolto": "Sporting CP",
                                   "club_alternativo": "Cerezo Osaka"}])
        self.assertEqual(len(lex), 2)


class TestEstrazione(unittest.TestCase):
    def test_trasferimento_riconosciuto(self):
        obs = extract_club_observations(
            [_item("Yuki Yokoyama signs for Cerezo Osaka - Nikkan Sports")],
            known_clubs={"FC Imabari"}, lexicon=LEX)
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["valore"], "Cerezo Osaka")
        self.assertEqual(obs[0]["datato_al"], "2026-07-01")
        self.assertEqual(obs[0]["url"], "http://x/1")
        self.assertIn("Nikkan Sports", obs[0]["nota"])

    def test_senza_verbo_di_trasferimento_non_emette(self):
        # un titolo puo' nominare un club per mille motivi (avversario, ex
        # squadra, stadio): senza indizio esplicito si tace
        obs = extract_club_observations(
            [_item("Cerezo Osaka wins 2-0 against FC Imabari - Soccer Digest")],
            known_clubs={"FC Imabari"}, lexicon=LEX)
        self.assertEqual(obs, [])

    def test_club_fuori_dal_lessico_mai_inventato(self):
        # vocabolario chiuso: meglio non vedere il trasferimento che
        # inventarne uno, che finirebbe nel grafo come fatto datato
        obs = extract_club_observations(
            [_item("Yuki Yokoyama signs for Real Madrid Castilla - Marca")],
            known_clubs={"FC Imabari"}, lexicon=LEX)
        self.assertEqual(obs, [])

    def test_conferma_del_club_attuale_non_e_notizia(self):
        obs = extract_club_observations(
            [_item("Yuki Yokoyama signs for FC Imabari - Nikkan Sports")],
            known_clubs={"FC Imabari"}, lexicon=LEX)
        self.assertEqual(obs, [])

    def test_club_prima_del_verbo_ignorato(self):
        # "lascia il Palermo per il ..." - prendere il club sbagliato
        # invertirebbe il trasferimento
        obs = extract_club_observations(
            [_item("Palermo FC starlet joins Juventus Next Gen - TMW")],
            known_clubs={"Palermo FC"}, lexicon=LEX)
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs[0]["valore"], "Juventus Next Gen")

    def test_nessun_club_dopo_il_verbo_non_emette(self):
        obs = extract_club_observations(
            [_item("Yuki Yokoyama joins an unnamed club - Nikkan Sports")],
            known_clubs={"FC Imabari"}, lexicon=LEX)
        self.assertEqual(obs, [])

    def test_testata_non_confonde_il_match(self):
        # una testata tipo "Milan News" farebbe scattare un club sbagliato a
        # ogni titolo se non venisse tolta prima di cercare
        lex = build_club_lexicon([{"club": "Sporting CP"}, {"club": "Cerezo Osaka"}])
        obs = extract_club_observations(
            [_item("Player of the week - Cerezo Osaka Daily")],
            known_clubs={"Sporting CP"}, lexicon=lex)
        self.assertEqual(obs, [])

    def test_lingue_locali(self):
        # la stampa locale (quella che per il two-step flow arriva per prima)
        # scrive nella sua lingua
        for titolo, atteso in [
            ("Il giovane passa al Palermo FC - Giornale di Sicilia", "Palermo FC"),
            ("El juvenil ficha por Estudiantes de La Plata - Ole", "Estudiantes de La Plata"),
            ("Jovem assina com Sporting CP - A Bola", "Sporting CP"),
        ]:
            with self.subTest(titolo=titolo):
                obs = extract_club_observations([_item(titolo)], known_clubs={"FC Imabari"},
                                                lexicon=LEX)
                self.assertEqual([o["valore"] for o in obs], [atteso])

    def test_data_illeggibile_non_inventata(self):
        obs = extract_club_observations(
            [_item("Player signs for Cerezo Osaka - X", date="data-rotta")],
            known_clubs={"FC Imabari"}, lexicon=LEX)
        self.assertEqual(len(obs), 1)
        self.assertIsNone(obs[0]["datato_al"])

    def test_dedup_tra_titoli(self):
        titolo = "Player joins Cerezo Osaka - {}"
        obs = extract_club_observations(
            [_item(titolo.format("Nikkan")), _item(titolo.format("Sponichi"))],
            known_clubs={"FC Imabari"}, lexicon=LEX)
        self.assertEqual(len(obs), 1)

    def test_titoli_vuoti_non_esplodono(self):
        self.assertEqual(extract_club_observations([{}, {"title": ""}],
                                                   known_clubs=set(), lexicon=LEX), [])


class TestIntegrazioneGrafo(unittest.TestCase):
    """L'osservazione emessa dev'essere accettata dal grafo e vincere sui
    claim Wikidata non datati - e' tutto il punto del grounding gratuito."""

    def test_osservazione_news_batte_wikidata_non_datato(self):
        from discovery_engine import record_observation, resolve_field
        cfg = {"piramide": {
            "livelli": {"umano": 0, "news": 2, "wikipedia_torneo": 3, "wikidata": 4},
            "regole_campo": {"club": "dal_basso", "dob": "dall_alto"},
        }}
        store = {}
        record_observation(store, "Q1", "club", "FC Imabari", "wikidata", cfg)
        obs = extract_club_observations(
            [_item("Yuki Yokoyama signs for Cerezo Osaka - Nikkan Sports")],
            known_clubs={"FC Imabari"}, lexicon=LEX)[0]
        self.assertTrue(record_observation(store, "Q1", "club", obs["valore"], "news", cfg,
                                           datato_al=obs["datato_al"], url=obs["url"],
                                           nota=obs["nota"]))
        risolto = resolve_field(store, "Q1", "club", cfg)
        self.assertEqual(risolto["valore"], "Cerezo Osaka")
        self.assertEqual(risolto["fonte"], "news")
        self.assertTrue(risolto["conflitto"])
        self.assertEqual(risolto["alternativa"], "FC Imabari")


if __name__ == "__main__":
    unittest.main()
