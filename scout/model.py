"""
Modello di diffusione dell'attenzione (curva di Rogers applicata
al mercato calcistico).

Tre numeri per giocatore, tutti spiegabili e ricostruibili dai dati:

  ADI (Attention Diffusion Index, 0-100)
      DOVE si trova sulla curva. Cumulativo: tier delle fonti,
      presenza Wikipedia, spread linguistico, volume menzioni,
      pageviews. ADI basso + performance alta = occasione.

  BREAKOUT SCORE (0-100)
      QUANTO VELOCEMENTE sta attraversando la curva ADESSO.
      Derivate: accelerazione menzioni, escalation tier, spike
      pageviews, keyword rumor, nuove lingue. E' l'allarme.

  WINDOW (OPEN / CLOSING / CLOSED)
      La sintesi operativa per l'occhio umano:
        OPEN    -> early adopter stabile: visionare con calma
        CLOSING -> sta uscendo dalla fase: AGIRE ORA
        CLOSED  -> mainstream: la concorrenza sa gia' tutto

Ogni punteggio porta con sé i "reasons": la lista dei fattori
oggettivi che l'hanno generato. Niente black box — davanti a un DS
devi poter dire PERCHE' il radar suona.
"""
import math

# Soglie di fase sull'ADI (bande della curva di Rogers)
PHASE_BANDS = [
    (0, 15, "INNOVATOR", "Nessuno ne parla: solo fonti iper-locali"),
    (15, 40, "EARLY_ADOPTER", "Gli addetti ai lavori lo conoscono, il pubblico no"),
    (40, 65, "CROSSING", "Sta attraversando il chasm: mainstream in arrivo"),
    (65, 101, "MAINSTREAM", "Visibilita' piena: la finestra e' chiusa"),
]

BREAKOUT_ALERT_THRESHOLD = 45  # sopra questa soglia in fase EA/CROSSING -> alert


def _log_scale(value: float, cap: float) -> float:
    """Scala logaritmica 0-1: i primi segnali contano piu' degli ultimi."""
    if value <= 0:
        return 0.0
    return min(1.0, math.log1p(value) / math.log1p(cap))


def _totals(compact: dict) -> dict:
    """Aggrega lo snapshot compatto in totali cross-lingua."""
    news = compact.get("news", {})
    return {
        "m7": sum(d["m7"] for d in news.values()),
        "m30": sum(d["m30"] for d in news.values()),
        "max_tier": max((d["tier"] for d in news.values()), default=-1),
        "domains": sum(d["domains"] for d in news.values()),
        "rumors": sum(d["rumors"] for d in news.values()),
        "langs_active": sum(1 for d in news.values() if d["m30"] > 0),
        "langs_set": {lang for lang, d in news.items() if d["m30"] > 0},
    }


def compute_adi(compact: dict) -> tuple[float, list[str]]:
    """ADI 0-100: posizione cumulativa sulla curva di diffusione."""
    t = _totals(compact)
    reasons = []
    score = 0.0

    # 1. Tier massimo delle fonti (max 30 punti) — CHI ne parla
    tier_pts = {-1: 0, 0: 4, 1: 12, 2: 22, 3: 30}[t["max_tier"]]
    score += tier_pts
    if t["max_tier"] >= 2:
        reasons.append(f"fonti tier {t['max_tier']} (mainstream) ne parlano")
    elif t["max_tier"] == 1:
        reasons.append("coperto dagli specialisti di mercato (tier 1)")
    elif t["max_tier"] == 0:
        reasons.append("solo fonti locali/nicchia (tier 0)")
    else:
        reasons.append("nessuna menzione news negli ultimi 30 giorni")

    # 2. Presenza Wikipedia (max 25 punti) — il pubblico lo cerca?
    wiki_langs = compact.get("wiki_langs", 0)
    if wiki_langs > 0:
        wiki_pts = 10 + 15 * _log_scale(wiki_langs, 30)
        lingua = "lingua" if wiki_langs == 1 else "lingue"
        reasons.append(f"pagina Wikipedia in {wiki_langs} {lingua}")
    else:
        wiki_pts = 0
        reasons.append("nessuna pagina Wikipedia (invisibile al pubblico)")
    score += wiki_pts

    # 3. Volume menzioni 30gg (max 20 punti)
    score += 20 * _log_scale(t["m30"], 120)

    # 4. Spread linguistico (max 15 punti) — diffusione internazionale
    lang_pts = {0: 0, 1: 3, 2: 7, 3: 10, 4: 12, 5: 14, 6: 15}.get(
        t["langs_active"], 15
    )
    score += lang_pts
    if t["langs_active"] >= 3:
        reasons.append(f"menzionato in {t['langs_active']} lingue diverse")

    # 5. Pageviews Wikipedia (max 10 punti)
    pv = compact.get("pv_avg30")
    if pv:
        score += 10 * _log_scale(pv, 3000)
        if pv > 100:
            reasons.append(f"~{int(pv)} visite/giorno alla pagina Wikipedia")

    return min(100.0, round(score, 1)), reasons


