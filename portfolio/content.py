# -*- coding: utf-8 -*-
"""
Fixed content for the Scouting & Match Analysis portfolio.

This is the single source of truth for the copy shown in the generated
PDF. Only the recipient on the cover page is parametrized (see
generate_portfolio.py) — everything in here is the same for every export.

Sourced from the live copy at matchanalysispro.online, mtornani.github.io
(ob1-scout, ob1-serie-c) and this repo's own README (Sentinel), so the
portfolio never says anything the public sites don't already say.

The SENTINEL evidence table is a dated, real snapshot pulled from the
live "IL TURNO" queue (ob1-radar Cloud Run app, guest-key access) — not
live data embedded in the PDF (a static file can't be live), just an
honest point-in-time capture. To refresh it: open
  https://ob1-radar-957169827556.europe-west1.run.app/turno?guest_key=<KEY>
note today's cases from GET /api/radar/turno, and update SENTINEL_SNAPSHOT_DATE
+ the "sentinel" system's evidence/stats below. The guest key itself is
never committed here.
"""

COVER = {
    "eyebrow": "> PORTFOLIO",
    "title": "Scouting & Match Analysis Systems",
    "author": "Mirko Tornani",
    "role": "UEFA B Coach · Football Data Developer",
    "location": "San Marino / Italy",
    "tagline": "I build systems that find talent before the market does.",
}

LOOP_STAGES = ["SCRAPE", "ANALYZE", "DETECT", "REPORT", "VALIDATE", "CALIBRATE"]

# Snapshot date for the live SENTINEL evidence below (IL TURNO queue).
SENTINEL_SNAPSHOT_DATE = "2026-08-11"
SENTINEL_CANDIDATES_TRACKED = "3,518"
SENTINEL_IN_REVIEW = "3"

SYSTEMS = [
    {
        "key": "ob1-global",
        "title": "OB1 GLOBAL RADAR",
        "subtitle": "Asymmetric talent intelligence",
        "badge": "OPERATIONAL",
        "description": (
            "Scans low-visibility sources every 6 hours and identifies players the "
            "market hasn't priced yet — before they become known names. Every "
            "candidate is cross-referenced against Transfermarkt (Ghost Protocol) "
            "to isolate who's still completely invisible to the structured market."
        ),
        "stats": [
            ("Candidates tracked", f"{SENTINEL_CANDIDATES_TRACKED} (live)"),
            ("Operating cost", "$0–5 / month"),
            ("Cycle", "6h, autonomous"),
        ],
        "evidence": [],
        "evidence_note": None,
        "screens": [],
        "link": "https://mtornani.github.io/ob1-scout/",
        "link_label": "mtornani.github.io/ob1-scout",
    },
    {
        "key": "ob1-serie-c",
        "title": "OB1 SERIE C SCOUT",
        "subtitle": "Italian lower-league radar",
        "badge": "OPERATIONAL",
        "description": (
            "Same pipeline as OB1 Global Radar, recalibrated for Italy's lower "
            "divisions. Targeted intelligence on Serie C and Serie D — anomalies "
            "where no institutional radar is looking."
        ),
        "stats": [
            ("Focus", "Serie C / Serie D"),
            ("Pipeline", "Asynchronous · GitHub Actions"),
            ("Cycle", "6h · ~$0 cost"),
        ],
        "evidence": [],
        "evidence_note": None,
        "screens": [],
        "link": "https://mtornani.github.io/ob1-serie-c/",
        "link_label": "mtornani.github.io/ob1-serie-c",
    },
    {
        "key": "sentinel",
        "title": "SENTINEL",
        "subtitle": "An attention prioritizer, not a prediction engine",
        "badge": "OPERATIONAL",
        "description": (
            "Mobile-only interface that measures WHEN attention on a player starts "
            "moving — from niche press to mainstream — and tries to flag it before "
            "it becomes news, in the window where it still costs little and "
            "competition is low. Deliberately readable backend: direct functions, "
            "explicit formulas, zero ML/training."
        ),
        "stats": [
            ("Candidates tracked", SENTINEL_CANDIDATES_TRACKED),
            ("In review today", SENTINEL_IN_REVIEW),
            ("Stack", "Python 3.12 · SQLite · Bayesian (1D Kalman)"),
        ],
        "screens": [
            ("THE QUEUE", "One case at a time: only what changed, or a window still open."),
            ("THE MAP", "Unknown-to-known adoption curve, hot zone highlighted."),
            ("THE DEVIL'S ADVOCATE", "The system cross-examined by its own numbers: precision, recall, honest objections."),
            ("ARCHIVE", "Every candidate filterable by profile, role, age, country."),
        ],
        # Real snapshot from the live "THE QUEUE" (IL TURNO) API — see module
        # docstring for how to refresh. verdict.vale_la_pena: True -> TRACKING,
        # False -> FLAGGED (the system calling a likely false positive on itself).
        "evidence": [
            ("Luke Vickery", "89.2", "TRACKING"),
            ("Paul Smajlaj", "88.9", "TRACKING"),
            ("Jhafets Reyes", "88.7", "FLAGGED"),
        ],
        "evidence_note": f"Live snapshot from THE QUEUE — {SENTINEL_SNAPSHOT_DATE}",
        "link": None,
        "link_label": None,
    },
    {
        "key": "match-analysis-pro",
        "title": "MATCH ANALYSIS PRO",
        "subtitle": "The hub — Ouroboros Protocol",
        "badge": "LIVE",
        "description": (
            "The layer that orchestrates everything else. Multiple AI agents debate "
            "every anomaly before it reaches a human: consensus gets challenged, "
            "noise gets filtered. What survives is signal. The method is public — "
            "the Ship of Theseus Protocol whitepaper explains the why, the "
            "Ouroboros Protocol the how."
        ),
        "stats": [
            ("Cycle", " → ".join(LOOP_STAGES) + " → LOOP"),
            ("Philosophy", "Radical transparency, not artificial scarcity"),
        ],
        "evidence": [],
        "evidence_note": None,
        "screens": [],
        "link": "https://matchanalysispro.online",
        "link_label": "matchanalysispro.online",
    },
]

CONTACT = {
    "email": "mirkotornani@gmail.com",
    "linkedin": "linkedin.com/in/mirkotornani",
    "linkedin_url": "https://www.linkedin.com/in/mirkotornani/",
    "note": "I don't do sales calls. Send me a problem, I'll tell you if I can solve it.",
}
