# -*- coding: utf-8 -*-
"""
Fixed content for the Scouting & Match Analysis portfolio.

This is the single source of truth for the copy shown in the generated
PDF. Only the recipient on the cover page is parametrized (see
generate_portfolio.py) — everything in here is the same for every export.

Sourced from the live copy at matchanalysispro.online, mtornani.github.io
(ob1-scout, ob1-serie-c) and this repo's own README (Sentinel), so the
portfolio never says anything the public sites don't already say.
"""

COVER = {
    "eyebrow": "> PORTFOLIO",
    "title": "Scouting & Match Analysis Systems",
    "author": "Mirko Tornani",
    "role": "UEFA B Coach · Football Data Developer",
    "location": "San Marino / Italy",
    "tagline": "Costruisco sistemi che trovano talento prima del mercato.",
}

LOOP_STAGES = ["SCRAPE", "ANALYZE", "DETECT", "REPORT", "VALIDATE", "CALIBRATE"]

SYSTEMS = [
    {
        "key": "ob1-global",
        "title": "OB1 GLOBAL RADAR",
        "subtitle": "Asymmetric talent intelligence",
        "badge": "OPERATIONAL",
        "description": (
            "Scansiona fonti a bassa visibilità ogni 6 ore e identifica giocatori "
            "che il mercato non ha ancora prezzato — prima che diventino nomi noti. "
            "Ogni candidato è cross-referenziato con Transfermarkt (Ghost Protocol) "
            "per isolare chi è ancora totalmente invisibile al mercato strutturato."
        ),
        "stats": [
            ("Copertura", "100+ giocatori monitorati"),
            ("Costo operativo", "$0–5 / mese"),
            ("Ciclo", "6h, autonomo"),
        ],
        "evidence": [
            ("Ryan Evaristo", "100", "GHOST"),
            ("Andre Maia", "95", "TRACKING"),
            ("Saviolo", "82", "TRACKING"),
        ],
        "link": "https://mtornani.github.io/ob1-scout/",
        "link_label": "mtornani.github.io/ob1-scout",
    },
    {
        "key": "ob1-serie-c",
        "title": "OB1 SERIE C SCOUT",
        "subtitle": "Radar Lega Pro",
        "badge": "OPERATIONAL",
        "description": (
            "Stessa pipeline di OB1 Global Radar, ricalibrata sulle divisioni "
            "inferiori italiane. Intelligence mirata su Serie C e Serie D — "
            "anomalie dove nessun radar istituzionale sta guardando."
        ),
        "stats": [
            ("Focus", "Serie C / Serie D"),
            ("Pipeline", "Asincrona · GitHub Actions"),
            ("Ciclo", "6h · costo ~$0"),
        ],
        "evidence": [],
        "link": "https://mtornani.github.io/ob1-serie-c/",
        "link_label": "mtornani.github.io/ob1-serie-c",
    },
    {
        "key": "sentinel",
        "title": "SENTINEL",
        "subtitle": "Un prioritizzatore di attenzione, non un motore di previsione",
        "badge": "OPERATIONAL",
        "description": (
            "Interfaccia solo-mobile che misura QUANDO l'attenzione su un giocatore "
            "inizia a muoversi — dalla stampa di nicchia al mainstream — e prova a "
            "segnalarlo prima che diventi notizia, nella finestra in cui costa ancora "
            "poco e la concorrenza è bassa. Backend deliberatamente leggibile: "
            "funzioni dirette, formule esplicite, zero ML/training."
        ),
        "screens": [
            ("IL TURNO", "Un caso alla volta: solo ciò che è cambiato o ha una finestra ancora aperta."),
            ("LA MAPPA", "Curva da sconosciuto a conosciuto, zona calda in evidenza."),
            ("L'AVVOCATO DEL DIAVOLO", "Il sistema sotto processo dai suoi stessi numeri: precisione, richiamo, obiezioni oneste."),
            ("ARCHIVIO", "Tutti i candidati filtrabili per profilo, ruolo, età, paese."),
        ],
        "stats": [
            ("Stack", "Python 3.12 · SQLite"),
            ("Stima", "Filtro bayesiano (Kalman 1D)"),
            ("Deploy", "GitHub Actions · PWA"),
        ],
        "evidence": [],
        "link": None,
        "link_label": None,
    },
    {
        "key": "match-analysis-pro",
        "title": "MATCH ANALYSIS PRO",
        "subtitle": "L'hub — Ouroboros Protocol",
        "badge": "LIVE",
        "description": (
            "Il layer che orchestra tutto il resto. Più agenti AI dibattono su ogni "
            "anomalia prima che arrivi a un umano: il consenso viene sfidato, il "
            "rumore filtrato. Quello che sopravvive è segnale. Il metodo è "
            "pubblico — il whitepaper Ship of Theseus Protocol spiega il perché, "
            "l'Ouroboros Protocol il come."
        ),
        "stats": [
            ("Ciclo", " → ".join(LOOP_STAGES) + " → LOOP"),
            ("Filosofia", "Trasparenza radicale, non scarsità artificiale"),
        ],
        "evidence": [],
        "link": "https://matchanalysispro.online",
        "link_label": "matchanalysispro.online",
    },
]

CONTACT = {
    "email": "mirkotornani@gmail.com",
    "linkedin": "linkedin.com/in/mirkotornani",
    "linkedin_url": "https://www.linkedin.com/in/mirkotornani/",
    "note": "Non faccio chiamate commerciali. Mandami un problema, ti dico se posso risolverlo.",
}
