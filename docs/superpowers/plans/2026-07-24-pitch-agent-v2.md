# pitch-agent v2 (Closing-Loop) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Baut den deterministischen Kern `scripts/pipeline_engine.py` (Stage-Maschine + Cadence + CRM-QA) plus 4-Phasen-SKILL, der einen Lead über `leads.json` von Kontakt bis Abschluss führt — ohne Auto-Versand.

**Architecture:** Reine Funktionen auf Lead-Dicts (wie `demo_pipeline.py`), stdlib-only, unit-getestet. Ein Python-Kern entscheidet WANN/OB (Cadence, Stage-Übergänge, QA); Haiku-Subagenten (im SKILL, nicht getestet) entscheiden WAS geschrieben wird. `leads.json` ist die einzige Wahrheit. Dashboard wird in diesem Durchgang NICHT angefasst.

**Tech Stack:** Python 3 Standardbibliothek (`json`, `argparse`, `datetime`, `os`, `sys`). Tests mit `unittest`. Kein `requirements.txt`.

## Global Constraints

- **Nur Python-Standardbibliothek.** Kein pip, kein `requirements.txt`.
- **Feld-Shapes folgen dem bestehenden Dashboard-Schema** (`~/agency-dashboard/index.html`), NICHT den Spec-Beispielen: `notes` = Liste von `{"date": "YYYY-MM-DD", "text": "..."}`; `nextAction` = `{"date": "YYYY-MM-DD", "note": "..."}` oder `null`. String-Werte würden das Dashboard-Rendering brechen.
- **Kanonische Stages:** `NEW → CONTACTED → REPLIED → IN_TALKS → WON | LOST` (immer UPPERCASE).
- **JSON schreiben** wie v1: atomar via `.tmp` + `os.replace`, `json.dump(..., ensure_ascii=False, indent=2)`.
- **Cadence-Defaults:** `thresholds = {1: 3, 2: 7, 3: 14}` (Tage seit `lastTouch` je `touchCount`), `maxTouches = 4`. Optionaler Override aus `~/.claude/agency-data/config.json` unter Key `pitchAgent.cadence` (n8n-Config bleibt unangetastet).
- **`migrate` ist idempotent** — zweiter Lauf ändert nichts.
- **Nichts erfinden, kein Auto-Versand.** `date` (Lead-Erfassung) wird NICHT als `lastTouch` verwendet.
- **Docstrings/Kommentare Deutsch, Tech-Begriffe Englisch.** Type-Hints wie in `demo_pipeline.py`.
- **Nach JEDEM Task committen + pushen auf `main`** (Build-Journal-Regel). Verifikation vor Commit: `python3 -m unittest discover -s tests -v` grün.
- **GateGuard aktiv:** vor Write/Edit und erstem Bash die geforderten Fakten präsentieren.

**Verifikationsbefehl (überall):** `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest discover -s tests -v`

---

## Datenmodell (leads.json-Record v2)

```json
{
  "company": "Muster Elektro",
  "status": "CONTACTED",
  "demoUrl": "https://demos-tilind.netlify.app/muster-elektro/",
  "lastTouch": "2026-07-24",
  "touchCount": 2,
  "followUpDue": "2026-07-31",
  "snoozeUntil": null,
  "nextAction": {"date": "2026-07-31", "note": "Follow-up #3 fällig"},
  "notes": [{"date": "2026-07-20", "text": "Erst-DM (FB)"},
            {"date": "2026-07-24", "text": "Follow-up #2 gesendet"}]
}
```

Bestehende v1-Felder (`contact`, `problem`, `source`, `date`, `revenue`, `recurring`, `invoiceOpen`, `lostReason`, `farbe`) bleiben unberührt.

## Modul-Konstanten (Task 1 legt sie an, alle späteren Tasks nutzen sie)

```python
STAGES = ["NEW", "CONTACTED", "REPLIED", "IN_TALKS", "WON", "LOST"]

VALID_TRANSITIONS = {
    ("NEW", "CONTACTED"),
    ("CONTACTED", "CONTACTED"),   # Follow-up-Nudge
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
```

**Umsetzungsentscheidung (Spec-Widerspruch aufgelöst):** `apply_reply("frage"/"einwand")` setzt Ziel `CONTACTED` UND `lastTouch=today` (wir antworten jetzt → Cadence startet neu ab heute), `touchCount` bleibt unverändert (Dialog-Antwort ist kein Aufgeben-Nudge). Das verhindert, dass ein Lead, auf dessen Frage wir gerade antworten, sofort als cadence-fällig erscheint.

---

## Datei-Struktur

- `scripts/pipeline_engine.py` — NEU, der ganze deterministische Kern + CLI. Eine Datei (wie `demo_pipeline.py`), eine Verantwortung: Stage/Cadence/QA-Logik.
- `tests/test_pipeline_engine.py` — NEU, alle Unit-Tests.
- `tests/fixtures/leads.pipeline.sample.json` — NEU, Fake-Leads über alle Stages/Cadence-Fälle.
- `skills/pitch-agent/SKILL.md` — GEÄNDERT, 4-Phasen-Orchestrator (Task 9).
- `README.md`, `INSTALL.md` — GEÄNDERT, v2-Phasen dokumentieren (Task 9).

---

### Task 1: Fixture + Stage-Konstanten + `valid_transition`

**Files:**
- Create: `scripts/pipeline_engine.py`
- Create: `tests/fixtures/leads.pipeline.sample.json`
- Create: `tests/test_pipeline_engine.py`

**Interfaces:**
- Produces: `STAGES`, `VALID_TRANSITIONS`, `REPLY_TARGET`, `DEFAULT_THRESHOLDS`, `DEFAULT_MAX_TOUCHES` (Konstanten oben); `valid_transition(from_stage: str, to_stage: str) -> bool`.

