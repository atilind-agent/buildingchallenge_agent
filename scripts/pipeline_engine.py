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
                thresholds.update({int(k): int(v) for k, v in cad["thresholds"].items()})
            if "maxTouches" in cad:
                max_touches = int(cad["maxTouches"])
        except (ValueError, OSError, AttributeError, TypeError):
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
    cur = (lead.get("status") or "").upper()
    if not valid_transition(cur, "CONTACTED"):
        raise ValueError(f"Nudge in Stage {cur} nicht möglich")
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
    cur = (lead.get("status") or "").upper()
    if cur != "REPLIED" and not valid_transition(cur, "REPLIED"):
        raise ValueError(f"Antwort in Stage {cur} nicht möglich (Lead muss CONTACTED oder REPLIED sein)")

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
    thresholds, _ = load_cadence(args.config)
    leads = _load_json(args.leads)
    hit = next((l for l in leads if l.get("company") == args.company), None)
    if hit is None:
        sys.exit(f"Lead nicht gefunden: {args.company}")
    try:
        apply_reply(hit, args.reply_class, _today(args),
                    snooze_until=args.snooze, reply_text=args.reply_text, thresholds=thresholds)
    except ValueError as e:
        sys.exit(str(e))
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
    r.add_argument("--today"); r.add_argument("--config"); r.set_defaults(func=cmd_react_apply)

    q = sub.add_parser("qa"); q.add_argument("--leads", required=True)
    q.add_argument("--repair", action="store_true"); q.add_argument("--today")
    q.add_argument("--config"); q.set_defaults(func=cmd_qa)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
