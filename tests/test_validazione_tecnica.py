# Test del LAYER F - VALIDAZIONE TECNICA (il segnale costoso).
#
# Il layer esiste per chiudere la lacuna dichiarata del radar: fino al Layer E
# si misura solo l'ATTENZIONE, e scrivere un articolo non costa nulla. Qui si
# misura quanto qualcuno CHE RISCHIAVA QUALCOSA ha gia' puntato sul giocatore.
#
# Questi test bloccano le due proprieta' da cui dipende tutto il resto:
#
#  1. MONOTONIA - la validazione puo' solo CONFERMARE, mai CONDANNARE.
#     Aggiungere un record non deve MAI abbassare il punteggio. E' cio' che
#     rende il layer sicuro su fonti incomplete (audit README: 52% dei QID
#     senza club su Wikidata): se aggiungere evidenza potesse far scendere il
#     numero, il punteggio direbbe piu' cose sulla COPERTURA della fonte che
#     sul giocatore. E' anche il motivo del noisy-OR al posto della media.
#
#  2. I TRE STATI RESTANO DISTINTI - "non ho potuto guardare"
#     (non_validabile) non deve mai diventare indistinguibile da "ho guardato
#     e non c'era niente" (non_corroborato), ne' da un voto basso.
#
# Nessuna rete: validation_score e' una funzione pura, i record di carriera
# arrivano gia' letti.
#
#   python3 -m unittest tests/test_validazione_tecnica.py -v
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import yaml

from discovery_engine import (detect_state_change, evidence_quadrant,
                              nuove_prove_costose, player_caveats,
                              validation_score, _banda_selezione)

CFG = yaml.safe_load(open(Path(__file__).resolve().parent.parent / "radar_config.yaml",
                          encoding="utf-8"))
VT = CFG["validazione_tecnica"]

OGGI = datetime.now()


def _anni_fa(anni: float) -> str:
    return (OGGI - timedelta(days=anni * 365.25)).strftime("%Y-%m-%d")


def _carriera(memberships, stato="ok"):
    return {"memberships": memberships, "fonte": "wikidata",
            "letto_il": OGGI.strftime("%Y-%m-%d"), "stato_lettura": stato}


def _club(team="Club X", qid="Q100", league="Q607965", apps=25, start_anni_fa=1.0):
    """Una membership di club. Default: stagione piena in Serie C."""
    return {"team": team, "team_qid": qid, "league_qid": league, "apps": apps,
            "start": _anni_fa(start_anni_fa), "end": None, "is_national": False}


def _nazionale(team="Italy national under-19 football team", qid="Q900", apps=3,
               start_anni_fa=0.5):
    return {"team": team, "team_qid": qid, "league_qid": None, "apps": apps,
            "start": _anni_fa(start_anni_fa), "end": None, "is_national": True}


def _giocatore(eta=18.0):
    return {"candidate_id": "Q1", "name": "Test", "dob": _anni_fa(eta), "tier": "serie_c"}


def _score(candidate, carriera):
    return validation_score(candidate, carriera, CFG)


# ======================================================================
class TestTreStatiDistinti(unittest.TestCase):
    """La distinzione fra 'non ho potuto guardare' e 'ho guardato e non c'era
    niente' e' il cuore onesto del layer. Se collassano, il layer mente."""

    def test_carriera_mai_letta_e_non_validabile(self):
        r = _score(_giocatore(), None)
        self.assertEqual(r["stato"], "non_validabile")
        self.assertIsNone(r["validation_score"])

    def test_fonte_muta_e_non_validabile_non_zero(self):
        r = _score(_giocatore(), _carriera([], stato="timeout WDQS"))
        self.assertEqual(r["stato"], "non_validabile")
        # il punto: NON e' zero, e' assenza di numero
        self.assertIsNone(r["validation_score"])
        self.assertIn("non disponibile", r["motivo"].lower())

    def test_nessuna_membership_e_non_validabile(self):
        r = _score(_giocatore(), _carriera([]))
        self.assertEqual(r["stato"], "non_validabile")

    def test_membership_senza_nulla_di_costoso_e_non_corroborato(self):
        """Sta in rosa ma nessuna presenza registrata: le fonti si sono lette
        DAVVERO e non c'era niente di costoso. Diverso da non_validabile."""
        r = _score(_giocatore(), _carriera([_club(apps=None)]))
        self.assertEqual(r["stato"], "non_corroborato")
        self.assertIsNone(r["validation_score"])
        self.assertEqual(r["copertura"]["memberships_lette"], 1)

    def test_non_corroborato_non_e_una_condanna(self):
        r = _score(_giocatore(), _carriera([_club(apps=None)]))
        self.assertIn("NON una prova contraria", r["motivo"])

    def test_presenza_in_rosa_da_sola_non_valida(self):
        """Esserci e basta costa poco (costo_segnale.presenza_in_rosa = 0.2):
        non deve validare nessuno da solo."""
        r = _score(_giocatore(), _carriera([_club(apps=0)]))
        self.assertNotEqual(r["stato"], "validato")