- [ ] **Step 1: Fixture anlegen** — `tests/fixtures/leads.pipeline.sample.json`. Referenz-„heute" der Tests ist `2026-07-24`.

```json
[
  {"company": "New Ohne Demo", "status": "new", "problem": "Keine Website",
   "date": "2026-06-01", "notes": []},
  {"company": "New Mit Demo", "status": "NEW", "problem": "Keine Website",
   "date": "2026-06-02", "demoUrl": "https://demos-tilind.netlify.app/new-mit-demo/", "notes": []},
  {"company": "Contacted Frisch", "status": "CONTACTED",
   "demoUrl": "https://demos-tilind.netlify.app/contacted-frisch/",
   "lastTouch": "2026-07-22", "touchCount": 1, "followUpDue": "2026-07-25",
   "snoozeUntil": null, "nextAction": {"date": "2026-07-25", "note": "Follow-up #2 fällig"}, "notes": []},
  {"company": "Contacted Faellig", "status": "CONTACTED",
   "demoUrl": "https://demos-tilind.netlify.app/contacted-faellig/",
   "lastTouch": "2026-07-21", "touchCount": 1, "followUpDue": "2026-07-24",
   "snoozeUntil": null, "nextAction": {"date": "2026-07-24", "note": "Follow-up #2 fällig"}, "notes": []},
  {"company": "Contacted Faellig3", "status": "CONTACTED",
   "demoUrl": "https://demos-tilind.netlify.app/contacted-faellig3/",
   "lastTouch": "2026-07-17", "touchCount": 2, "followUpDue": "2026-07-24",
   "snoozeUntil": null, "nextAction": {"date": "2026-07-24", "note": "Follow-up #3 fällig"}, "notes": []},
  {"company": "Contacted Aufgeben", "status": "CONTACTED",
   "demoUrl": "https://demos-tilind.netlify.app/contacted-aufgeben/",
   "lastTouch": "2026-07-04", "touchCount": 4, "followUpDue": null,
   "snoozeUntil": null, "nextAction": {"date": "2026-07-04", "note": "Aufgeben prüfen"}, "notes": []},
  {"company": "Contacted Snoozed", "status": "CONTACTED",
   "demoUrl": "https://demos-tilind.netlify.app/contacted-snoozed/",
   "lastTouch": "2026-07-10", "touchCount": 2, "followUpDue": "2026-07-17",
   "snoozeUntil": "2026-08-01", "nextAction": {"date": "2026-08-01", "note": "Später nachfassen"}, "notes": []},
  {"company": "Replied Lead", "status": "REPLIED",
   "demoUrl": "https://demos-tilind.netlify.app/replied-lead/",
   "lastTouch": "2026-07-20", "touchCount": 2, "followUpDue": null,
   "snoozeUntil": null, "nextAction": {"date": "2026-07-23", "note": "Auf Rückfrage antworten"}, "notes": []},
  {"company": "In Talks Lead", "status": "IN_TALKS",
   "demoUrl": "https://demos-tilind.netlify.app/in-talks-lead/",
   "lastTouch": "2026-07-19", "touchCount": 2, "followUpDue": null,
   "snoozeUntil": null, "nextAction": {"date": "2026-07-24", "note": "Angebot senden"}, "notes": []},
  {"company": "Won Lead", "status": "WON",
   "demoUrl": "https://demos-tilind.netlify.app/won-lead/",
   "lastTouch": "2026-07-15", "touchCount": 3, "followUpDue": null,
   "snoozeUntil": null, "nextAction": null, "notes": []},
  {"company": "Lost Lead", "status": "LOST",
   "lastTouch": "2026-07-01", "touchCount": 4, "followUpDue": null,
   "snoozeUntil": null, "nextAction": null, "notes": []},
  {"company": "Contacted Kaputt", "status": "CONTACTED",
   "lastTouch": null, "touchCount": 1, "followUpDue": null,
   "snoozeUntil": null, "nextAction": null, "notes": []}
]
```

- [ ] **Step 2: Failing test schreiben** — `tests/test_pipeline_engine.py`.

```python
# tests/test_pipeline_engine.py
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import pipeline_engine as pe

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "leads.pipeline.sample.json")
TODAY = "2026-07-24"


def _load():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _by(leads, company):
    return next(l for l in leads if l["company"] == company)


class TestTransitions(unittest.TestCase):
    def test_valid_transitions_true(self):
        for a, b in [("NEW", "CONTACTED"), ("CONTACTED", "REPLIED"),
                     ("REPLIED", "IN_TALKS"), ("IN_TALKS", "WON"), ("CONTACTED", "CONTACTED")]:
            self.assertTrue(pe.valid_transition(a, b), f"{a}->{b} sollte gültig sein")

    def test_invalid_transitions_false(self):
        for a, b in [("NEW", "WON"), ("WON", "CONTACTED"), ("LOST", "NEW"),
                     ("NEW", "NEW"), ("IN_TALKS", "REPLIED")]:
            self.assertFalse(pe.valid_transition(a, b), f"{a}->{b} sollte ungültig sein")

    def test_transition_is_case_insensitive(self):
        self.assertTrue(pe.valid_transition("new", "contacted"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline_engine'`

- [ ] **Step 4: Minimal implementieren** — `scripts/pipeline_engine.py` Kopf + Konstanten + `valid_transition`.

```python
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
```

- [ ] **Step 5: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: PASS (3 Tests)

- [ ] **Step 6: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py tests/fixtures/leads.pipeline.sample.json
git commit -m "feat(v2): stage constants + valid_transition + pipeline fixture"
git push origin main
```

---

### Task 2: Datums-Helfer + Cadence-Config-Loader

**Files:**
- Modify: `scripts/pipeline_engine.py`
- Test: `tests/test_pipeline_engine.py`

**Interfaces:**
- Produces: `days_since(iso: str, today_iso: str) -> int`; `load_cadence(config_path: str | None = None) -> tuple[dict, int]` (gibt `(thresholds, max_touches)`; thresholds-Keys sind ints).

- [ ] **Step 1: Failing tests** — an `tests/test_pipeline_engine.py` anhängen (vor dem `if __name__`-Block).

```python
import tempfile


