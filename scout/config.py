"""Caricamento watchlist giocatori da players.yaml."""
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PLAYERS_FILE = REPO_ROOT / "players.yaml"


def load_players() -> list[dict]:
    if not PLAYERS_FILE.exists():
        return []
    with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    players = []
    for name, cfg in (data.get("players") or {}).items():
        cfg = cfg or {}
        players.append(
            {
                "name": name,
                "club": cfg.get("club", ""),
                "born": cfg.get("born", ""),
                "position": cfg.get("position", ""),
                "country": cfg.get("country", ""),
                "aliases": cfg.get("aliases", []) or [],
                "notes": cfg.get("notes", ""),
            }
        )
    return players


def add_player(name: str, **kwargs) -> bool:
    """Aggiunge un giocatore alla watchlist. Ritorna False se gia' presente."""
    data = {}
    if PLAYERS_FILE.exists():
        with open(PLAYERS_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    players = data.setdefault("players", {})
    if name in players:
        return False
    players[name] = {k: v for k, v in kwargs.items() if v}
    with open(PLAYERS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    return True
