#!/usr/bin/env python3
"""ESTRATTO DEL GIORNO — costruirsi i "true fan" (Kevin Kelly) un post al
giorno, con lo stesso materiale che il motore produce comunque ogni mattina.

Il problema che risolve non è "cosa scrivo oggi" — è la frizione. Se ogni
sera bisogna aprire il codice e pensare a un post, lo streak muore alla
prima serata storta (lo stesso principio per cui deploy.sh è un comando
solo). Questo script legge la run vera del giorno dal servizio in
produzione e stampa tre bozze pronte da incollare — zero scrittura
creativa richiesta per tenere vivo lo streak.

Uso:
    export RADAR_GUEST_KEY=...       # sola lettura, la stessa di deploy.sh
    python3 estratto_del_giorno.py              # mostra 3 bozze + streak
    python3 estratto_del_giorno.py --registra   # bozze + segna oggi pubblicato

REGOLA DI SICUREZZA, non negoziabile: uno di questi post può nominare un
giocatore reale SOLO se l'età alla data odierna è calcolabile dalla data di
nascita ED è >= 18 anni. Niente euristiche sul livello del campionato, niente
"probabilmente è adulto" - la stessa regola con cui il resto del motore non
inventa mai un dato mancante (vedi discovery_engine, "un'assenza di dato non
e' mai un voto"). Se l'età non si può calcolare, quel candidato è escluso dal
tutto, non declassato a "forse va bene".
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
STREAK_FILE = BASE_DIR / "streak_estratti.json"
DEFAULT_URL = "https://ob1-radar-957169827556.europe-west1.run.app"
ETA_MINIMA_PUBBLICABILE = 18.0
LIMITE_CARATTERI = 280  # X classico - un post che sfora si nota subito, non a bozza scelta


# ============================================================
# LETTURA DAL SERVIZIO (unica parte con I/O di rete)
# ============================================================

def _fetch(url: str, path: str, guest_key: str | None) -> dict:
    q = f"?guest_key={urllib.parse.quote(guest_key)}" if guest_key else ""
    with urllib.request.urlopen(f"{url}{path}{q}", timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def leggi_run_di_oggi(url: str, guest_key: str | None) -> dict:
    """Un solo punto di contatto col servizio vero - tutto il resto del
    file lavora su questo dict, quindi tutto il resto e' testabile senza
    rete (vedi tests/test_estratto_del_giorno.py)."""
    turno = _fetch(url, "/api/radar/turno", guest_key)
    processo = _fetch(url, "/api/radar/processo", guest_key)
    if turno.get("status") != "success" or processo.get("status") != "success":
        raise RuntimeError(
            f"il servizio non ha risposto come atteso: "
            f"turno={turno.get('message')} processo={processo.get('message')}"
        )
    return {"turno": turno, "processo": processo}


# ============================================================
# FUNZIONI PURE - eta', bozze, streak. Nessuna qui tocca la rete o il
# filesystem: prendono dict, restituiscono dict/stringhe. Testabili offline.
# ============================================================

def eta_anni(dob_iso: str | None, oggi: datetime | None = None) -> float | None:
    """None se il dato manca o non si legge - mai una eta' indovinata."""
    if not dob_iso:
        return None
    try:
        nascita = datetime.fromisoformat(dob_iso[:10])
    except ValueError:
        return None
    oggi = oggi or datetime.now(timezone.utc)
    riferimento = datetime(oggi.year, oggi.month, oggi.day)
    return (riferimento - nascita).days / 365.25


def _tronca(testo: str, limite: int = LIMITE_CARATTERI) -> str:
    if len(testo) <= limite:
        return testo
    return testo[: limite - 1].rstrip() + "…"