class TestDateAndCadence(unittest.TestCase):
    def test_days_since_positive(self):
        self.assertEqual(pe.days_since("2026-07-21", TODAY), 3)

    def test_days_since_same_day_zero(self):
        self.assertEqual(pe.days_since("2026-07-24", TODAY), 0)

    def test_load_cadence_defaults_when_no_file(self):
        thresholds, maxt = pe.load_cadence("/nonexistent/config.json")
        self.assertEqual(thresholds, {1: 3, 2: 7, 3: 14})
        self.assertEqual(maxt, 4)

    def test_load_cadence_override_from_config(self):
        with tempfile.TemporaryDirectory() as d:
            cfg = os.path.join(d, "config.json")
            with open(cfg, "w", encoding="utf-8") as f:
                json.dump({"n8n": {"apiKey": "x"},
                           "pitchAgent": {"cadence": {"thresholds": {"1": 5}, "maxTouches": 6}}}, f)
            thresholds, maxt = pe.load_cadence(cfg)
            self.assertEqual(thresholds[1], 5)
            self.assertEqual(maxt, 6)
```

- [ ] **Step 2: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestDateAndCadence -v`
Expected: FAIL — `AttributeError: module 'pipeline_engine' has no attribute 'days_since'`

- [ ] **Step 3: Implementieren** — in `pipeline_engine.py` nach den Konstanten einfügen.

```python
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
```

- [ ] **Step 4: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: PASS (alle bisherigen Tests)

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py
git commit -m "feat(v2): days_since + cadence config loader"
git push origin main
```

---

### Task 3: `recompute_due` + `due_for_followup` + `select_due`

**Files:**
- Modify: `scripts/pipeline_engine.py`
- Test: `tests/test_pipeline_engine.py`

**Interfaces:**
- Consumes: `days_since`, `_parse_date`, `DEFAULT_THRESHOLDS`.
- Produces: `recompute_due(lead: dict, thresholds: dict | None = None) -> dict` (setzt nur `followUpDue`-Cache); `due_for_followup(lead: dict, today: str, thresholds: dict | None = None) -> bool`; `select_due(leads: list, today: str, thresholds: dict | None = None) -> list`.

- [ ] **Step 1: Failing tests**

```python
class TestDue(unittest.TestCase):
    def setUp(self):
        self.leads = _load()

    def test_due_at_threshold_boundary(self):
        # touchCount 1, lastTouch vor genau 3 Tagen -> fällig
        self.assertTrue(pe.due_for_followup(_by(self.leads, "Contacted Faellig"), TODAY))

    def test_not_due_below_threshold(self):
        # touchCount 1, lastTouch vor 2 Tagen -> nicht fällig
        self.assertFalse(pe.due_for_followup(_by(self.leads, "Contacted Frisch"), TODAY))

    def test_due_second_threshold(self):
        # touchCount 2, lastTouch vor 7 Tagen -> fällig
        self.assertTrue(pe.due_for_followup(_by(self.leads, "Contacted Faellig3"), TODAY))

    def test_snooze_blocks_due(self):
        self.assertFalse(pe.due_for_followup(_by(self.leads, "Contacted Snoozed"), TODAY))

    def test_maxed_out_not_due(self):
        # touchCount 4 (nicht in thresholds) -> nicht regulär fällig
        self.assertFalse(pe.due_for_followup(_by(self.leads, "Contacted Aufgeben"), TODAY))

    def test_non_contacted_not_due(self):
        self.assertFalse(pe.due_for_followup(_by(self.leads, "Replied Lead"), TODAY))
        self.assertFalse(pe.due_for_followup(_by(self.leads, "New Mit Demo"), TODAY))

    def test_missing_lasttouch_not_due(self):
        self.assertFalse(pe.due_for_followup(_by(self.leads, "Contacted Kaputt"), TODAY))

    def test_select_due_returns_two(self):
        due = pe.select_due(self.leads, TODAY)
        names = sorted(l["company"] for l in due)
        self.assertEqual(names, ["Contacted Faellig", "Contacted Faellig3"])

    def test_recompute_due_sets_cache(self):
        lead = {"status": "CONTACTED", "lastTouch": "2026-07-21", "touchCount": 1}
        pe.recompute_due(lead)
        self.assertEqual(lead["followUpDue"], "2026-07-24")  # +3 Tage

    def test_recompute_due_none_for_terminal(self):
        lead = {"status": "WON", "lastTouch": "2026-07-21", "touchCount": 1}
        pe.recompute_due(lead)
        self.assertIsNone(lead["followUpDue"])
```

- [ ] **Step 2: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestDue -v`
Expected: FAIL — `AttributeError: ... 'due_for_followup'`

- [ ] **Step 3: Implementieren**

```python
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
```

