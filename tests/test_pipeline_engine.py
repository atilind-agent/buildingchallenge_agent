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