def bozza_numero_onesto(processo: dict) -> dict | None:
    """Categoria A: un numero vero da /processo, mai un numero inventato.
    Preferisce il tasso di apertura (e' il piu' forte: misura te, non il
    sistema) e cade sulla copertura di validazione se non c'e' abbastanza
    storico di decisioni."""
    prec = processo.get("precisione_turno") or {}
    tot = prec.get("decisioni_totali") or 0
    tasso = prec.get("tasso_apertura_complessivo")
    if tot > 0 and tasso is not None:
        testo = (
            f"Il turno mi fa aprire una scheda vera {tasso:g}% delle volte "
            f"— misurato su {tot} decisioni mie, non promesso in un pitch. "
            f"#buildinpublic"
        )
        return {"categoria": "numero", "testo": _tronca(testo)}

    cop = processo.get("validazione_copertura") or {}
    considerati = cop.get("considerati")
    pct = cop.get("copertura_pct")
    if considerati and pct is not None:
        testo = (
            f"Su {considerati} candidati nel radar, il segnale costoso "
            f"(minuti veri, una convocazione) e' leggibile solo per il "
            f"{pct:g}%. Il resto non e' \"zero\" — e' \"non verificabile\", "
            f"e lo dichiariamo invece di far finta di saperlo."
        )
        return {"categoria": "numero", "testo": _tronca(testo)}
    return None


def bozza_limite_onesto(processo: dict, turno: dict) -> dict | None:
    """Categoria C: un limite o una correzione dichiarata OGGI - il
    materiale piu' forte per un true fan, perche' non e' promozione."""
    scaduti = turno.get("scaduti_count") or 0
    if scaduti > 0:
        soglia = turno.get("scadenza_scansioni")
        soggetto = "1 caso e'" if scaduti == 1 else f"{scaduti} casi sono"
        uscito = "uscito" if scaduti == 1 else "usciti"
        pronome = "lo" if scaduti == 1 else "li"
        testo = (
            f"Oggi {soggetto} {uscito} dalla mia lista giornaliera: "
            f"le ultime {soglia} scansioni non {pronome} toccavano piu'. "
            f"Non spariscono in silenzio — li conto e lo dico."
        )
        return {"categoria": "limite", "testo": _tronca(testo)}

    esplosi = processo.get("esplosi")
    sgonfiati = processo.get("sgonfiati")
    if esplosi is not None and sgonfiati:
        chiuse = (esplosi or 0) + sgonfiati
        testo = (
            f"{esplosi} scommesse esplose su {chiuse} chiuse finora. "
            f"Ve lo dico perche' il giorno che smettessi di dirvelo, "
            f"dovreste smettere di fidarvi di tutto il resto."
        )
        return {"categoria": "limite", "testo": _tronca(testo)}
    return None


def bozza_caso_reale(turno: dict, oggi: datetime | None = None) -> dict | None:
    """Categoria D: un caso vero di oggi, MAI un minorenne e MAI un'eta'
    indovinata (vedi eta_anni). Se oggi non c'e' nessun caso pubblicabile,
    None - dichiarato in main(), non sostituito con una scelta a caso."""
    for caso in turno.get("cases") or []:
        eta = eta_anni(caso.get("dob"), oggi)
        if eta is None or eta < ETA_MINIMA_PUBBLICABILE:
            continue
        nome = caso.get("name")
        club = caso.get("club")
        lead = ((caso.get("change") or {}).get("lead") or "").strip()
        if not nome or not lead:
            continue
        pezzo_club = f" ({club})" if club else ""
        testo = f"Nel turno di oggi{pezzo_club}: {nome}. {lead}"
        return {"categoria": "caso", "testo": _tronca(testo), "candidate_id": caso.get("candidate_id")}
    return None


def costruisci_bozze(run: dict, oggi: datetime | None = None) -> list[dict]:
    """Fino a 3 bozze, ognuna da una categoria diversa quando possibile.
    Un giorno povero di materiale ne restituisce meno di 3 - mai bozze
    duplicate o inventate solo per arrivare a tre."""
    turno, processo = run["turno"], run["processo"]
    candidate = [
        bozza_numero_onesto(processo),
        bozza_limite_onesto(processo, turno),
        bozza_caso_reale(turno, oggi),
    ]
    return [b for b in candidate if b]


# ============================================================
# STREAK - locale, onesta: un buco si vede, non si finge continuita'.
# Stesso principio del turno che non nasconde un caso scaduto.
# ============================================================