- [ ] **Step 4: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: PASS

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py
git commit -m "feat(v2): cadence due-logic (recompute_due, due_for_followup, select_due)"
git push origin main
```

---

### Task 4: `mark_sent`

**Files:**
- Modify: `scripts/pipeline_engine.py`
- Test: `tests/test_pipeline_engine.py`

**Interfaces:**
- Consumes: `recompute_due`, `_append_note`.
- Produces: `_append_note(lead: dict, today: str, text: str) -> None`; `mark_sent(lead: dict, today: str, thresholds: dict | None = None) -> dict` (touchCount++, lastTouch=today, status=CONTACTED, followUpDue neu, notes-Eintrag, nextAction gesetzt).

- [ ] **Step 1: Failing tests**

```python
class TestMarkSent(unittest.TestCase):
    def test_mark_sent_increments_and_dates(self):
        lead = {"company": "X", "status": "CONTACTED", "lastTouch": "2026-07-21",
                "touchCount": 1, "notes": []}
        pe.mark_sent(lead, TODAY)
        self.assertEqual(lead["touchCount"], 2)
        self.assertEqual(lead["lastTouch"], TODAY)
        self.assertEqual(lead["status"], "CONTACTED")
        self.assertEqual(lead["followUpDue"], "2026-07-31")  # +7 (touchCount 2)

    def test_mark_sent_appends_note_object(self):
        lead = {"company": "X", "status": "CONTACTED", "lastTouch": "2026-07-21",
                "touchCount": 1, "notes": []}
        pe.mark_sent(lead, TODAY)
        self.assertEqual(lead["notes"][-1], {"date": TODAY, "text": "Follow-up #2 gesendet"})

    def test_mark_sent_nextaction_is_object(self):
        lead = {"company": "X", "status": "CONTACTED", "lastTouch": "2026-07-21",
                "touchCount": 1, "notes": []}
        pe.mark_sent(lead, TODAY)
        self.assertEqual(lead["nextAction"]["date"], "2026-07-31")
        self.assertIn("fällig", lead["nextAction"]["note"])

    def test_mark_sent_at_max_flags_aufgeben(self):
        lead = {"company": "X", "status": "CONTACTED", "lastTouch": "2026-07-04",
                "touchCount": 3, "notes": []}
        pe.mark_sent(lead, TODAY)  # -> touchCount 4
        self.assertEqual(lead["touchCount"], 4)
        self.assertIsNone(lead["followUpDue"])
        self.assertIn("Aufgeben", lead["nextAction"]["note"])
```

- [ ] **Step 2: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestMarkSent -v`
Expected: FAIL — `AttributeError: ... 'mark_sent'`

- [ ] **Step 3: Implementieren**

```python
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
```

- [ ] **Step 4: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: PASS

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py
git commit -m "feat(v2): mark_sent (touch increment, cadence + note update)"
git push origin main
```

---

### Task 5: `apply_reply`

**Files:**
- Modify: `scripts/pipeline_engine.py`
- Test: `tests/test_pipeline_engine.py`

**Interfaces:**
- Consumes: `REPLY_TARGET`, `recompute_due`, `_append_note`, `DEFAULT_THRESHOLDS`.
- Produces: `apply_reply(lead: dict, reply_class: str, today: str, snooze_until: str | None = None, reply_text: str | None = None, thresholds: dict | None = None) -> dict`.

Zielstufen: `interessiert→IN_TALKS`, `frage/einwand→CONTACTED` (+ `lastTouch=today`, Cadence-Reset, `touchCount` unverändert), `später→CONTACTED` (+ `snoozeUntil`), `nein→LOST`. `notes`-Eintrag immer. Unbekannte Klasse oder `später` ohne `snooze_until` → `ValueError`.

- [ ] **Step 1: Failing tests**

```python
class TestApplyReply(unittest.TestCase):
    def _contacted(self):
        return {"company": "X", "status": "CONTACTED", "lastTouch": "2026-07-17",
                "touchCount": 2, "notes": [], "demoUrl": "https://x/"}

    def test_interessiert_to_in_talks(self):
        lead = self._contacted()
        pe.apply_reply(lead, "interessiert", TODAY)
        self.assertEqual(lead["status"], "IN_TALKS")
        self.assertIsNone(lead["followUpDue"])

    def test_frage_stays_contacted_resets_cadence(self):
        lead = self._contacted()
        pe.apply_reply(lead, "frage", TODAY)
        self.assertEqual(lead["status"], "CONTACTED")
        self.assertEqual(lead["lastTouch"], TODAY)       # Cadence-Reset
        self.assertEqual(lead["touchCount"], 2)          # Dialog zählt nicht als Nudge
        self.assertEqual(lead["followUpDue"], "2026-07-31")  # +7 ab heute

    def test_einwand_stays_contacted(self):
        lead = self._contacted()
        pe.apply_reply(lead, "einwand", TODAY)
        self.assertEqual(lead["status"], "CONTACTED")

    def test_spaeter_sets_snooze(self):
        lead = self._contacted()
        pe.apply_reply(lead, "später", TODAY, snooze_until="2026-08-15")
        self.assertEqual(lead["status"], "CONTACTED")
        self.assertEqual(lead["snoozeUntil"], "2026-08-15")

    def test_spaeter_without_snooze_raises(self):
        with self.assertRaises(ValueError):
            pe.apply_reply(self._contacted(), "später", TODAY)

    def test_nein_to_lost(self):
        lead = self._contacted()
        pe.apply_reply(lead, "nein", TODAY)
        self.assertEqual(lead["status"], "LOST")
        self.assertIsNone(lead["nextAction"])

    def test_unknown_class_raises(self):
        with self.assertRaises(ValueError):
            pe.apply_reply(self._contacted(), "vielleicht", TODAY)

    def test_reply_text_lands_in_notes(self):
        lead = self._contacted()
        pe.apply_reply(lead, "frage", TODAY, reply_text="Was kostet das?")
        self.assertEqual(lead["notes"][-1]["date"], TODAY)
        self.assertIn("Was kostet das?", lead["notes"][-1]["text"])
```

- [ ] **Step 2: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestApplyReply -v`
Expected: FAIL — `AttributeError: ... 'apply_reply'`

- [ ] **Step 3: Implementieren**

```python
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
```

