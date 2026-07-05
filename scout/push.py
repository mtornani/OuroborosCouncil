"""
Radar -> Telegram. Riusa il canale e la disciplina di Miss Minute:
max 3 alert/giorno, quiet hours 22-07, CRITICAL passa sempre.

Cosa merita un alert:
  CRITICAL -> finestra CLOSING con breakout alto: agire ora
  HIGH     -> transizione di fase rispetto al run precedente
  HIGH     -> candidato discovery molto ricorrente

Il silenzio e' un valore: se il radar non suona, la watchlist e' stabile.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import requests

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

REPO_ROOT = Path(__file__).resolve().parent.parent
SENT_LOG = REPO_ROOT / "data" / "radar" / "radar_sent.json"

DAILY_LIMIT = 3
QUIET_HOURS = (22, 7)


def _sent_today() -> int:
    if not SENT_LOG.exists():
        return 0
    try:
        with open(SENT_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
        if data.get("date") != datetime.now().strftime("%Y-%m-%d"):
            return 0
        return data.get("count", 0)
    except Exception:
        return 0


def _increment_sent():
    SENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(SENT_LOG, "w", encoding="utf-8") as f:
        json.dump(
            {"date": datetime.now().strftime("%Y-%m-%d"),
             "count": _sent_today() + 1},
            f,
        )


def _should_send(priority: str) -> bool:
    hour = datetime.now().hour
    if priority == "CRITICAL":
        return True
    if hour >= QUIET_HOURS[0] or hour < QUIET_HOURS[1]:
        return False
    if priority == "HIGH":
        return _sent_today() < DAILY_LIMIT
    return False


def send_telegram(text: str) -> bool:
    if not BOT_TOKEN or not CHAT_ID:
        print(f"[radar/push] Telegram non configurato. Messaggio:\n{text}\n")
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=15,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[radar/push] errore invio: {e}")
        return False


def build_alerts(cards: list[dict], prev_cards: list[dict],
                 discoveries: list[dict]) -> list[dict]:
    """Costruisce gli alert confrontando run attuale e precedente."""
    alerts = []
    prev_by_name = {c.get("player"): c for c in prev_cards if "player" in c}

    for card in cards:
        if "error" in card:
            continue
        name = card["player"]
        prev = prev_by_name.get(name)

        # 1. Finestra CLOSING con breakout alto -> agire ORA
        if card["window"] == "CLOSING" and card["breakout"] >= 45:
            was_closing = prev and prev.get("window") == "CLOSING"
            weeks = card.get("weeks_to_mainstream")
            sett = "settimana" if weeks == 1 else "settimane"
            eta = f"\nStima: mainstream tra ~{weeks} {sett}." if weeks else ""
            alerts.append({
                "priority": "HIGH" if was_closing else "CRITICAL",
                "text": (
                    f"🚨 *RADAR: FINESTRA IN CHIUSURA*\n"
                    f"*{name}* ({card.get('club', '?')})\n"
                    f"ADI {card['adi']}/100 — Breakout {card['breakout']}/100\n"
                    f"Fase: {card['phase']}{eta}\n\n"
                    "Perche':\n"
                    + "\n".join(f"• {r}" for r in card["breakout_reasons"][:4])
                    + "\n\n_Visionare/agire ora: ogni settimana aumenta "
                    "concorrenza e prezzo._"
                ),
            })
        # 2. Transizione di fase rispetto al run precedente
        elif prev and prev.get("phase") != card["phase"]:
            alerts.append({
                "priority": "HIGH",
                "text": (
                    f"📈 *RADAR: CAMBIO FASE*\n"
                    f"*{name}*: {prev.get('phase')} → {card['phase']}\n"
                    f"ADI {prev.get('adi')} → {card['adi']}\n\n"
                    + "\n".join(f"• {r}" for r in card["adi_reasons"][:3])
                ),
            })

    # 3. Discovery: candidati con ricorrenza alta, ancora sotto radar
    hot = [d for d in discoveries if d["hits"] >= 3]
    if hot:
        lines = [
            f"• *{d['name']}* — {d['hits']} titoli, "
            f"tier max {d['max_tier']}, lingue: {','.join(d['langs'])}"
            for d in hot[:5]
        ]
        alerts.append({
            "priority": "HIGH",
            "text": (
                "🔍 *RADAR DISCOVERY*\nNomi ricorrenti nelle fonti di "
                "nicchia, non in watchlist:\n" + "\n".join(lines)
                + "\n\n_Se uno ti convince:_ `python -m scout add \"Nome\"`"
            ),
        })

    return alerts


def push_alerts(alerts: list[dict]) -> int:
    sent = 0
    order = {"CRITICAL": 0, "HIGH": 1}
    for alert in sorted(alerts, key=lambda a: order.get(a["priority"], 9)):
        if _should_send(alert["priority"]):
            if send_telegram(alert["text"]):
                _increment_sent()
                sent += 1
        else:
            print(f"[radar/push] filtrato ({alert['priority']}): "
                  f"{alert['text'][:60]}...")
    print(f"[radar/push] {sent} alert inviati, {len(alerts) - sent} filtrati")
    return sent
