# Traduzioni IT/EN dello "chrome" statico (titoli, bottoni, paragrafi fissi
# nei template). NON copre i testi generati a runtime da discovery_engine.py
# (caveat, spiegazioni "CLUB DA CORREGGERE", fattori della curva) ne' i
# verdetti dello swarm AI: quelli sono logica di dominio scritta in italiano
# e i verdetti escono da modelli istruiti in italiano (vedi _ROLES) - una
# traduzione onesta di quella parte richiederebbe rigenerare i prompt e
# ririlanciare lo swarm nella lingua del visitatore (raddoppia le chiamate
# AI per scansione, quindi le quote gratuite consumate). Per ora, in
# modalita' EN, quel testo resta in italiano con una nota che lo dice
# chiaramente - mai un finto "tradotto" su contenuto che non lo e'.
#
# Chiave piatta "pagina.elemento" per restare leggibile a colpo d'occhio.
# Se una chiave manca in una lingua, TRANSLATIONS ripiega sull'italiano
# (vedi t() in visual_council_app.py) - mai una pagina con un buco vuoto.

TRANSLATIONS = {
    "it": {
        "nav.home": "torna alla home",
        "nav.map": "la mappa",
        "nav.process": "l'avvocato del diavolo",
        "nav.archive": "vai all'archivio completo",
        "nav.turno_home": "torna al turno",
        "dynamic_content_note": "Nota: i verdetti AI e le spiegazioni generate dal sistema restano in italiano (il motore ragiona in italiano) - il resto dell'interfaccia è in inglese.",
    },
    "en": {
        "nav.home": "back to home",
        "nav.map": "the map",
        "nav.process": "the devil's advocate",
        "nav.archive": "go to the full archive",
        "nav.turno_home": "back to the shift",
        "dynamic_content_note": "Note: AI verdicts and system-generated explanations stay in Italian (the engine reasons in Italian) - the rest of the interface is in English.",

        # ---------- IL TURNO ----------
        "turno.eyebrow_prefix": "SHIFT OF",
        "turno.intake_title": "There's no list to scroll. There's a shift to do.",
        "turno.intake_sub_html": "Here you'll find who has news or a <strong>window still open</strong> (a \"about to break out\" stays until it actually closes). When a window closes — reached the big papers, or cooled off — it's shown to you once, explained: <strong>nothing disappears in silence</strong>. The rest is in the archive, quiet, until it moves.",
        "turno.stat_cases": "CASES TO REVIEW",
        "turno.stat_minutes": "MIN. READ",
        "turno.stat_archived": "ARCHIVED, QUIET",
        "turno.btn_start": "START THE SHIFT",
        "turno.btn_scan": "CHECK FOR UPDATES FIRST",
        "turno.btn_scan_running": "SCAN IN PROGRESS...",
        "turno.link_map": "the map — where every player stands on the path",
        "turno.link_process": "the devil's advocate — the scoreboard and the objections",
        "turno.link_archive": "see the full archive anyway",
        "turno.case_of": "CASE",
        "turno.case_of_sep": "OF",
        "turno.min_remaining": "min left",
        "turno.btn_flag": "FLAG",
        "turno.btn_flagged": "FLAGGED",
        "turno.btn_next": "NEXT",
        "turno.verdict_head": "swarm verdict",
        "turno.verdict_worth_it": "WORTH FOLLOWING",
        "turno.verdict_doubtful": "DOUBTFUL",
        "turno.verdict_pending": "VERDICT PENDING",
        "turno.no_motivation": "no motivation available",
        "turno.contra_head": "the counter-argument — what plays against this",
        "turno.contra_sub": "before you trust it, here's what plays against this signal",
        "turno.club_confirm_btn": "✓ CONFIRM: NOW PLAYING FOR «{club}»",
        "turno.club_confirm_done": "✓ RECORDED",
        "turno.club_confirm_retry": "✓ RETRY THE CONFIRMATION",
        "turno.club_confirm_note": "from now on the system uses this club (news search included), whatever the archive says.",
        "turno.club_confirm_note_registering": "recording...",
        "turno.end_title_prefix": "Shift over.",
        "turno.end_stat_reviewed": "CASES REVIEWED",
        "turno.end_stat_flagged": "FLAGGED FOR FOLLOW-UP",
        "turno.btn_restart": "↺ BACK TO HOME",
        "turno.install_btn": "＋ INSTALL THE APP",
        "turno.install_ios_hint": "on iPhone: Share → Add to Home Screen",
        "turno.status_scanning": "scan in progress... ({s}s)",
        "turno.status_scanning_retry": "scan running on the server... (retrying the connection)",
        "turno.status_connection_lost": "connection lost, but the scan keeps running on the server: reopen in a minute.",
        "turno.status_unstable": "unstable connection, checking status...",
        "turno.status_done": "scan complete.",
        "turno.status_error_prefix": "error:",
        "turno.status_slow": "slow connection, pull down to refresh.",
        "turno.curve_missing": "chart not tracked yet: this player enters the press-monitoring round from the next shift, and their position on the path to the spotlight will draw itself in.",
        "turno.curve_building": "chart building: {seen} of 3 press checks — {left} more and the position on the path appears here.",

        # ---------- LA MAPPA ----------
        "mappa.eyebrow": "THE MAP",
        "mappa.title": "Where every player stands on the path.",
        "mappa.sub": "Every dot is a player. The further right, the more the world knows them. Your edge is to the left of the hot zone — whoever's there still costs little to watch, and is about to break out.",
        "mappa.hot_zone_label": "ABOUT TO BREAK OUT",
        "mappa.hot_zone_arrow": "← the hot zone",
        "mappa.axis_left": "unknown",
        "mappa.axis_right": "everyone knows them",
        "mappa.stat_on_path": "players on the path",
        "mappa.stat_pending": "still to profile (below the minimum scans)",
        "mappa.ledger_empty": "The verification ledger is still empty: it fills up when a player really crosses over to the big papers.",
        "mappa.now_heading": "WHO'S ABOUT TO BREAK OUT NOW",
        "mappa.none_hot": "No one in the hot zone right now. That's normal: it's the rarest, most valuable band. Keep scanning — as soon as the signals converge on someone, they'll show up here first.",
        "mappa.stages_heading": "THE SIX STAGES OF THE PATH",
        "mappa.stages_hint": "tap a stage to see every player inside it",
        "mappa.sheet_stage_prefix": "STAGE",
        "mappa.sheet_players_suffix": "PLAYERS",
        "mappa.signal_label": "signal",

        # ---------- L'AVVOCATO DEL DIAVOLO ----------
        "processo.eyebrow": "THE DEVIL'S ADVOCATE",
        "processo.title": "The system, put on trial by its own numbers.",
        "processo.sub_html": "Anyone who sees SENTINEL will try to take it apart — that's fair. A system that defends itself with words is marketing. This one defends itself with <strong>the scoreboard</strong>: every time it says \"about to break out\" it opens a verifiable bet, and closes it with the real outcome, <strong>failures included</strong>. Below, the hardest objections and the honest answer to each — including the ones where the answer is \"you're right\".",
        "processo.scoreboard_heading": "THE SCOREBOARD — PROOF ON THE FACTS",
        "processo.precision_label": "PRECISION — of the players flagged \"about to break out\"",
        "processo.precision_sub": "broke out out of resolved bets",
        "processo.recall_label": "RECALL — of the players who really broke out",
        "processo.recall_sub_none": "no one has broken out yet",
        "processo.stat_exploded": "broke out (crossed over)",
        "processo.stat_deflated": "deflated (fell back)",
        "processo.stat_pending": "pending (window still open)",
        "processo.stat_total": "total flagged",
        "processo.stat_flagged_before": "flagged by the radar first",
        "processo.stat_reached_big": "reached the major papers",
        "processo.scoreboard_empty": "The scoreboard is <strong>empty</strong>: no \"about to break out\" call has been logged yet. It fills up on its own by scanning over time. Better an empty, honest scoreboard than a made-up percentage.",
        "processo.scoreboard_early": "Careful: only <strong>{n}</strong> resolved bet{plural} so far. Too few for a verdict — read any percentage here as provisional, not as proof. The number becomes serious in the tens, not the units.",
        "processo.objections_heading": "THE HARDEST OBJECTIONS",
        "processo.defense_heading": "THE HONEST DEFENSE",
        "processo.concession_tag": "CONCESSION",
        "processo.skeptic_voice_heading": "THE SWARM'S SKEPTICAL VOICE",

        # ---------- ARCHIVIO ----------
        "radar.eyebrow": "discovery, not a press digest",
        "radar.title_part1": "OB1 ",
        "radar.title_part2": "RADAR",
        "radar.disclaimer": "Attention prioritizer, not a prediction engine: flags who deserves 20 minutes of your human eye this week. Buzz is a corroborating signal, never the only proof.",
        "radar.filters_toggle": "FILTERS",
        "radar.btn_refresh": "REFRESH",
        "radar.last_run_never": "never updated",
        "radar.candidates_shown": "candidates",
        "radar.candidates_capped": "· first {shown} of {total} loaded",
        "radar.mini_curve_missing": "chart: not in the press-monitoring round yet",
        "radar.mini_curve_building": "chart building: {seen}/3 checks",
        "radar.watchlist_btn": "watch",
        "radar.watchlist_btn_active": "watched",
        "radar.load_more": "load more",
        "radar.contra_head": "the counter-argument",
        "radar.status_scanning": "SCAN IN PROGRESS... ({s}s)",
        "radar.status_last_run": "last update: {time} · {ranked}/{evaluated} candidates",
        "radar.filter_role_all": "all roles",
        "radar.filter_age_all": "any age",
        "radar.filter_country_all": "all countries",
    },
}


def translate(key: str, lang: str) -> str:
    """Ripiega sull'italiano se la chiave manca nella lingua richiesta (mai
    un buco vuoto in pagina), e sulla chiave stessa se manca ovunque (un
    placeholder visibile e' un bug da notare, non un crash)."""
    table = TRANSLATIONS.get(lang, {})
    if key in table:
        return table[key]
    return TRANSLATIONS["it"].get(key, key)