- [ ] **Step 4: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: PASS

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py
git commit -m "feat(v2): apply_reply (deterministic stage move from reply class)"
git push origin main
```

---

### Task 6: `migrate` (idempotent)

**Files:**
- Modify: `scripts/pipeline_engine.py`
- Test: `tests/test_pipeline_engine.py`

**Interfaces:**
- Consumes: `STAGES`, `recompute_due`.
- Produces: `migrate(leads: list, today: str | None = None, thresholds: dict | None = None) -> list` (mutiert und gibt dieselbe Liste zurück).

Regeln: `status` UPPERCASE, `new→NEW`; unbekannte Stages (z. B. altes `OFFER/ACTIVE/DONE`) bleiben unverändert-uppercased (QA flaggt sie später). Felder initialisieren, wo fehlend: `touchCount=0`, `lastTouch=None`, `snoozeUntil=None`, `notes=[]`; `followUpDue` via `recompute_due`. `date` wird NICHT als `lastTouch` verwendet. Zweiter Lauf ändert nichts.

- [ ] **Step 1: Failing tests**

```python
class TestMigrate(unittest.TestCase):
    def test_normalizes_status_case(self):
        leads = [{"company": "A", "status": "new"}]
        pe.migrate(leads)
        self.assertEqual(leads[0]["status"], "NEW")

    def test_initializes_missing_fields(self):
        leads = [{"company": "A", "status": "new"}]
        pe.migrate(leads)
        self.assertEqual(leads[0]["touchCount"], 0)
        self.assertIsNone(leads[0]["lastTouch"])
        self.assertIsNone(leads[0]["snoozeUntil"])
        self.assertEqual(leads[0]["notes"], [])
        self.assertIsNone(leads[0]["followUpDue"])

    def test_does_not_use_date_as_lasttouch(self):
        leads = [{"company": "A", "status": "new", "date": "2026-06-01"}]
        pe.migrate(leads)
        self.assertIsNone(leads[0]["lastTouch"])

    def test_new_with_demourl_stays_new(self):
        leads = _load()
        pe.migrate(leads)
        self.assertEqual(_by(leads, "New Mit Demo")["status"], "NEW")

    def test_idempotent(self):
        leads = _load()
        once = json.dumps(pe.migrate(leads), sort_keys=True, ensure_ascii=False)
        twice = json.dumps(pe.migrate(leads), sort_keys=True, ensure_ascii=False)
        self.assertEqual(once, twice)

    def test_unknown_legacy_status_preserved_uppercased(self):
        leads = [{"company": "A", "status": "offer"}]
        pe.migrate(leads)
        self.assertEqual(leads[0]["status"], "OFFER")  # nicht zerstört, QA flaggt
```

- [ ] **Step 2: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestMigrate -v`
Expected: FAIL — `AttributeError: ... 'migrate'`

- [ ] **Step 3: Implementieren**

```python
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
```

- [ ] **Step 4: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: PASS

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py
git commit -m "feat(v2): idempotent migrate (status normalize + field init)"
git push origin main
```

---

### Task 7: `crm_qa` (Laufzeit-CRM-QA)

**Files:**
- Modify: `scripts/pipeline_engine.py`
- Test: `tests/test_pipeline_engine.py`

**Interfaces:**
- Consumes: `STAGES`, `recompute_due`, `DEFAULT_MAX_TOUCHES`.
- Produces: `crm_qa(leads: list, today: str, thresholds: dict | None = None, max_touches: int = DEFAULT_MAX_TOUCHES, repair: bool = False) -> dict`.

Report-Shape: `{"status": "PASS"|"WARN", "warnungen": [str], "graufaelle": [str], "aktion_noetig": [company], "aufgeben_kandidaten": [company]}`. Prüfungen: ungültige Stage → Warnung; `CONTACTED/REPLIED/IN_TALKS/WON` ohne `demoUrl` → Warnung; `CONTACTED` ohne `lastTouch` → Warnung; `CONTACTED` mit `touchCount>=max_touches` → `aufgeben_kandidaten` + Graufall; alle `REPLIED` → `aktion_noetig`; nicht-terminaler Lead ohne `nextAction` → Waisen-Warnung. `repair=True`: `followUpDue` neu rechnen + fehlende `nextAction` bei nicht-terminalen setzen. `status="WARN"` sobald Warnungen ODER Graufälle existieren.

- [ ] **Step 1: Failing tests**

```python
class TestCrmQa(unittest.TestCase):
    def setUp(self):
        self.leads = _load()

    def test_flags_contacted_without_demourl(self):
        r = pe.crm_qa(self.leads, TODAY)
        self.assertTrue(any("Contacted Kaputt" in w for w in r["warnungen"]))

    def test_aufgeben_candidate_listed(self):
        r = pe.crm_qa(self.leads, TODAY)
        self.assertIn("Contacted Aufgeben", r["aufgeben_kandidaten"])

    def test_replied_in_aktion_noetig(self):
        r = pe.crm_qa(self.leads, TODAY)
        self.assertIn("Replied Lead", r["aktion_noetig"])

    def test_status_warn_when_issues(self):
        r = pe.crm_qa(self.leads, TODAY)
        self.assertEqual(r["status"], "WARN")

    def test_clean_leads_pass(self):
        clean = [{"company": "Ok", "status": "IN_TALKS", "demoUrl": "https://x/",
                  "lastTouch": "2026-07-20", "touchCount": 2, "followUpDue": None,
                  "snoozeUntil": None, "nextAction": {"date": TODAY, "note": "x"}, "notes": []}]
        r = pe.crm_qa(clean, TODAY)
        self.assertEqual(r["status"], "PASS")

    def test_repair_sets_missing_nextaction(self):
        leads = [{"company": "Orphan", "status": "CONTACTED", "demoUrl": "https://x/",
                  "lastTouch": "2026-07-21", "touchCount": 1, "followUpDue": None,
                  "snoozeUntil": None, "nextAction": None, "notes": []}]
        pe.crm_qa(leads, TODAY, repair=True)
        self.assertIsNotNone(leads[0]["nextAction"])
        self.assertEqual(leads[0]["followUpDue"], "2026-07-24")  # recomputed
```

- [ ] **Step 2: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestCrmQa -v`
Expected: FAIL — `AttributeError: ... 'crm_qa'`

