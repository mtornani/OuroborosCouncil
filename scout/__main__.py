"""
CLI Ouroboros Radar.

  python -m scout run          # raccolta + scoring + report + alert
  python -m scout run --no-push    # senza Telegram (es. test locale)
  python -m scout run --no-discovery
  python -m scout report       # rigenera report dall'ultimo run
  python -m scout add "Nome Cognome" --club X --born 2008 --position AT
  python -m scout status       # stato watchlist in terminale
"""
import argparse
import sys

from . import config, discover, history, model, push, report, sources


def cmd_run(args):
    players = config.load_players()
    if not players:
        print("players.yaml vuoto. Aggiungi giocatori con: python -m scout add \"Nome\"")
        return 1

    prev_cards = [c for c in history.load_latest() if "player" in c]

    print(f"[radar] Raccolta segnali per {len(players)} giocatori...")
    cards = []
    for player in players:
        print(f"  -> {player['name']}...", flush=True)
        try:
            snap = sources.collect_player(player)
            history.append_snapshot(snap)
        except Exception as e:
            print(f"     ERRORE raccolta: {e}")
        hist = history.load_history(player["name"])
        card = model.score_player(player, hist)
        if "error" not in card:
            print(
                f"     ADI {card['adi']} | breakout {card['breakout']} | "
                f"{card['phase']} | finestra {card['window']}"
            )
        cards.append(card)

    discoveries = []
    if not args.no_discovery:
        print("[radar] Discovery: scansione fonti di nicchia...")
        known = {p["name"] for p in players}
        try:
            discoveries = discover.run_discovery(known)
            print(f"[radar] Discovery: {len(discoveries)} candidati")
        except Exception as e:
            print(f"[radar] Discovery fallita: {e}")

    history.save_latest(cards)
    md = report.write_markdown(cards, discoveries)
    html = report.write_html(cards, discoveries)
    print(f"[radar] Report: {md.name}, {html}")

    alerts = push.build_alerts(cards, prev_cards, discoveries)
    if args.no_push:
        for a in alerts:
            print(f"\n--- ALERT {a['priority']} (non inviato) ---\n{a['text']}")
    else:
        push.push_alerts(alerts)
    return 0


def cmd_report(args):
    cards = history.load_latest()
    if not cards:
        print("Nessun run precedente. Esegui: python -m scout run")
        return 1
    report.write_markdown(cards, [])
    report.write_html(cards, [])
    print("Report rigenerati da latest.json (senza discovery).")
    return 0


def cmd_add(args):
    ok = config.add_player(
        args.name, club=args.club, born=args.born,
        position=args.position, country=args.country,
        aliases=args.alias or [], notes=args.notes,
    )
    if ok:
        print(f"Aggiunto: {args.name}. Al prossimo run il radar lo monitora.")
        return 0
    print(f"{args.name} e' gia' in watchlist.")
    return 1


def cmd_status(args):
    cards = [c for c in history.load_latest() if "player" in c]
    if not cards:
        print("Nessun run precedente. Esegui: python -m scout run")
        return 1
    order = {"CLOSING": 0, "OPEN": 1, "CLOSED": 2}
    cards.sort(key=lambda c: (order.get(c["window"], 9), -c["breakout"]))
    badge = {"OPEN": "🟢", "CLOSING": "🟠", "CLOSED": "⚪"}
    print(f"\n🐍 OUROBOROS RADAR — {cards[0]['date']}\n")
    for c in cards:
        weeks = c.get("weeks_to_mainstream")
        eta = f" | mainstream ~{weeks} sett." if weeks else ""
        print(
            f"  {badge[c['window']]} {c['player']:<24} "
            f"ADI {c['adi']:>5} | brk {c['breakout']:>5} | {c['phase']}{eta}"
        )
    print()
    return 0


def main():
    parser = argparse.ArgumentParser(prog="scout", description="Ouroboros Radar")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="raccolta + scoring + report + alert")
    p_run.add_argument("--no-push", action="store_true")
    p_run.add_argument("--no-discovery", action="store_true")
    p_run.set_defaults(func=cmd_run)

    p_rep = sub.add_parser("report", help="rigenera report dall'ultimo run")
    p_rep.set_defaults(func=cmd_report)

    p_add = sub.add_parser("add", help="aggiungi giocatore alla watchlist")
    p_add.add_argument("name")
    p_add.add_argument("--club", default="")
    p_add.add_argument("--born", default="")
    p_add.add_argument("--position", default="")
    p_add.add_argument("--country", default="")
    p_add.add_argument("--alias", action="append")
    p_add.add_argument("--notes", default="")
    p_add.set_defaults(func=cmd_add)

    p_st = sub.add_parser("status", help="stato watchlist")
    p_st.set_defaults(func=cmd_status)

    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
