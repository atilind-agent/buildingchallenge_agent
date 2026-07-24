#!/usr/bin/env python3
"""pitch-agent v2: deterministische Closing-Loop-Engine.

Stage-Maschine + Cadence + CRM-QA über leads.json. Nur Standardbibliothek.
Tests: python3 -m unittest discover -s tests
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

STAGES = ["NEW", "CONTACTED", "REPLIED", "IN_TALKS", "WON", "LOST"]

VALID_TRANSITIONS = {
    ("NEW", "CONTACTED"),
    ("CONTACTED", "CONTACTED"),
    ("CONTACTED", "REPLIED"),
    ("CONTACTED", "LOST"),
    ("REPLIED", "IN_TALKS"),
    ("REPLIED", "CONTACTED"),
    ("REPLIED", "LOST"),
    ("IN_TALKS", "WON"),
    ("IN_TALKS", "LOST"),
}

REPLY_TARGET = {
    "interessiert": "IN_TALKS",
    "frage": "CONTACTED",
    "einwand": "CONTACTED",
    "später": "CONTACTED",
    "nein": "LOST",
}

DEFAULT_THRESHOLDS = {1: 3, 2: 7, 3: 14}
DEFAULT_MAX_TOUCHES = 4


def valid_transition(from_stage: str, to_stage: str) -> bool:
    """True, wenn der Stage-Übergang in der kanonischen Tabelle erlaubt ist."""
    a = (from_stage or "").strip().upper()
    b = (to_stage or "").strip().upper()
    return (a, b) in VALID_TRANSITIONS


def _parse_date(iso: str) -> date:
    return date.fromisoformat(iso)


def days_since(iso: str, today_iso: str) -> int:
    """Ganze Tage von iso bis today_iso (positiv, wenn iso in der Vergangenheit)."""
    return (_parse_date(today_iso) - _parse_date(iso)).days


def load_cadence(config_path: str | None = None):
    """(thresholds, max_touches). Defaults, optional überschrieben aus config.json
    unter pitchAgent.cadence. Fehlt Datei/Key, greifen die Defaults."""
    thresholds = dict(DEFAULT_THRESHOLDS)
    max_touches = DEFAULT_MAX_TOUCHES
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            cad = (cfg.get("pitchAgent") or {}).get("cadence") or {}
            if "thresholds" in cad:
                thresholds = {int(k): int(v) for k, v in cad["thresholds"].items()}
            if "maxTouches" in cad:
                max_touches = int(cad["maxTouches"])
        except (ValueError, OSError):
            pass  # kaputte Config -> Defaults, nichts erfinden
    return thresholds, max_touches