def _carica_streak(percorso: Path = STREAK_FILE) -> list[str]:
    if not percorso.exists():
        return []
    try:
        dati = json.loads(percorso.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return sorted(set(dati.get("pubblicazioni") or []))


def _salva_streak(date_iso: list[str], percorso: Path = STREAK_FILE) -> None:
    percorso.write_text(
        json.dumps({"pubblicazioni": sorted(set(date_iso))}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def registra_pubblicazione(oggi_iso: str, percorso: Path = STREAK_FILE) -> list[str]:
    date_iso = _carica_streak(percorso)
    if oggi_iso not in date_iso:
        date_iso.append(oggi_iso)
    _salva_streak(date_iso, percorso)
    return sorted(set(date_iso))


def stato_streak(date_iso: list[str], oggi: datetime | None = None) -> dict:
    """Streak consecutivo che finisce OGGI o IERI (non punisce chi non ha
    ancora pubblicato quello di oggi), piu' il totale onesto e l'ultimo
    buco - mai un numero che finge continuita' che non c'e'."""
    oggi = (oggi or datetime.now(timezone.utc)).date()
    giorni = sorted({datetime.fromisoformat(d).date() for d in date_iso if d}, reverse=True)
    if not giorni:
        return {"consecutivi": 0, "totale": 0, "ultimo_buco": None}

    ancora_attivo = giorni[0] in (oggi, oggi - timedelta(days=1))
    consecutivi = 0
    if ancora_attivo:
        consecutivi = 1
        for a, b in zip(giorni, giorni[1:]):
            if (a - b).days == 1:
                consecutivi += 1
            else:
                break

    ultimo_buco = None
    for a, b in zip(giorni, giorni[1:]):
        scarto = (a - b).days
        if scarto > 1:
            ultimo_buco = {"dopo": b.isoformat(), "prima": a.isoformat(), "giorni_saltati": scarto - 1}
            break

    return {"consecutivi": consecutivi, "totale": len(giorni), "ultimo_buco": ultimo_buco}


# ============================================================
# CLI
# ============================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default=os.environ.get("RADAR_URL", DEFAULT_URL))
    ap.add_argument("--guest-key", default=os.environ.get("RADAR_GUEST_KEY"))
    ap.add_argument("--registra", action="store_true", help="segna la pubblicazione di oggi nello streak locale")
    args = ap.parse_args()

    oggi = datetime.now(timezone.utc)
    oggi_iso = oggi.date().isoformat()

    print(f"── estratto del giorno — {oggi_iso}")
    try:
        run = leggi_run_di_oggi(args.url, args.guest_key)
    except (RuntimeError, OSError) as e:
        print(f"\nNon riesco a leggere la run di oggi: {e}", file=sys.stderr)
        print("Il turno funziona lo stesso — riprova, o pubblica a mano oggi.", file=sys.stderr)
        return 1

    bozze = costruisci_bozze(run, oggi)
    if not bozze:
        print("\nNessuna bozza pubblicabile oggi (niente numeri nuovi, niente casi con età verificabile).")
        print("Non è un errore: capita. Non c'è materiale onesto oggi, quindi non ne inventiamo.")
    else:
        print(f"\n{len(bozze)} bozze pronte — copia e incolla, zero editing richiesto:\n")
        for i, b in enumerate(bozze, 1):
            print(f"[{i}] ({b['categoria']}, {len(b['testo'])} caratteri)")
            print(f"    {b['testo']}\n")

    date_iso = _carica_streak()
    if args.registra:
        date_iso = registra_pubblicazione(oggi_iso)
        print(f"── registrato: hai pubblicato oggi ({oggi_iso}).")
    stato = stato_streak(date_iso, oggi)

    print(f"── streak: {stato['consecutivi']} giorni consecutivi · {stato['totale']} pubblicazioni totali")
    if stato["ultimo_buco"]:
        b = stato["ultimo_buco"]
        print(f"   ultimo buco: {b['giorni_saltati']} giorno/i saltati fra {b['prima']} e {b['dopo']} — dichiarato, non nascosto.")
    if not args.registra:
        print("   (rilancia con --registra dopo aver incollato il post, per far salire lo streak)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
