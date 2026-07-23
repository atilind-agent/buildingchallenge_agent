# tests/test_demo_pipeline.py
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import demo_pipeline as dp

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "leads.sample.json")


class TestHelpers(unittest.TestCase):
    def test_slugify_lowercases_and_dashes(self):
        self.assertEqual(dp.slugify("Elektro Müller GmbH"), "elektro-mueller-gmbh")

    def test_slugify_strips_punctuation_and_collapses(self):
        self.assertEqual(dp.slugify("Thomas Zygar Sanitär-Installation"),
                         "thomas-zygar-sanitaer-installation")

    def test_extract_phone(self):
        c = "Tel: +49 2841 1347 / Mail: info@x.de"
        self.assertEqual(dp.extract_phone(c), "+49 2841 1347")

    def test_extract_phone_none(self):
        self.assertIsNone(dp.extract_phone("Mail: info@x.de"))

    def test_extract_social_facebook_and_instagram(self):
        c = "Tel: +49 1 / FB: https://www.facebook.com/firmax/ / IG: https://www.instagram.com/firmax"
        fb, ig = dp.extract_social(c)
        self.assertEqual(fb, "https://www.facebook.com/firmax/")
        self.assertEqual(ig, "https://www.instagram.com/firmax")

    def test_extract_social_none(self):
        self.assertEqual(dp.extract_social("Tel: +49 2841 1347"), (None, None))

    def test_has_chatbot_true(self):
        self.assertTrue(dp.has_chatbot("Chat/WhatsApp vorhanden"))

    def test_has_chatbot_false_for_kein_chat(self):
        self.assertFalse(dp.has_chatbot("Website 2020, kein Chat-Widget"))

    def test_has_chatbot_false_for_no_website(self):
        self.assertFalse(dp.has_chatbot("Keine Website"))


class TestSelect(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE, encoding="utf-8") as f:
            self.leads = json.load(f)

    def test_selects_only_no_chat_with_social_open_leads(self):
        cands = dp.select_candidates(self.leads)
        names = sorted(c["company"] for c in cands)
        self.assertEqual(names, ["Dachbau Beispiel", "Elektro Musterlicht GmbH"])

    def test_candidate_fields(self):
        cand = next(c for c in dp.select_candidates(self.leads)
                    if c["company"] == "Elektro Musterlicht GmbH")
        self.assertEqual(cand["slug"], "elektro-musterlicht-gmbh")
        self.assertEqual(cand["phone"], "+49 2841 111111")
        self.assertEqual(cand["facebook"], "https://www.facebook.com/musterlicht/")
        self.assertEqual(cand["website"], "https://musterlicht-example.de/")
        self.assertEqual(cand["farbe"], "#1E5AA8")

    def test_require_social_false_includes_email_only_lead(self):
        cands = dp.select_candidates(self.leads, require_social=False)
        names = {c["company"] for c in cands}
        self.assertIn("Sanitär Habenschon", names)

    def test_include_done_true_includes_lead_with_demourl(self):
        cands = dp.select_candidates(self.leads, include_done=True)
        names = {c["company"] for c in cands}
        self.assertIn("Maler Fertig", names)


class TestBuildConfig(unittest.TestCase):
    def _cand(self):
        return {"company": "Elektro Musterlicht GmbH", "slug": "elektro-musterlicht-gmbh",
                "phone": "+49 2841 111111", "facebook": "https://fb/x", "instagram": None,
                "website": "https://musterlicht-example.de/", "problem": "Website 2019, kein Chat-Widget",
                "farbe": "#1E5AA8"}

    def test_build_config_uses_enrichment(self):
        enr = {"gewerk": "Elektrotechnik", "stadt": "Moers",
               "leistungen": "Elektroinstallation, Photovoltaik", "oeffnungszeiten": "Mo-Fr 8-16 Uhr",
               "farbe": "#0A7C2F", "faq": "Notdienst rund um die Uhr."}
        cfg = dp.build_config(self._cand(), enr)
        self.assertEqual(cfg["slug"], "elektro-musterlicht-gmbh")
        self.assertEqual(cfg["name"], "Elektro Musterlicht GmbH")
        self.assertEqual(cfg["gewerk"], "Elektrotechnik")
        self.assertEqual(cfg["stadt"], "Moers")
        self.assertEqual(cfg["notfall_nummer"], "+49 2841 111111")
        self.assertEqual(cfg["leistungen"], "Elektroinstallation, Photovoltaik")
        self.assertEqual(cfg["oeffnungszeiten"], "Mo-Fr 8-16 Uhr")
        self.assertEqual(cfg["farbe"], "#0A7C2F")
        self.assertEqual(cfg["faq"], "Notdienst rund um die Uhr.")

    def test_build_config_falls_back(self):
        cfg = dp.build_config(self._cand(), {})
        self.assertEqual(cfg["gewerk"], "Handwerksbetrieb")
        self.assertEqual(cfg["stadt"], "")
        self.assertEqual(cfg["leistungen"], "")
        self.assertEqual(cfg["oeffnungszeiten"], "Mo-Fr 8-17 Uhr")
        self.assertEqual(cfg["farbe"], "#1E5AA8")  # aus Lead-farbe, da enrichment leer

    def test_build_config_default_color_when_nothing(self):
        cand = self._cand(); cand["farbe"] = None
        cfg = dp.build_config(cand, {})
        self.assertEqual(cfg["farbe"], "#F97316")


if __name__ == "__main__":
    unittest.main()
