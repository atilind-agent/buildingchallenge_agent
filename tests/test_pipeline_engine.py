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


if __name__ == "__main__":
    unittest.main()
