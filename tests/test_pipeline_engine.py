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


if __name__ == "__main__":
    unittest.main()