- [ ] **Step 3: Implementieren**

```python
def crm_qa(leads: list, today: str, thresholds: dict | None = None,
           max_touches: int = DEFAULT_MAX_TOUCHES, repair: bool = False) -> dict:
    """Laufzeit-CRM-QA: Triviales optional auto-fixen (repair), Rest flaggen."""
    warnungen, graufaelle, aktion_noetig, aufgeben = [], [], [], []
    need_demo = {"CONTACTED", "REPLIED", "IN_TALKS", "WON"}
    terminal = {"WON", "LOST"}
    for lead in leads:
        name = lead.get("company", "?")
        st = (lead.get("status") or "").upper()
        if st not in STAGES:
            warnungen.append(f"{name}: ungültige Stage '{st}'")
            continue
        if st in need_demo and not lead.get("demoUrl"):
            warnungen.append(f"{name}: {st} ohne demoUrl")
        if st == "CONTACTED" and not lead.get("lastTouch"):
            warnungen.append(f"{name}: CONTACTED ohne lastTouch")
        if st == "CONTACTED" and int(lead.get("touchCount") or 0) >= max_touches:
            aufgeben.append(name)
            graufaelle.append(f"{name}: {lead.get('touchCount')} Touches ohne Antwort — aufgeben?")
        if st == "REPLIED":
            aktion_noetig.append(name)
        if st not in terminal and not lead.get("nextAction"):
            if repair:
                recompute_due(lead, thresholds)
                lead["nextAction"] = {"date": today, "note": "Nächsten Schritt festlegen"}
            else:
                warnungen.append(f"{name}: {st} ohne nextAction (Waise)")
        if repair:
            recompute_due(lead, thresholds)
    status = "WARN" if (warnungen or graufaelle) else "PASS"
    return {"status": status, "warnungen": warnungen, "graufaelle": graufaelle,
            "aktion_noetig": aktion_noetig, "aufgeben_kandidaten": aufgeben}
```

- [ ] **Step 4: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine -v`
Expected: PASS

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py
git commit -m "feat(v2): crm_qa runtime pipeline check (+ optional repair)"
git push origin main
```

---

### Task 8: CLI (`migrate`/`due`/`advance-apply`/`react-apply`/`qa`)

**Files:**
- Modify: `scripts/pipeline_engine.py`
- Test: `tests/test_pipeline_engine.py`

**Interfaces:**
- Consumes: alle bisherigen Funktionen.
- Produces: `main(argv=None)`; Helfer `_load_json(path)`, `_write_json_atomic(path, data)` (identisch zu `demo_pipeline.py`).

CLI-Verträge:
- `migrate --leads <path>` — migriert Datei in-place, druckt `N Leads migriert.`
- `due --leads <path> [--today ISO] [--config <path>]` — druckt JSON-Array fälliger Leads (`company`, `touchCount`, `lastTouch`, `followUpDue`).
- `advance-apply --leads <path> --sent <map.json> [--today ISO] [--config <path>]` — `map.json` = `["CompanyA", "CompanyB"]` (Liste gesendeter Firmen) ODER `{"CompanyA": true}`; ruft `mark_sent` je Treffer, schreibt zurück, druckt `K Lead(s) als gesendet markiert.`
- `react-apply --leads <path> --company <name> --reply-class <klasse> [--snooze ISO] [--reply-text <txt>] [--today ISO]` — `apply_reply`, schreibt zurück, druckt neue Stage.
- `qa --leads <path> [--repair] [--today ISO] [--config <path>]` — druckt Report-JSON; bei `--repair` Datei zurückschreiben.

`--today` default = `date.today().isoformat()`.

- [ ] **Step 1: Failing tests** (subprocess-CLI wie v1)

```python
import subprocess
import shutil

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "pipeline_engine.py")


class TestCli(unittest.TestCase):
    def _tmp_leads(self, d):
        p = os.path.join(d, "leads.json")
        shutil.copy(FIXTURE, p)
        return p

    def test_migrate_cli_writes_and_counts(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._tmp_leads(d)
            res = subprocess.run(["python3", SCRIPT, "migrate", "--leads", p],
                                 capture_output=True, text=True, check=True)
            self.assertIn("migriert", res.stdout)
            with open(p, encoding="utf-8") as f:
                self.assertEqual(json.load(f)[0]["status"], "NEW")

    def test_due_cli_lists_due(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._tmp_leads(d)
            res = subprocess.run(["python3", SCRIPT, "due", "--leads", p, "--today", TODAY],
                                 capture_output=True, text=True, check=True)
            names = {x["company"] for x in json.loads(res.stdout)}
            self.assertEqual(names, {"Contacted Faellig", "Contacted Faellig3"})

    def test_react_apply_cli_sets_stage(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._tmp_leads(d)
            subprocess.run(["python3", SCRIPT, "react-apply", "--leads", p,
                            "--company", "Replied Lead", "--reply-class", "interessiert",
                            "--today", TODAY], capture_output=True, text=True, check=True)
            with open(p, encoding="utf-8") as f:
                self.assertEqual(_by(json.load(f), "Replied Lead")["status"], "IN_TALKS")

    def test_qa_cli_prints_report(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._tmp_leads(d)
            res = subprocess.run(["python3", SCRIPT, "qa", "--leads", p, "--today", TODAY],
                                 capture_output=True, text=True, check=True)
            self.assertIn("aufgeben_kandidaten", res.stdout)
```

- [ ] **Step 2: Run — muss fehlschlagen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestCli -v`
Expected: FAIL (kein `main`/CLI, subprocess returncode != 0)

- [ ] **Step 3: Implementieren** — ans Ende von `pipeline_engine.py`.

```python
def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _today(args):
    return args.today or date.today().isoformat()


def cmd_migrate(args):
    leads = _load_json(args.leads)
    migrate(leads, _today(args))
    _write_json_atomic(args.leads, leads)
    print(f"{len(leads)} Leads migriert.")