# ======================================================================
class TestMonotonia(unittest.TestCase):
    """LA REGOLA CARDINALE. Aggiungere evidenza non puo' mai far scendere il
    punteggio. Con una media pesata questo test fallirebbe - e' esattamente
    il motivo per cui la combinazione e' noisy-OR."""

    def test_aggiungere_una_membership_non_abbassa_mai(self):
        g = _giocatore(18.0)
        base = _score(g, _carriera([_club(apps=25)]))["validation_score"]
        aggiunte = [
            _club(team="Altro", qid="Q101", apps=1, league="Q1141778"),   # poche presenze, categoria bassa
            _club(team="Riserve", qid="Q102", apps=30, league=None),      # livello ignoto
            _nazionale(apps=0),                                            # convocazione senza presenze
            _club(team="Vecchio", qid="Q103", apps=2, start_anni_fa=3.0),  # roba vecchia e magra
        ]
        for extra in aggiunte:
            con_extra = _score(g, _carriera([_club(apps=25), extra]))["validation_score"]
            self.assertGreaterEqual(
                con_extra, base,
                f"aggiungere {extra['team']} ha ABBASSATO il punteggio "
                f"({base} -> {con_extra}): la monotonia e' rotta")

    def test_monotonia_su_accumulo_progressivo(self):
        g = _giocatore(18.0)
        pezzi = [_club(apps=25), _nazionale(), _club(team="B", qid="Q104", apps=12, league="Q194052"),
                 _club(team="C", qid="Q105", apps=3, league="Q1141778")]
        precedente = 0.0
        for i in range(1, len(pezzi) + 1):
            r = _score(g, _carriera(pezzi[:i]))
            attuale = r["validation_score"] or 0.0
            self.assertGreaterEqual(attuale, precedente,
                                    f"il punteggio e' sceso al passo {i}")
            precedente = attuale

    def test_una_categoria_inferiore_non_penalizza_mai(self):
        """Sui dati liberi non si distingue un prestito di crescita da un
        ridimensionamento: nel dubbio si tace, non si condanna."""
        g = _giocatore(18.0)
        solo_alto = _score(g, _carriera([_club(apps=25, league="Q194052", start_anni_fa=2.0)]))
        poi_giu = _score(g, _carriera([
            _club(apps=25, league="Q194052", start_anni_fa=2.0),
            _club(team="Giu", qid="Q106", apps=20, league="Q1141778", start_anni_fa=0.5),
        ]))
        self.assertGreaterEqual(poi_giu["validation_score"], solo_alto["validation_score"])