def compute_breakout(history: list[dict]) -> tuple[float, list[str]]:
    """
    Breakout Score 0-100: velocita' di attraversamento della curva ADESSO.
    Usa lo storico per le derivate; con un solo snapshot usa solo i
    segnali istantanei (rumor, spike) e lo dichiara.
    """
    if not history:
        return 0.0, ["nessun dato storico"]

    now = history[-1]
    t_now = _totals(now)
    reasons = []
    score = 0.0

    # Snapshot precedente ad almeno 5 giorni di distanza (derivate stabili)
    prev = None
    for row in reversed(history[:-1]):
        if _days_between(row["date"], now["date"]) >= 5:
            prev = row
            break
    if prev is None and len(history) >= 2:
        prev = history[-2]

    # 1. Accelerazione menzioni (max 25) — seconda derivata dell'attenzione
    if prev is not None:
        t_prev = _totals(prev)
        delta = t_now["m7"] - t_prev["m7"]
        if delta > 0 and t_prev["m7"] > 0:
            growth = delta / max(t_prev["m7"], 1)
            pts = min(25, 25 * min(growth, 2.0) / 2.0)
            score += pts
            reasons.append(
                f"menzioni/settimana da {t_prev['m7']} a {t_now['m7']} "
                f"(+{int(growth * 100)}%)"
            )
        elif delta > 0:
            score += min(25, delta * 5)
            reasons.append(f"prime menzioni della settimana: {t_now['m7']}")
    else:
        reasons.append("(un solo snapshot: derivate non ancora calcolabili)")

    # 2. Escalation tier (max 25) — fonte di livello mai visto prima.
    # Richiede storico: al primo snapshot non esiste un "prima".
    max_tier_before = max(
        (_totals(r)["max_tier"] for r in history[:-1]), default=-1
    )
    if history[:-1] and t_now["max_tier"] > max_tier_before and t_now["max_tier"] >= 1:
        pts = {1: 12, 2: 25, 3: 25}[t_now["max_tier"]]
        score += pts
        reasons.append(
            f"ESCALATION: prima menzione tier {t_now['max_tier']} "
            "(fonte di livello mai raggiunto prima)"
        )

    # 3. Spike pageviews (max 20) — il pubblico ha iniziato a cercarlo
    pv7, pv30 = now.get("pv_avg7"), now.get("pv_avg30")
    if pv7 and pv30 and pv30 > 0 and pv7 >= 10:
        ratio = pv7 / pv30
        if ratio >= 1.5:
            score += min(20, 20 * min(ratio - 1, 2.0) / 2.0)
            reasons.append(
                f"spike pageviews Wikipedia: media 7gg {ratio:.1f}x la media 30gg"
            )

    # 4. Keyword rumor mercato (max 15)
    if t_now["rumors"] > 0:
        score += min(15, 5 + t_now["rumors"] * 2)
        titolo = "titolo" if t_now["rumors"] == 1 else "titoli"
        reasons.append(
            f"{t_now['rumors']} {titolo} con keyword di mercato "
            "(interesse/osservatori/transfer...)"
        )

    # 5. Nuova lingua (max 15) — diffusione internazionale in corso
    langs_before = set()
    for r in history[:-1]:
        langs_before |= _totals(r)["langs_set"]
    new_langs = t_now["langs_set"] - langs_before
    if langs_before and new_langs:
        score += min(15, len(new_langs) * 8)
        reasons.append(f"nuove lingue: {', '.join(sorted(new_langs))}")

    # 6. Evento Wikipedia (bonus 20, sopra il cap parziale) — pagina creata
    wiki_before = any(r.get("wiki_langs", 0) > 0 for r in history[:-1])
    if history[:-1] and not wiki_before and now.get("wiki_langs", 0) > 0:
        score += 20
        reasons.append("EVENTO: pagina Wikipedia appena creata")

    return min(100.0, round(score, 1)), reasons


