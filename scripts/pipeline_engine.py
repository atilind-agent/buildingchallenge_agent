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