# ======================================================================
class TestPrecocitaELivello(unittest.TestCase):
    """Il segnale non e' 'ha giocato', e' 'ha giocato COSI' GIOVANE a QUEL
    livello' - la stessa idea del Layer A, ma su minuti veri invece che sulla
    semplice presenza in rosa."""

    def test_piu_giovane_vale_di_piu_a_parita_di_presenze(self):
        giovane = _score(_giocatore(17.0), _carriera([_club(apps=25)]))["validation_score"]
        maturo = _score(_giocatore(23.5), _carriera([_club(apps=25)]))["validation_score"]
        self.assertGreater(giovane, maturo)

    def test_categoria_piu_alta_vale_di_piu_a_parita_di_tutto(self):
        g = _giocatore(18.0)
        serie_b = _score(g, _carriera([_club(apps=25, league="Q194052")]))["validation_score"]
        serie_d = _score(g, _carriera([_club(apps=25, league="Q1141778")]))["validation_score"]
        self.assertGreater(serie_b, serie_d)

    def test_stagione_piena_di_un_17enne_in_serie_c_e_validata(self):
        """Il CASO CENTRALE del radar. Una taratura in cui questo non passa
        rende il layer inutile per la pool principale - errore realmente
        commesso in fase di sviluppo (dava 36/100), vedi il commento sulla
        taratura in radar_config.yaml."""
        r = _score(_giocatore(17.4), _carriera([_club(apps=25, league="Q607965")]))
        self.assertEqual(r["stato"], "validato")
        self.assertGreaterEqual(r["validation_score"], VT["quadranti"]["soglia_validazione"])

    def test_eta_alla_firma_ignota_usa_il_pavimento_non_una_stima(self):
        m = _club(apps=25)
        m["start"] = None
        r = _score(_giocatore(17.0), _carriera([m]))
        self.assertEqual(r["stato"], "validato")
        self.assertEqual(r["copertura"]["senza_data"], 1)
        # senza data si applica il pavimento: vale meno del caso datato
        datato = _score(_giocatore(17.0), _carriera([_club(apps=25)]))
        self.assertLess(r["validation_score"], datato["validation_score"])

    def test_ogni_salto_verso_lalto_lascia_la_sua_prova(self):
        """Il punteggio prende il salto migliore, ma la scheda deve mostrarli
        tutti: legare le due cose nascondeva il caso del secondo salto piu'
        piccolo del primo, facendo sparire il movimento PIU' RECENTE - per uno
        scout spesso quello che conta di piu'."""
        # Due salti ENTRAMBI in salita, il secondo piu' piccolo del primo:
        # quarta -> terza (+0.15) -> seconda (+0.12). Sotto la vecchia logica
        # il secondo non lasciava prova perche' non batteva il massimo.
        # (Una discesa dal picco resterebbe giustamente non contata: vedi
        # test_una_categoria_inferiore_non_penalizza_mai.)
        g = _giocatore(19.0)
        r = _score(g, _carriera([
            _club(team="Quarta", qid="Q200", league="Q1141778", apps=20, start_anni_fa=1.9),
            _club(team="Terza", qid="Q201", league="Q607965", apps=15, start_anni_fa=1.2),
            _club(team="Seconda", qid="Q202", league="Q194052", apps=18, start_anni_fa=0.4),
        ]))
        salti = [p for p in r["prove"] if p["tipo"] == "salto"]
        self.assertEqual(len(salti), 2, "un salto verso l'alto non ha lasciato prova")
        self.assertTrue(any("Seconda" in p["testo"] for p in salti),
                        "il salto piu' recente e' sparito dalla scheda")

    def test_lega_ignota_finisce_in_copertura_non_a_zero(self):
        r = _score(_giocatore(18.0), _carriera([_club(apps=20, league="Q999999")]))
        self.assertEqual(r["copertura"]["presenze_livello_ignoto"], 1)
        # conta comunque come scommettitore: qualcuno l'ha fatto giocare
        self.assertEqual(r["indipendenza"]["scommettitori"], 1)