def cmd_due(args):
    thresholds, _ = load_cadence(args.config)
    leads = _load_json(args.leads)
    due = select_due(leads, _today(args), thresholds)
    out = [{"company": l.get("company"), "touchCount": l.get("touchCount"),
            "lastTouch": l.get("lastTouch"), "followUpDue": l.get("followUpDue")} for l in due]
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_advance_apply(args):
    thresholds, _ = load_cadence(args.config)
    leads = _load_json(args.leads)
    sent = _load_json(args.sent)
    names = set(sent) if isinstance(sent, list) else {k for k, v in sent.items() if v}
    hits = 0
    for lead in leads:
        if lead.get("company") in names:
            mark_sent(lead, _today(args), thresholds)
            hits += 1
    _write_json_atomic(args.leads, leads)
    print(f"{hits} Lead(s) als gesendet markiert.")


def cmd_react_apply(args):
    leads = _load_json(args.leads)
    hit = next((l for l in leads if l.get("company") == args.company), None)
    if hit is None:
        sys.exit(f"Lead nicht gefunden: {args.company}")
    apply_reply(hit, args.reply_class, _today(args),
                snooze_until=args.snooze, reply_text=args.reply_text)
    _write_json_atomic(args.leads, leads)
    print(f"{args.company} -> {hit['status']}")


def cmd_qa(args):
    thresholds, max_touches = load_cadence(args.config)
    leads = _load_json(args.leads)
    report = crm_qa(leads, _today(args), thresholds, max_touches, repair=args.repair)
    if args.repair:
        _write_json_atomic(args.leads, leads)
    print(json.dumps(report, ensure_ascii=False, indent=2))


def main(argv=None):
    p = argparse.ArgumentParser(description="pitch-agent v2 Closing-Loop Engine")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("migrate"); m.add_argument("--leads", required=True)
    m.add_argument("--today"); m.set_defaults(func=cmd_migrate)

    d = sub.add_parser("due"); d.add_argument("--leads", required=True)
    d.add_argument("--today"); d.add_argument("--config"); d.set_defaults(func=cmd_due)

    a = sub.add_parser("advance-apply"); a.add_argument("--leads", required=True)
    a.add_argument("--sent", required=True); a.add_argument("--today")
    a.add_argument("--config"); a.set_defaults(func=cmd_advance_apply)

    r = sub.add_parser("react-apply"); r.add_argument("--leads", required=True)
    r.add_argument("--company", required=True)
    r.add_argument("--reply-class", required=True, dest="reply_class")
    r.add_argument("--snooze"); r.add_argument("--reply-text", dest="reply_text")
    r.add_argument("--today"); r.set_defaults(func=cmd_react_apply)

    q = sub.add_parser("qa"); q.add_argument("--leads", required=True)
    q.add_argument("--repair", action="store_true"); q.add_argument("--today")
    q.add_argument("--config"); q.set_defaults(func=cmd_qa)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run — voller Lauf muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest discover -s tests -v`
Expected: PASS (alle Tests aus demo_pipeline UND pipeline_engine)

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add scripts/pipeline_engine.py tests/test_pipeline_engine.py
git commit -m "feat(v2): CLI (migrate/due/advance-apply/react-apply/qa)"
git push origin main
```

---

### Task 9: SKILL.md 4-Phasen-Orchestrator + README/INSTALL

**Files:**
- Modify: `skills/pitch-agent/SKILL.md`
- Modify: `README.md`
- Modify: `INSTALL.md`

**Interfaces:** Keine Python-Interfaces. Verifikation per grep (keine `{{`-Platzhalter neu eingeführt, alle 4 Phasen benannt).

- [ ] **Step 1: SKILL.md erweitern** — Der bestehende v1-Inhalt bleibt als **Phase 1 (Acquire)**. Danach diesen Block ergänzen (Platzhalter `{{PITCH_AGENT_DIR}}`/`{{LEADS_JSON}}` beibehalten — INSTALL.md ersetzt sie):

````markdown
## v2 — Closing-Loop (4 Phasen)

`/pitch-agent` ohne Argument = **Acquire** (oben). Mit Phasenwort: `advance`, `react …`, `review`.
Engine: `python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py`. Einmalig zuerst:
`… migrate --leads {{LEADS_JSON}}` (idempotent, normalisiert Status + initialisiert Felder).

### Phase 2: Advance (fällige Follow-ups)
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py due --leads {{LEADS_JSON}} > /tmp/pitch-due.json
```
Keine fälligen Leads → sagen und stoppen. Sonst pro fälligem Lead EIN Nudge-Entwurf via Haiku-
Subagenten (parallel, `model: "haiku"`), Ton eskaliert mit `touchCount` (#2 freundliche Erinnerung,
#3 kurz mit Mehrwert, #4 letzte weiche Meldung). Prompt bekommt `company, problem, demoUrl,
touchCount`. Nichts erfinden. Entwürfe dem User zeigen. Erst NACH Senden (User bestätigt):
`{company:true}`-Map nach `/tmp/pitch-sent.json`, dann
`… advance-apply --leads {{LEADS_JSON}} --sent /tmp/pitch-sent.json`.

### Phase 3: React (Antwort verarbeiten)
User meldet: „Lead X hat geantwortet: «Text»". Haiku klassifiziert in genau eine Klasse
`interessiert | frage | einwand | später | nein` und entwirft die Reaktion. Klasse unklar →
User fragen, nicht raten. Dann:
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py react-apply --leads {{LEADS_JSON}} \
  --company "X" --reply-class <klasse> [--snooze YYYY-MM-DD] --reply-text "«Text»"
```
(`später` braucht `--snooze`.) Reaktion dem User zum Senden zeigen — kein Auto-Versand.

