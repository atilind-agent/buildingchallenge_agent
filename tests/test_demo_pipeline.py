# tests/test_demo_pipeline.py
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import demo_pipeline as dp


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


if __name__ == "__main__":
    unittest.main()