# ======================================================================
class TestSelezioneEsterna(unittest.TestCase):
    """La nazionale pesa piu' di tutto perche' e' l'unico valutatore che NON
    possiede il cartellino: il club ha interesse a gonfiare il proprio asset,
    la federazione no."""

    def test_banda_riconosciuta_dalletichetta(self):
        self.assertEqual(_banda_selezione("Italy national under-19 football team", VT), "U19")
        self.assertEqual(_banda_selezione("Brazil U-17 national team", VT), "U17")
        self.assertEqual(_banda_selezione("Italy national football team", VT), "senior")

    def test_banda_non_interpretabile_usa_la_piu_prudente(self):
        """Nel dubbio non si gonfia mai."""
        self.assertEqual(_banda_selezione(None, VT), VT["selezione_banda_ignota"])

    def test_convocazione_senza_presenze_vale_gia(self):
        """L'ATTO della selezione e' la scommessa; i minuti la rifiniscono."""
        r = _score(_giocatore(17.0), _carriera([_nazionale(apps=0)]))
        self.assertEqual(r["stato"], "validato")
        self.assertGreater(r["validation_score"], 0)

    def test_convocazione_precoce_vale_piu_di_una_in_fascia(self):
        precoce = _score(_giocatore(16.5), _carriera([_nazionale()]))["validation_score"]
        in_fascia = _score(_giocatore(18.9), _carriera([_nazionale()]))["validation_score"]
        self.assertGreater(precoce, in_fascia)

    def test_selezione_e_presenze_insieme_valgono_piu_di_ciascuna(self):
        g = _giocatore(17.5)
        solo_club = _score(g, _carriera([_club(apps=25)]))["validation_score"]
        solo_naz = _score(g, _carriera([_nazionale()]))["validation_score"]
        insieme = _score(g, _carriera([_club(apps=25), _nazionale()]))["validation_score"]
        self.assertGreater(insieme, max(solo_club, solo_naz))


# ======================================================================
class TestIndipendenzaEProve(unittest.TestCase):

    def test_indipendenza_conta_soggetti_distinti(self):
        r = _score(_giocatore(18.0), _carriera([
            _club(apps=20, qid="Q100"), _club(team="B", qid="Q101", apps=15, league="Q194052"),
            _nazionale(),
        ]))
        self.assertEqual(r["indipendenza"]["scommettitori"], 3)
        self.assertTrue(r["indipendenza"]["corroborato"])

    def test_indipendenza_non_entra_nel_punteggio(self):
        """E' una misura di CORROBORAZIONE, non di forza: mescolarla farebbe
        scendere il punteggio di chi ha una prova sola ma schiacciante, cioe'
        una condanna per assenza di dati."""
        uno = _score(_giocatore(17.0), _carriera([_club(apps=25)]))
        self.assertEqual(uno["indipendenza"]["scommettitori"], 1)
        self.assertFalse(uno["indipendenza"]["corroborato"])
        self.assertEqual(uno["stato"], "validato")  # resta validato lo stesso

    def test_ogni_punteggio_porta_le_sue_prove(self):
        """Un punteggio senza la lista di cosa lo sostiene sarebbe il numero
        da prendere sulla fiducia che il progetto rifiuta ovunque."""
        r = _score(_giocatore(17.0), _carriera([_club(apps=25), _nazionale()]))
        self.assertEqual(len(r["prove"]), 2)
        for p in r["prove"]:
            self.assertTrue(p["testo"])
            self.assertIn("fonte", p)
        # ordinate per costo del segnale: la nazionale prima delle presenze
        self.assertEqual(r["prove"][0]["tipo"], "nazionale")

    def test_il_buzz_non_entra_mai_nella_validazione(self):
        """INVARIANTE: cio' che il buzz gia' misura non deve mai contare qui,
        altrimenti si conta due volte lo stesso bit e i due assi smettono di
        essere indipendenti."""
        self.assertEqual(VT["costo_segnale"]["menzione_stampa"], 0.0)
        r = _score(_giocatore(17.0), _carriera([_club(apps=25)]))
        self.assertNotIn("menzione", str(r["componenti"]).lower())
        for p in r["prove"]:
            self.assertGreater(p["costo"], 0.0)


