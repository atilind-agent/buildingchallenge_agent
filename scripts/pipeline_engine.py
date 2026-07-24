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


def recompute_due(lead: dict, thresholds: dict | None = None) -> dict:
    """Setzt nur den followUpDue-Cache (lastTouch + Schwelle je touchCount).
    Nur für CONTACTED mit gültigem touchCount/lastTouch; sonst None.
    today-unabhängig -> idempotent."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    tc = int(lead.get("touchCount") or 0)
    lt = lead.get("lastTouch")
    if (lead.get("status") or "").upper() == "CONTACTED" and lt and tc in thresholds:
        lead["followUpDue"] = (_parse_date(lt) + timedelta(days=thresholds[tc])).isoformat()
    else:
        lead["followUpDue"] = None
    return lead


def due_for_followup(lead: dict, today: str, thresholds: dict | None = None) -> bool:
    """True, wenn ein CONTACTED-Lead einen Follow-up-Nudge fällig hat."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    if (lead.get("status") or "").upper() != "CONTACTED":
        return False
    tc = int(lead.get("touchCount") or 0)
    if tc not in thresholds:
        return False
    lt = lead.get("lastTouch")
    if not lt:
        return False
    snooze = lead.get("snoozeUntil")
    if snooze and _parse_date(snooze) > _parse_date(today):
        return False
    return days_since(lt, today) >= thresholds[tc]


def select_due(leads: list, today: str, thresholds: dict | None = None) -> list:
    """Alle fälligen CONTACTED-Leads (Advance-Input)."""
    return [l for l in leads if due_for_followup(l, today, thresholds)]


def _append_note(lead: dict, today: str, text: str) -> None:
    """Hängt einen {date, text}-Eintrag an notes (Dashboard-Shape)."""
    notes = lead.get("notes")
    if not isinstance(notes, list):
        notes = []
        lead["notes"] = notes
    notes.append({"date": today, "text": text})


def mark_sent(lead: dict, today: str, thresholds: dict | None = None) -> dict:
    """Nach dem Senden eines Follow-up-Nudges: touchCount++, lastTouch=today,
    Status CONTACTED, followUpDue + nextAction neu, notes-Eintrag."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    lead["touchCount"] = int(lead.get("touchCount") or 0) + 1
    lead["lastTouch"] = today
    lead["status"] = "CONTACTED"
    recompute_due(lead, thresholds)
    n = lead["touchCount"]
    _append_note(lead, today, f"Follow-up #{n} gesendet")
    if lead.get("followUpDue"):
        lead["nextAction"] = {"date": lead["followUpDue"], "note": f"Follow-up #{n + 1} fällig"}
    else:
        lead["nextAction"] = {"date": today, "note": "Aufgeben prüfen (max. Touches erreicht)"}
    return lead


def apply_reply(lead: dict, reply_class: str, today: str,
                snooze_until: str | None = None, reply_text: str | None = None,
                thresholds: dict | None = None) -> dict:
    """Deterministischer Stage-Move aus einer gemeldeten Antwort.
    Klassen: interessiert|frage|einwand|später|nein. Setzt status, nextAction, notes."""
    thresholds = thresholds or DEFAULT_THRESHOLDS
    if reply_class not in REPLY_TARGET:
        raise ValueError(f"unbekannte reply_class: {reply_class}")
    if reply_class == "später" and not snooze_until:
        raise ValueError("reply_class 'später' erfordert snooze_until")

    target = REPLY_TARGET[reply_class]
    lead["status"] = target

    note_text = f"Antwort ({reply_class})"
    if reply_text:
        note_text += f": {reply_text}"
    _append_note(lead, today, note_text)

    if reply_class in ("frage", "einwand"):
        # Wir antworten jetzt -> Cadence-Uhr startet neu, touchCount unverändert
        lead["lastTouch"] = today
        recompute_due(lead, thresholds)
        lead["nextAction"] = {"date": lead.get("followUpDue") or today,
                              "note": "Wartet auf Rückmeldung"}
    elif reply_class == "später":
        lead["snoozeUntil"] = snooze_until
        lead["followUpDue"] = None
        lead["nextAction"] = {"date": snooze_until, "note": "Später nachfassen"}
    elif reply_class == "interessiert":
        lead["followUpDue"] = None
        lead["nextAction"] = {"date": today, "note": "Gespräch führen / Angebot"}
    else:  # nein -> LOST
        lead["followUpDue"] = None
        lead["nextAction"] = None
    return lead


def migrate(leads: list, today: str | None = None, thresholds: dict | None = None) -> list:
    """Idempotent: status normalisieren + v2-Felder initialisieren.
    date wird NICHT als lastTouch verwendet (nichts erfinden)."""
    for lead in leads:
        st = (lead.get("status") or "NEW").strip().upper()
        lead["status"] = "NEW" if st in ("NEW", "") else st
        if "touchCount" not in lead or lead["touchCount"] is None:
            lead["touchCount"] = 0
        if "lastTouch" not in lead:
            lead["lastTouch"] = None
        if "snoozeUntil" not in lead:
            lead["snoozeUntil"] = None
        if not isinstance(lead.get("notes"), list):
            lead["notes"] = []
        recompute_due(lead, thresholds)
    return leads