### Phase 4: Review (CRM-QA)
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py qa --leads {{LEADS_JSON}} --repair
```
Druckt `status/warnungen/graufaelle/aktion_noetig/aufgeben_kandidaten`. `--repair` fixt Triviales
(followUpDue, fehlende nextAction). Graufälle + „Aktion nötig" (REPLIED) dem User auflisten,
nichts verschweigen.
````

- [ ] **Step 2: README.md** — im Feature-/Ablauf-Abschnitt die 4 Phasen in 4 Zeilen ergänzen (Acquire/Advance/React/Review) mit Verweis auf `scripts/pipeline_engine.py`. Bestehenden v1-Text nicht löschen.

- [ ] **Step 3: INSTALL.md** — falls dort Test-/Dateilisten stehen: `scripts/pipeline_engine.py` + `tests/test_pipeline_engine.py` ergänzen, sodass der `grep -L "{{"`-Check und der unittest-Lauf weiterhin stimmen. Sonst unverändert lassen.

- [ ] **Step 4: Verifikation**

```bash
cd ~/Desktop/buildingchallenge_agent
grep -c "Phase 2: Advance\|Phase 3: React\|Phase 4: Review" skills/pitch-agent/SKILL.md   # >= 3
grep -n "pipeline_engine.py" skills/pitch-agent/SKILL.md README.md                        # Treffer
python3 -m unittest discover -s tests -v                                                   # weiterhin grün
```
Expected: alle 4 Phasen benannt, Engine referenziert, Tests grün.

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add skills/pitch-agent/SKILL.md README.md INSTALL.md
git commit -m "docs(v2): 4-phase closing-loop orchestrator in SKILL + README/INSTALL"
git push origin main
```

---

### Task 10: E2E-Trockenlauf (deterministisch)

**Files:**
- Test: `tests/test_pipeline_engine.py`

**Interfaces:** Consumes CLI aus Task 8.

- [ ] **Step 1: Failing test** — die Kette `migrate → due → advance-apply → qa` auf einer Kopie der Fixture.

```python
class TestE2E(unittest.TestCase):
    def test_full_chain_deterministic(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "leads.json")
            shutil.copy(FIXTURE, p)
            run = lambda *a: subprocess.run(["python3", SCRIPT, *a],
                                            capture_output=True, text=True, check=True)
            run("migrate", "--leads", p)
            due = json.loads(run("due", "--leads", p, "--today", TODAY).stdout)
            sent = os.path.join(d, "sent.json")
            with open(sent, "w", encoding="utf-8") as f:
                json.dump([x["company"] for x in due], f)
            run("advance-apply", "--leads", p, "--sent", sent, "--today", TODAY)
            # Nach dem Senden ist keiner der zuvor Fälligen erneut sofort fällig
            due2 = json.loads(run("due", "--leads", p, "--today", TODAY).stdout)
            self.assertEqual(due2, [])
            report = json.loads(run("qa", "--leads", p, "--today", TODAY).stdout)
            self.assertIn("Contacted Aufgeben", report["aufgeben_kandidaten"])
```

- [ ] **Step 2: Run — ausführen**
Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest tests.test_pipeline_engine.TestE2E -v`

- [ ] **Step 3: Grün machen** — falls `due2` nicht leer: prüfen, dass `mark_sent` `lastTouch=today` + neuen `followUpDue` setzt (Task 4). Kein neuer Code erwartet, wenn Tasks 1-8 korrekt sind.

- [ ] **Step 4: Run — muss bestehen**

Run: `cd ~/Desktop/buildingchallenge_agent && python3 -m unittest discover -s tests -v`
Expected: PASS (alle Tests)

- [ ] **Step 5: Commit + Push**

```bash
cd ~/Desktop/buildingchallenge_agent
git add tests/test_pipeline_engine.py
git commit -m "test(v2): deterministic E2E dry-run (migrate->due->advance->qa)"
git push origin main
```

---

## Abschluss-Schritt (nach allen Tasks, betrieblich — kein Test)

Echte Migration einmal gegen die produktive Datei (idempotent, sicher):

```bash
python3 ~/.claude/skills/pitch-agent/scripts/pipeline_engine.py migrate \
  --leads ~/.claude/agency-data/leads.json
```

Danach `finishing-a-development-branch`-Skill: Tests grün bestätigen, Optionen präsentieren. Screen-Recording/Abgabe-Post (aus v1-Handoff) bleiben separat offen.

## Was dieser Plan NICHT enthält (bewusst)

- **Kein Dashboard-Umbau** (User-Entscheidung 2026-07-24). Die Engine schreibt v2-Status + Objekt-Shapes, sodass das laufende Dashboard nicht bricht; das schöne Rendern der neuen Stages ist ein späterer Mini-Schritt.
- Kein Auto-Versand, kein DM-Pull, kein n8n/Cron (Umfang B).
- LLM-Stufen (Nudge/Reaktion) nicht unit-getestet — Dry-Run + Sichtprüfung im SKILL.

## Self-Review

- **Spec-Coverage:** Datenmodell (Task 1/4/5/6) ✓, Engine-Funktionen valid_transition/due/select_due/apply_reply/mark_sent/recompute_due/crm_qa (Tasks 1,3,4,5,7) ✓, migrate (Task 6) ✓, CLI migrate/due/advance-apply/react-apply/qa (Task 8) ✓, SKILL 4 Phasen (Task 9) ✓, Cadence in config.json (Task 2) ✓, Test-Strategie inkl. E2E (Task 10) ✓, Migration der echten Leads (Abschluss-Schritt) ✓. Dashboard-Anschluss bewusst ausgeklammert (User-Entscheidung).
- **Type-Konsistenz:** `thresholds`-Keys durchgängig int; `notes`=`[{date,text}]`, `nextAction`=`{date,note}`|None überall; `recompute_due` ohne `today` (followUpDue ist today-unabhängig) — bewusste, dokumentierte Abweichung von der Spec-Signatur.