# ======================================================================
class TestQuadranti(unittest.TestCase):
    """I due assi restano separati: sommarli farebbe collassare sullo stesso
    numero i due casi piu' opposti che esistono."""

    def _val(self, punteggio, stato="validato"):
        return {"validation_score": punteggio, "stato": stato}

    def test_tesoro_silenzioso_e_il_caso_che_prima_era_invisibile(self):
        q = evidence_quadrant(10, self._val(70), CFG)
        self.assertEqual(q["quadrante"], "tesoro_silenzioso")

    def test_confermato(self):
        q = evidence_quadrant(80, self._val(70), CFG)
        self.assertEqual(q["quadrante"], "confermato")

    def test_solo_rumore_e_la_firma_del_falso_positivo(self):
        q = evidence_quadrant(80, self._val(None, "non_corroborato"), CFG)
        self.assertEqual(q["quadrante"], "solo_rumore")

    def test_quiete(self):
        q = evidence_quadrant(10, self._val(None, "non_corroborato"), CFG)
        self.assertEqual(q["quadrante"], "quiete")

    def test_non_validabile_non_diventa_mai_solo_rumore(self):
        """IL PUNTO PIU' DELICATO. Se non si e' potuto leggere nulla, un buzz
        alto NON deve trasformarsi in un'accusa: e' assenza di informazione,
        non prova contraria."""
        q = evidence_quadrant(95, self._val(None, "non_validabile"), CFG)
        self.assertEqual(q["quadrante"], "indeterminato")
        self.assertNotEqual(q["quadrante"], "solo_rumore")

    def test_quadrante_sempre_presente_anche_senza_dati(self):
        """Niente sparisce in silenzio: e' la regola del progetto."""
        q = evidence_quadrant(None, None, CFG)
        self.assertIn("quadrante", q)
        self.assertEqual(q["quadrante"], "indeterminato")


# ======================================================================
class TestNuoveProveCostose(unittest.TestCase):
    """Alimenta IL TURNO: un fatto costoso NUOVO e' l'evento piu' importante
    che il radar possa riportare, ma non deve diventare rumore permanente."""

    def test_prima_lettura_non_genera_allarme(self):
        r = _score(_giocatore(17.0), _carriera([_club(apps=25)]))
        self.assertEqual(nuove_prove_costose(r, None), [])
        self.assertEqual(nuove_prove_costose(r, {}), [])

    def test_prima_convocazione_e_un_evento(self):
        g = _giocatore(17.0)
        prima = _score(g, _carriera([_club(apps=25)]))
        dopo = _score(g, _carriera([_club(apps=25), _nazionale()]))
        nuove = nuove_prove_costose(dopo, prima)
        self.assertEqual(len(nuove), 1)
        self.assertEqual(nuove[0]["tipo"], "nazionale")

    def test_solo_piu_presenze_non_generano_allarme(self):
        """Le presenze crescono ogni settimana: un confronto numerico farebbe
        scattare l'allarme a ogni scansione, cioe' rumore permanente."""
        g = _giocatore(17.0)
        prima = _score(g, _carriera([_club(apps=20)]))
        dopo = _score(g, _carriera([_club(apps=24)]))
        self.assertEqual(nuove_prove_costose(dopo, prima), [])


