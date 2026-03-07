"""
MissMinute Telegram Push — Invia segnali proattivi.
Rate limited: max 3 messaggi/giorno, quiet hours 22:00-07:00.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import requests

# Config — stessi token di Eater of Logs
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Caricamento da .env se locale
if not BOT_TOKEN:
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(r"D:\AI\_archivio\miss_minute\.env"))
        BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
        CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    except Exception:
        pass

# Path intelligente: locale se esiste, altrimenti current dir (CI)
_LOCAL_DIR = Path(r"D:\AI\.miss_minute")
BASE_DIR = _LOCAL_DIR if _LOCAL_DIR.exists() else Path(".")
INTEL_FILE = BASE_DIR / "web_intel.json" if BASE_DIR == _LOCAL_DIR else Path("web_intel.json")
SENT_LOG = BASE_DIR / "telegram_sent.json" if BASE_DIR == _LOCAL_DIR else Path("telegram_sent.json")

DAILY_LIMIT = 3
QUIET_HOURS = (22, 7)  # No notifiche 22:00-07:00


def _load_sent_today() -> int:
    """Conta messaggi inviati oggi."""
    if not SENT_LOG.exists():
        return 0
    try:
        with open(SENT_LOG, "r", encoding="utf-8") as f:
            data = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        if data.get("date") != today:
            return 0
        return data.get("count", 0)
    except Exception:
        return 0


def _increment_sent():
    """Incrementa il contatore giornaliero."""
    today = datetime.now().strftime("%Y-%m-%d")
    count = _load_sent_today() + 1
    with open(SENT_LOG, "w", encoding="utf-8") as f:
        json.dump({"date": today, "count": count}, f)


def should_send(signal: dict) -> bool:
    """Decide se inviare questo segnale su Telegram."""
    hour = datetime.now().hour
    priority = signal.get("priority", "LOW")

    # CRITICAL va sempre (anche in quiet hours)
    if priority == "CRITICAL":
        return True

    # Quiet hours: blocca tutto tranne CRITICAL
    if hour >= QUIET_HOURS[0] or hour < QUIET_HOURS[1]:
        return False

    # HIGH va se non abbiamo superato il limite giornaliero
    if priority == "HIGH":
        return _load_sent_today() < DAILY_LIMIT

    # MEDIUM e LOW: solo in MissMinute locale, MAI Telegram
    return False


def send_telegram(text: str) -> dict | None:
    """Invia messaggio Telegram."""
    if not BOT_TOKEN or not CHAT_ID:
        print(f"Telegram non configurato. Messaggio:\n{text}")
        return None

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    resp = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        },
    )
    return resp.json()


def format_signal(signal: dict) -> str:
    """Formatta un segnale per Telegram."""
    emoji = {
        "CRITICAL": "🔴",
        "HIGH": "🟠",
        "MEDIUM": "🟡",
        "LOW": "⚪",
    }.get(signal.get("priority", "LOW"), "⚪")

    lines = [
        f"{emoji} *MissMinute Alert*",
        f"Tipo: `{signal.get('type', 'UNKNOWN')}`",
        "",
        signal.get("message", ""),
    ]

    if signal.get("action_hint"):
        lines.append("")
        lines.append(f"_{signal['action_hint']}_")

    if signal.get("url"):
        lines.append("")
        lines.append(f"[Link]({signal['url']})")

    return "\n".join(lines)


def process_and_push():
    """Leggi intel, filtra segnali, invia quelli rilevanti."""
    if not INTEL_FILE.exists():
        print("web_intel.json non trovato. Esegui prima web_monitor.py")
        return

    with open(INTEL_FILE, "r", encoding="utf-8") as f:
        intel = json.load(f)

    signals = intel.get("signals", [])

    if not signals:
        print("Nessun segnale rilevante. Silenzio.")
        return

    sent = 0
    skipped = 0

    for signal in signals:
        if should_send(signal):
            msg = format_signal(signal)
            send_telegram(msg)
            _increment_sent()
            sent += 1
            print(f"Inviato: {signal.get('type')} -- {signal.get('message', '')[:50]}")
        else:
            skipped += 1

    print(f"Telegram push: {sent} inviati, {skipped} filtrati")

    if sent > 1:
        send_telegram(f"*MissMinute Summary*: {sent} segnali rilevanti oggi.")


if __name__ == "__main__":
    process_and_push()
