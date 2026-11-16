"""Laedt config.json und (falls vorhanden) config.local.json."""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent


def _merge(base: dict, extra: dict) -> dict:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


def _expand(cfg: dict, names: list) -> list:
    """Ersetzt den Platzhalter '@hoeherer_dienst' durch die Rollenliste."""
    out = []
    for name in names:
        if name == "@hoeherer_dienst":
            out.extend(cfg["hoeherer_dienst"])
        else:
            out.append(name)
    return out


def load() -> dict:
    cfg = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
    local = BASE / "config.local.json"
    if local.exists():
        _merge(cfg, json.loads(local.read_text(encoding="utf-8")))
    cfg["berechtigte_rollen"] = _expand(cfg, cfg["berechtigte_rollen"])
    for cat in cfg["tickets"]["kategorien"]:
        cat["rollen"] = _expand(cfg, cat["rollen"])
    return cfg