# ======================================================================
class TestIntegrazioneTurno(unittest.TestCase):
    """Il Layer F non e' un campo da mostrare: guida IL TURNO. Un fatto
    costoso nuovo e' l'unico motivo di revisione in cui a muoversi non e'
    l'attenzione ma qualcosa che qualcuno ha pagato."""

    def _sonda(self, **kw):
        base = dict(candidate={"name": "X"},
                    previous_last_entry={"signal_score": 50, "partial_data": False},
                    previous_dossier=None, current_dossier=None,
                    current_partial_data=False, bayes=None,
                    cusum_state={"pos": 0.0, "neg": 0.0}, cfg=CFG,
                    buzz_detail=None, curve=None)
        base.update(kw)
        return detect_state_change(**base)

    def test_nuova_convocazione_apre_il_turno(self):
        g = _giocatore(17.0)
        prima = _score(g, _carriera([_club(apps=25)]))
        dopo = _score(g, _carriera([_club(apps=25), _nazionale()]))
        ev = self._sonda(validazione=dopo, validazione_precedente=prima)
        self.assertIsNotNone(ev)
        self.assertEqual(ev["type"], "costoso")
        self.assertEqual(ev["tag"], "QUALCUNO CI HA PUNTATO")

    def test_nessun_fatto_nuovo_non_genera_nulla(self):
        """Non deve ripresentarsi identico a ogni scansione: sarebbe un evento
        puntuale trasformato in rumore permanente."""
        g = _giocatore(17.0)
        v = _score(g, _carriera([_club(apps=25), _nazionale()]))
        self.assertIsNone(self._sonda(validazione=v, validazione_precedente=v))

    def test_la_sonda_regge_senza_validazione(self):
        """Retrocompatibilita': i due argomenti sono opzionali e il resto della
        sonda deve funzionare esattamente come prima quando mancano."""
        self.assertIsNone(self._sonda())
        ev = self._sonda(previous_last_entry=None)
        self.assertEqual(ev["type"], "new")

    def test_decollo_imminente_porta_la_controprova(self):
        """L'allarme di punta ora risponde alla domanda che un uomo di campo
        fa per prima: 'si', ma ha giocato davvero?'."""
        curva = {"phase": 3, "factors": {"a": {"active": True, "detail": "le menzioni accelerano"}}}
        validato = _score(_giocatore(17.0), _carriera([_club(apps=25)]))
        ev = self._sonda(curve=curva, validazione=validato)
        self.assertEqual(ev["type"], "takeoff")
        self.assertIn("non e' solo stampa", ev["lead"])

    def test_decollo_senza_riscontri_avverte(self):
        curva = {"phase": 3, "factors": {"a": {"active": True, "detail": "le menzioni accelerano"}}}
        vuoto = _score(_giocatore(17.0), _carriera([_club(apps=None)]))
        ev = self._sonda(curve=curva, validazione=vuoto)
        self.assertEqual(ev["type"], "takeoff")
        self.assertIn("SOLO la stampa", ev["lead"])

    def test_decollo_non_validabile_non_accusa(self):
        """Se non si e' potuto leggere nulla, l'allarme non deve insinuare
        niente: ne' a favore ne' contro."""
        curva = {"phase": 3, "factors": {"a": {"active": True, "detail": "le menzioni accelerano"}}}
        muto = _score(_giocatore(17.0), None)
        ev = self._sonda(curve=curva, validazione=muto)
        self.assertNotIn("SOLO la stampa", ev["lead"])
        self.assertNotIn("non e' solo stampa", ev["lead"])


# ======================================================================
class TestContraddittorio(unittest.TestCase):
    """Il dubbio smette di essere generico ('il buzz e' fragile', vero per
    tutti) e diventa specifico di QUESTO giocatore."""

    def _caveats(self, validazione, signal=80):
        return player_caveats({"signal_score": signal, "components": {"buzz": 0.8, "age_vs_level": 0.5},
                               "partial_data": False},
                              None, {"tier": "serie_c"}, CFG, validazione=validazione)

    def test_buzz_alto_senza_riscontri_e_una_obiezione_specifica(self):
        c = self._caveats(_score(_giocatore(18.0), _carriera([_club(apps=None)])), signal=80)
        self.assertTrue(any("nessun segnale costoso lo conferma" in x for x in c))

    def test_non_validabile_non_diventa_mai_un_accusa(self):
        """LA RIGA PIU' DELICATA DI TUTTO IL LAYER. 'Non ho potuto guardare'
        non deve mai leggersi come 'non vale'."""
        c = self._caveats(_score(_giocatore(18.0), None), signal=80)
        testo = " ".join(c)
        self.assertIn("ne' a favore ne' contro", testo)
        self.assertNotIn("profilo tipico del falso positivo", testo)

    def test_conferma_isolata_viene_dichiarata(self):
        c = self._caveats(_score(_giocatore(17.0), _carriera([_club(apps=25)])), signal=20)
        self.assertTrue(any("un solo soggetto" in x for x in c))

    def test_caveats_funziona_senza_validazione(self):
        """Retrocompatibilita': il parametro e' opzionale."""
        c = player_caveats({"signal_score": 50, "components": {"age_vs_level": 0.95},
                            "partial_data": False}, None, {"tier": "serie_c"}, CFG)
        self.assertIsInstance(c, list)


