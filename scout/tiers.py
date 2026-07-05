"""
Classificazione TIER delle fonti media.

L'idea chiave del Radar: la diffusione dell'attenzione su un giocatore
si misura da CHI ne parla, non solo da QUANTO se ne parla.

  TIER 0 — locale/ultra-nicchia: siti di provincia, blog, fan media.
           Se un giocatore appare solo qui, e' in fase INNOVATOR.
  TIER 1 — specialisti/mercato: testate di settore e mercato
           (Tuttomercatoweb, Calciomercato, Scouted...). Fase EARLY ADOPTER:
           gli addetti ai lavori lo conoscono, il pubblico no.
  TIER 2 — mainstream nazionale: Gazzetta, Marca, L'Equipe, Kicker...
           Prima menzione tier 2 = il giocatore STA ATTRAVERSANDO la curva.
  TIER 3 — globale: BBC, Sky Sports, ESPN, Goal...
           Fase MAINSTREAM: la finestra e' chiusa, il prezzo lo sa il mondo.

L'ESCALATION di tier (0->1->2->3) e' il segnale piu' predittivo che
la finestra di vantaggio si sta chiudendo.
"""
from urllib.parse import urlparse

# Mappa dominio -> tier. Domini non elencati = tier 0 (locale/nicchia).
# Estendibile: aggiungi domini man mano che il radar li incontra.
TIER_3_GLOBAL = {
    "bbc.com", "bbc.co.uk", "skysports.com", "espn.com", "espn.co.uk",
    "theguardian.com", "goal.com", "90min.com", "onefootball.com",
    "theathletic.com", "nytimes.com", "cnn.com", "reuters.com",
    "fifa.com", "uefa.com", "eurosport.com", "eurosport.it",
    "foxsports.com", "beinsports.com", "givemesport.com",
    "sportbible.com", "fourfourtwo.com", "footballtransfers.com",
}

TIER_2_NATIONAL = {
    # Italia
    "gazzetta.it", "corrieredellosport.it", "tuttosport.com",
    "sport.sky.it", "sportmediaset.mediaset.it", "repubblica.it",
    "corriere.it", "rainews.it", "ansa.it",
    # Spagna
    "marca.com", "as.com", "sport.es", "mundodeportivo.com",
    # Francia
    "lequipe.fr", "footmercato.net", "rmcsport.bfmtv.com", "le10sport.com",
    # Germania
    "kicker.de", "bild.de", "sport1.de", "spox.com",
    # Portogallo
    "record.pt", "abola.pt", "ojogo.pt", "maisfutebol.iol.pt",
    # UK (nazionali non-globali)
    "dailymail.co.uk", "mirror.co.uk", "telegraph.co.uk",
    "independent.co.uk", "standard.co.uk", "thesun.co.uk",
    # Sud America
    "ole.com.ar", "ge.globo.com", "globoesporte.globo.com", "lance.com.br",
    "eltiempo.com", "marca.com.co", "depor.com",
    # Olanda / Belgio
    "ad.nl", "telegraaf.nl", "voetbalinternational.nl", "hln.be",
    # Turchia / altro
    "fanatik.com.tr", "sabah.com.tr", "hurriyet.com.tr",
}

TIER_1_SPECIALIST = {
    # Mercato / settore Italia
    "tuttomercatoweb.com", "calciomercato.com", "calciomercato.it",
    "transfermarkt.it", "transfermarkt.com", "transfermarkt.es",
    "transfermarkt.de", "transfermarkt.co.uk", "transfermarkt.us",
    "football-italia.net", "tuttoc.com", "seriebnews.com",
    "pianetaserieb.it", "tuttocalciatori.net", "alfredopedulla.com",
    "gianlucadimarzio.com",
    # Scouting / analytics internazionali
    "scoutedftbl.com", "breakingthelines.com", "totalfootballanalysis.com",
    "footballtalentscout.net", "wyscout.com", "fbref.com",
    "sofascore.com", "flashscore.com", "whoscored.com", "fotmob.com",
    # Youth / academy
    "vivoperlei.calciomercato.com", "ilovepalermocalcio.com",
}

# Query Google News restituisce host tipo "news.google.com" nel link;
# il vero publisher sta nel tag <source url="...">.


def domain_of(url: str) -> str:
    """Estrae il dominio registrabile (senza www) da un URL."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def classify(url: str) -> int:
    """Ritorna il tier (0-3) del dominio di un URL/publisher."""
    host = domain_of(url)
    if not host:
        return 0
    # match esatto o suffisso (sport.sky.it matcha sky.it se elencato)
    for candidates, tier in (
        (TIER_3_GLOBAL, 3),
        (TIER_2_NATIONAL, 2),
        (TIER_1_SPECIALIST, 1),
    ):
        for dom in candidates:
            if host == dom or host.endswith("." + dom):
                return tier
    return 0


TIER_LABELS = {
    0: "locale/nicchia",
    1: "specialisti mercato",
    2: "mainstream nazionale",
    3: "globale",
}