def classify_phase(adi: float) -> tuple[str, str]:
    for lo, hi, label, desc in PHASE_BANDS:
        if lo <= adi < hi:
            return label, desc
    return "MAINSTREAM", PHASE_BANDS[-1][3]


def window_status(adi: float, breakout: float) -> tuple[str, str]:
    """La sintesi operativa: cosa deve fare l'occhio umano."""
    phase, _ = classify_phase(adi)
    if phase == "MAINSTREAM":
        return "CLOSED", "Gia' mainstream: la concorrenza ha le stesse informazioni"
    if phase == "CROSSING" or breakout >= BREAKOUT_ALERT_THRESHOLD:
        return "CLOSING", (
            "Sta uscendo dalla fase early adopter: visionare/agire ORA, "
            "ogni settimana di attesa aumenta concorrenza e prezzo"
        )
    if phase == "EARLY_ADOPTER":
        return "OPEN", "Early adopter stabile: finestra aperta, visionare con calma"
    return "OPEN", "Fase innovator: monitorare, segnali di attenzione assenti"


def estimate_weeks_to_mainstream(history: list[dict]) -> int | None:
    """
    Estrapolazione lineare del trend ADI: a questa velocita' di crescita,
    tra quante settimane l'ADI supera 65 (mainstream)?
    Serve >= 3 snapshot su >= 10 giorni. None = non stimabile.
    """
    if len(history) < 3:
        return None
    points = []
    for row in history:
        adi, _ = compute_adi(row)
        points.append((_date_ordinal(row["date"]), adi))
    span_days = points[-1][0] - points[0][0]
    if span_days < 10:
        return None
    # regressione lineare semplice
    n = len(points)
    mean_x = sum(p[0] for p in points) / n
    mean_y = sum(p[1] for p in points) / n
    denom = sum((p[0] - mean_x) ** 2 for p in points)
    if denom == 0:
        return None
    slope = sum((p[0] - mean_x) * (p[1] - mean_y) for p in points) / denom
    current = points[-1][1]
    if slope <= 0.01 or current >= 65:
        return None
    days = (65 - current) / slope
    if days > 365:
        return None
    return max(1, round(days / 7))


def score_player(player: dict, history: list[dict]) -> dict:
    """Combina tutto in una scheda radar per il giocatore."""
    if not history:
        return {"error": "no_history"}
    now = history[-1]
    adi, adi_reasons = compute_adi(now)
    breakout, breakout_reasons = compute_breakout(history)
    phase, phase_desc = classify_phase(adi)
    window, window_desc = window_status(adi, breakout)
    weeks = estimate_weeks_to_mainstream(history)
    return {
        "player": player["name"],
        "club": player.get("club", ""),
        "born": player.get("born", ""),
        "position": player.get("position", ""),
        "date": now["date"],
        "adi": adi,
        "adi_reasons": adi_reasons,
        "breakout": breakout,
        "breakout_reasons": breakout_reasons,
        "phase": phase,
        "phase_desc": phase_desc,
        "window": window,
        "window_desc": window_desc,
        "weeks_to_mainstream": weeks,
        "snapshots": len(history),
    }


def _date_ordinal(date_str: str) -> int:
    from datetime import date

    y, m, d = date_str.split("-")
    return date(int(y), int(m), int(d)).toordinal()


def _days_between(d1: str, d2: str) -> int:
    return abs(_date_ordinal(d2) - _date_ordinal(d1))