# ======================================================================
class TestCacheCarriera(unittest.TestCase):
    """La cache non e' un'ottimizzazione, e' parte del contratto: la
    validazione e' un LUSSO che non deve mai far fallire una scansione.
    Durante lo sviluppo WDQS era sotto outage dichiarato e rispondeva 429
    'aggressively rate-limiting to 1 req/min' - questi test bloccano il
    comportamento in quelle condizioni, che sono la norma, non l'eccezione."""

    def setUp(self):
        import discovery_engine
        self.eng = discovery_engine
        self.originale = discovery_engine._sparql_career_batch
        self.chiamate = []

    def tearDown(self):
        self.eng._sparql_career_batch = self.originale

    def _stub(self, risposta):
        def fake(qids, cfg):
            self.chiamate.append(list(qids))
            return None if risposta is None else {q: list(risposta) for q in qids}
        self.eng._sparql_career_batch = fake

    def test_cache_fresca_non_viene_riletta(self):
        self._stub([_club()])
        cache = {"Q1": {"memberships": [], "fonte": "wikidata",
                        "letto_il": OGGI.strftime("%Y-%m-%d"), "stato_lettura": "ok"}}
        self.eng.fetch_career_records([{"candidate_id": "Q1"}], CFG, cache)
        self.assertEqual(self.chiamate, [], "ha riletto un record ancora fresco")

    def test_cache_scaduta_viene_riletta(self):
        self._stub([_club()])
        vecchio = (OGGI - timedelta(days=VT["cache"]["validita_giorni"] + 1)).strftime("%Y-%m-%d")
        cache = {"Q1": {"memberships": [], "fonte": "wikidata",
                        "letto_il": vecchio, "stato_lettura": "ok"}}
        self.eng.fetch_career_records([{"candidate_id": "Q1"}], CFG, cache)
        self.assertEqual(len(self.chiamate), 1)

    def test_fonte_muta_non_scrive_in_cache(self):
        """Se WDQS tace non si sedimenta un buco: al giro dopo si riprova.
        Scrivere 'vuoto' significherebbe trasformare un problema di rete in
        un giudizio permanente sul giocatore."""
        self._stub(None)
        cache = {}
        self.eng.fetch_career_records([{"candidate_id": "Q1"}], CFG, cache)
        self.assertEqual(cache, {}, "un errore di rete e' finito in cache come dato")

    def test_tetto_query_per_run_rispettato(self):
        """Con una pool nell'ordine delle migliaia la validazione non deve
        mai allungare la scansione senza limite."""
        self._stub([])
        tetto = VT["cache"]["max_query_per_run"]
        per_query = VT["cache"]["max_qid_per_query"]
        candidati = [{"candidate_id": f"Q{i}"} for i in range(per_query * (tetto + 5))]
        self.eng.fetch_career_records(candidati, CFG, {})
        self.assertLessEqual(len(self.chiamate), tetto)

    def test_chi_non_entra_nel_tetto_tiene_il_record_vecchio(self):
        """Dato stantio ma ONESTO (con letto_il in chiaro) e' meglio di una
        decadenza a 'non validabile'."""
        self._stub([])
        vecchio = (OGGI - timedelta(days=99)).strftime("%Y-%m-%d")
        cache = {"Qzzz": {"memberships": [_club()], "fonte": "wikidata",
                          "letto_il": vecchio, "stato_lettura": "ok"}}
        per_query = VT["cache"]["max_qid_per_query"]
        tetto = VT["cache"]["max_query_per_run"]
        candidati = [{"candidate_id": f"Q{i}"} for i in range(per_query * (tetto + 2))]
        candidati.append({"candidate_id": "Qzzz"})
        self.eng.fetch_career_records(candidati, CFG, cache)
        self.assertIn("Qzzz", cache)
        self.assertEqual(cache["Qzzz"]["letto_il"], vecchio)

    def test_solo_i_qid_wikidata_vengono_interrogati(self):
        """I candidati senza QID stabile (es. da parsing Wikipedia) non hanno
        nulla da chiedere a Wikidata: chiederlo sprecherebbe il tetto."""
        self._stub([])
        self.eng.fetch_career_records(
            [{"candidate_id": "watchlist-mario-rossi"}, {"candidate_id": "Q7"}], CFG, {})
        self.assertEqual(self.chiamate, [["Q7"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
