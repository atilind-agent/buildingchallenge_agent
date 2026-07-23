# pitch-agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Claude-Code-Agent, der aus einer vorhandenen `leads.json` pro passendem Lead automatisch eine live deployte, personalisierte Chatbot-Demo und einen fertigen Outreach-DM-Entwurf erzeugt.

**Architecture:** Ein deterministischer Python-Kern (`scripts/demo_pipeline.py`, stdlib-only, mit `unittest` getestet) übernimmt Filtern, Config-Bau und Zurückschreiben; ein Orchestrator-Skill (`skills/pitch-agent/SKILL.md`) steuert den Fluss und dispatcht Haiku-Subagenten für die sprachlich-unsicheren Stufen (Website-Anreicherung + Outreach-Text). Die eigentliche Demo-Erzeugung/Deploy nutzt das bestehende `~/demo-fabrik` (generate.py + Netlify).

**Tech Stack:** Python 3 (nur Standardbibliothek), Claude Code Skills + Haiku-Subagenten, bestehendes `demo-fabrik` (generate.py, template.html, Netlify-CLI).

## Global Constraints

- **Sprache:** Alle Nutzer-sichtbaren Ausgaben und Doku auf Deutsch; Code-Kommentare Englisch.
- **Keine externen Python-Deps:** ausschließlich Standardbibliothek; Tests mit `python3 -m unittest`. Keine `requirements.txt`.
- **Keine Kundendaten im Repo:** echte `leads.json`, Configs, Demos, Outreach-Texte liegen unter `~/demo-fabrik` bzw. `~/.claude/agency-data` — nie im Repo committen. Im Repo nur Fake-Fixtures.
- **Platzhalter für Teilbarkeit:** SKILL.md nutzt `{{PITCH_AGENT_DIR}}`, `{{DEMO_FABRIK_DIR}}`, `{{LEADS_JSON}}`; INSTALL.md ersetzt sie per `sed`.
- **Nichts erfinden (Denklogik):** Angaben zu einem Betrieb stammen aus echter Quelle (Website/leads.json) oder aus dokumentierten Fallbacks, nie aus Plausibilität.
- **Git-Regel:** Nach jedem Task automatisch committen + auf `main` pushen (Co-Author-Trailer), kurz Bescheid geben.
- **Kein Überschreiben:** bestehende Configs in `~/demo-fabrik/configs/` werden nie überschrieben (nur mit explizitem `--force`).
- **Netlify-Basis-URL:** `https://demos-tilind.netlify.app`; Demo-URL-Schema `<base>/<slug>/`.

**leads.json-Schema (real, Quelle der Wahrheit):** Felder u.a. `company`, `contact` (Freitext: `Tel: … / Mail: … / FB: … / IG: …`), `website` (URL oder null), `problem` (Freitext, z.B. `"Website 2020, kein Chat-Widget"`, `"Keine Website"`, `"Chat/WhatsApp vorhanden"`), `source`, `status` (`"new"`/`"NEW"`/…), `demoUrl` (URL oder fehlt), `farbe` (Hex oder fehlt).

**Config-Schema (aus `~/demo-fabrik/generate.py`):** `slug`, `name`, `gewerk`, `stadt`, `notfall_nummer`, `oeffnungszeiten`, `leistungen`, `faq`, `farbe`. Fehlende Felder füllt generate.py aus seinen DEFAULTS (`cal_link`, `webhook` etc.).

---

## File Structure

- `scripts/demo_pipeline.py` — deterministischer Kern (pure Funktionen + argparse-CLI). Eine Verantwortung: Lead-Daten → Configs/Kandidaten/Rückschreiben.
- `tests/fixtures/leads.sample.json` — Fake-Betriebe, decken alle Filter-Fälle ab. Keine echten Kunden.
- `tests/test_demo_pipeline.py` — `unittest`-Tests für die pure Funktionen.
- `skills/pitch-agent/SKILL.md` — Orchestrator-Gehirn (Frontmatter + Ablauf + Subagenten-Prompts).
- `INSTALL.md` — an Claude adressiert, Schritt-für-Schritt-Installation.
- `README.md` — Challenge-Template-Abschnitte, angereichert.
- `LICENSE` — MIT.

---

### Task 1: Deterministische Extraktions-Helfer (slugify, phone, social, chatbot)

**Files:**
- Create: `scripts/demo_pipeline.py`
- Test: `tests/test_demo_pipeline.py`

**Interfaces:**
- Produces:
  - `slugify(name: str) -> str`
  - `extract_phone(contact: str) -> str | None`
  - `extract_social(contact: str) -> tuple[str | None, str | None]` (facebook_url, instagram_url)
  - `has_chatbot(problem: str) -> bool`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_demo_pipeline -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'demo_pipeline'` (Datei existiert noch nicht).

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/demo_pipeline.py
#!/usr/bin/env python3
"""pitch-agent: deterministischer Kern.

Liest leads.json, wählt Kandidaten (kein Chatbot + Social vorhanden),
baut demo-fabrik-Configs und schreibt Demo-URLs nach leads.json zurück.
Nur Standardbibliothek. Tests: python3 -m unittest discover.
"""
import re

_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
            "Ä": "ae", "Ö": "oe", "Ü": "ue"}


def slugify(name: str) -> str:
    """Betriebsname -> URL-Slug [a-z0-9-], umlaut-aware."""
    s = (name or "").strip()
    for k, v in _UMLAUTS.items():
        s = s.replace(k, v)
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def extract_phone(contact: str) -> str | None:
    """Telefonnummer aus dem contact-Freitext ('Tel: ...')."""
    m = re.search(r"Tel:\s*([^/]+)", contact or "")
    return m.group(1).strip() if m else None


def extract_social(contact: str) -> tuple[str | None, str | None]:
    """(facebook_url, instagram_url) aus dem contact-Freitext, sonst None."""
    text = contact or ""
    fb = re.search(r"https?://[^\s]*facebook\.com[^\s]*", text)
    ig = re.search(r"https?://[^\s]*instagram\.com[^\s]*", text)
    clean = lambda m: m.group(0).rstrip(".,;") if m else None
    return clean(fb), clean(ig)


def has_chatbot(problem: str) -> bool:
    """True, wenn der problem-Text ein vorhandenes Chat/WhatsApp-Widget nennt."""
    p = (problem or "").lower()
    return "vorhanden" in p and ("chat" in p or "whatsapp" in p)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_demo_pipeline -v`
Expected: PASS (9 Tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/demo_pipeline.py tests/test_demo_pipeline.py
git commit -m "feat: deterministische Extraktions-Helfer (slugify, phone, social, chatbot)"
git push origin main
```

---

### Task 2: Kandidaten-Filter (`select_candidates`) + Fixture

**Files:**
- Modify: `scripts/demo_pipeline.py`
- Create: `tests/fixtures/leads.sample.json`
- Modify: `tests/test_demo_pipeline.py`

**Interfaces:**
- Consumes: `slugify`, `extract_phone`, `extract_social`, `has_chatbot` (Task 1)
- Produces: `select_candidates(leads: list[dict], require_social: bool = True, include_done: bool = False) -> list[dict]`
  Kandidat-Dict-Felder: `company, slug, phone, facebook, instagram, website, problem, farbe`.

- [ ] **Step 1: Fixture anlegen (Fake-Daten, alle Fälle)**

```json
[
  {"company": "Elektro Musterlicht GmbH", "contact": "Tel: +49 2841 111111 / FB: https://www.facebook.com/musterlicht/", "website": "https://musterlicht-example.de/", "problem": "Website 2019, kein Chat-Widget", "source": "lead-finder PLZ 47441", "status": "new", "farbe": "#1E5AA8"},
  {"company": "Dachbau Beispiel", "contact": "Tel: +49 2841 222222 / IG: https://www.instagram.com/dachbaubeispiel", "website": null, "problem": "Keine Website", "source": "lead-finder PLZ 47441", "status": "NEW"},
  {"company": "Sanitär Habenschon", "contact": "Tel: +49 2841 333333 / Mail: info@habenschon-example.de", "website": "https://habenschon-example.de/", "problem": "Website 2021, kein Chat-Widget", "source": "lead-finder PLZ 47441", "status": "new"},
  {"company": "Auto Chathaus", "contact": "Tel: +49 2841 444444 / FB: https://www.facebook.com/chathaus/", "website": "https://chathaus-example.de/", "problem": "Chat/WhatsApp vorhanden", "source": "lead-finder PLZ 47441", "status": "new"},
  {"company": "Maler Fertig", "contact": "Tel: +49 2841 555555 / FB: https://www.facebook.com/malerfertig/", "website": "https://malerfertig-example.de/", "problem": "Website 2020, kein Chat-Widget", "source": "lead-finder PLZ 47441", "status": "new", "demoUrl": "https://demos-tilind.netlify.app/maler-fertig/"},
  {"company": "Tischler Gewonnen", "contact": "Tel: +49 2841 666666 / IG: https://www.instagram.com/tischlergewonnen", "website": "https://gewonnen-example.de/", "problem": "Website 2020, kein Chat-Widget", "source": "lead-finder PLZ 47441", "status": "won"}
]
```

Erwartetes Filter-Ergebnis (require_social=True, include_done=False): **2 Kandidaten** — `Elektro Musterlicht GmbH` und `Dachbau Beispiel`. Ausgeschlossen: `Sanitär Habenschon` (kein Social), `Auto Chathaus` (hat Chatbot), `Maler Fertig` (demoUrl gesetzt), `Tischler Gewonnen` (status won).

- [ ] **Step 2: Write the failing test**

```python
# in tests/test_demo_pipeline.py ergänzen
import json

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "leads.sample.json")


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
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python3 -m unittest tests.test_demo_pipeline.TestSelect -v`
Expected: FAIL — `AttributeError: module 'demo_pipeline' has no attribute 'select_candidates'`.

- [ ] **Step 4: Write minimal implementation**

```python
# scripts/demo_pipeline.py ergänzen
def select_candidates(leads, require_social=True, include_done=False):
    """Leads -> Kandidaten: status new, kein Chatbot, (optional) Social vorhanden,
    (optional) noch keine demoUrl."""
    out = []
    for lead in leads:
        status = (lead.get("status") or "").strip().lower()
        if status != "new":
            continue
        if lead.get("demoUrl") and not include_done:
            continue
        if has_chatbot(lead.get("problem") or ""):
            continue
        fb, ig = extract_social(lead.get("contact") or "")
        if require_social and not (fb or ig):
            continue
        out.append({
            "company": lead.get("company"),
            "slug": slugify(lead.get("company") or ""),
            "phone": extract_phone(lead.get("contact") or ""),
            "facebook": fb,
            "instagram": ig,
            "website": lead.get("website"),
            "problem": lead.get("problem") or "",
            "farbe": lead.get("farbe"),
        })
    return out
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_demo_pipeline -v`
Expected: PASS (alle Tests grün).

- [ ] **Step 6: Commit**

```bash
git add scripts/demo_pipeline.py tests/test_demo_pipeline.py tests/fixtures/leads.sample.json
git commit -m "feat: Kandidaten-Filter select_candidates + Test-Fixture"
git push origin main
```

---

### Task 3: Config-Bau (`build_config`)

**Files:**
- Modify: `scripts/demo_pipeline.py`
- Modify: `tests/test_demo_pipeline.py`

**Interfaces:**
- Consumes: Kandidat-Dict (Task 2)
- Produces: `build_config(candidate: dict, enrichment: dict) -> dict` — vollständiges demo-fabrik-Config-Dict.

- [ ] **Step 1: Write the failing test**

```python
# in tests/test_demo_pipeline.py ergänzen
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_demo_pipeline.TestBuildConfig -v`
Expected: FAIL — `AttributeError: module 'demo_pipeline' has no attribute 'build_config'`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/demo_pipeline.py ergänzen
_FALLBACK_OEFFNUNG = "Mo-Fr 8-17 Uhr"
_FALLBACK_FARBE = "#F97316"


def build_config(candidate, enrichment):
    """Kandidat + Website-Anreicherung -> demo-fabrik-Config-Dict.
    Anreicherung schlägt Lead-Werte schlägt Defaults."""
    enr = enrichment or {}
    return {
        "slug": candidate["slug"],
        "name": candidate["company"],
        "gewerk": enr.get("gewerk") or "Handwerksbetrieb",
        "stadt": enr.get("stadt") or "",
        "notfall_nummer": candidate.get("phone") or "",
        "oeffnungszeiten": enr.get("oeffnungszeiten") or _FALLBACK_OEFFNUNG,
        "leistungen": enr.get("leistungen") or "",
        "faq": enr.get("faq") or "",
        "farbe": enr.get("farbe") or candidate.get("farbe") or _FALLBACK_FARBE,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_demo_pipeline -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/demo_pipeline.py tests/test_demo_pipeline.py
git commit -m "feat: build_config (Anreicherung > Lead > Default)"
git push origin main
```

---

### Task 4: Demo-URL zurückschreiben (`update_lead_demo_url`)

**Files:**
- Modify: `scripts/demo_pipeline.py`
- Modify: `tests/test_demo_pipeline.py`

**Interfaces:**
- Produces: `update_lead_demo_url(leads: list[dict], company: str, url: str) -> bool` — setzt `demoUrl` beim passenden Lead, gibt True zurück wenn ein Lead getroffen wurde.

- [ ] **Step 1: Write the failing test**

```python
# in tests/test_demo_pipeline.py ergänzen
class TestWriteBack(unittest.TestCase):
    def test_sets_demo_url_on_matching_company(self):
        leads = [{"company": "A"}, {"company": "Elektro Musterlicht GmbH"}]
        hit = dp.update_lead_demo_url(leads, "Elektro Musterlicht GmbH",
                                      "https://demos-tilind.netlify.app/elektro-musterlicht-gmbh/")
        self.assertTrue(hit)
        self.assertEqual(leads[1]["demoUrl"],
                         "https://demos-tilind.netlify.app/elektro-musterlicht-gmbh/")

    def test_returns_false_when_no_match(self):
        leads = [{"company": "A"}]
        self.assertFalse(dp.update_lead_demo_url(leads, "Nicht Da", "https://x/"))
        self.assertNotIn("demoUrl", leads[0])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_demo_pipeline.TestWriteBack -v`
Expected: FAIL — `AttributeError: ... 'update_lead_demo_url'`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/demo_pipeline.py ergänzen
def update_lead_demo_url(leads, company, url):
    """Setzt demoUrl beim Lead mit passendem company. True wenn getroffen."""
    for lead in leads:
        if lead.get("company") == company:
            lead["demoUrl"] = url
            return True
    return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_demo_pipeline -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/demo_pipeline.py tests/test_demo_pipeline.py
git commit -m "feat: update_lead_demo_url (demoUrl zurück in leads.json)"
git push origin main
```

---

### Task 5: CLI-Verdrahtung (`select`, `build`, `write-back`)

**Files:**
- Modify: `scripts/demo_pipeline.py`
- Modify: `tests/test_demo_pipeline.py`

**Interfaces:**
- Consumes: alle pure Funktionen (Task 1–4)
- Produces: CLI-Subcommands:
  - `select --leads <path> [--no-require-social] [--include-done]` → druckt Kandidaten-JSON auf stdout.
  - `build --enriched <path> --demo-fabrik <dir> [--force] [--no-deploy] [--base-url <url>]` → schreibt Configs, baut (generate.py), deployt (netlify), druckt `{slug: demoUrl}`-JSON.
  - `write-back --leads <path> --map <path>` → liest `{company: demoUrl}`-Map, setzt demoUrl, schreibt leads.json atomar zurück.

Die `build`-Subprozess-Schritte (generate.py, netlify) sind Integration; getestet wird der `select`-CLI-Pfad über subprocess plus die Config-Schreiblogik (kein Überschreiben).

- [ ] **Step 1: Write the failing test**

```python
# in tests/test_demo_pipeline.py ergänzen
import subprocess
import tempfile

SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts", "demo_pipeline.py")


class TestCli(unittest.TestCase):
    def test_select_cli_prints_two_candidates(self):
        res = subprocess.run(
            ["python3", SCRIPT, "select", "--leads", FIXTURE],
            capture_output=True, text=True, check=True)
        cands = json.loads(res.stdout)
        self.assertEqual(len(cands), 2)

    def test_write_configs_skips_existing(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "configs"))
            existing = os.path.join(d, "configs", "elektro-musterlicht-gmbh.json")
            with open(existing, "w", encoding="utf-8") as f:
                f.write('{"slug": "elektro-musterlicht-gmbh", "name": "ALT"}')
            cand = {"company": "Elektro Musterlicht GmbH", "slug": "elektro-musterlicht-gmbh",
                    "phone": "1", "facebook": None, "instagram": None, "website": None,
                    "problem": "", "farbe": "#1E5AA8"}
            written = dp.write_configs([{"candidate": cand, "enrichment": {}}], d, force=False)
            self.assertEqual(written, [])  # existierte -> nicht überschrieben
            with open(existing, encoding="utf-8") as f:
                self.assertIn("ALT", f.read())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_demo_pipeline.TestCli -v`
Expected: FAIL — `select`-Subcommand existiert noch nicht / `write_configs` fehlt.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/demo_pipeline.py ergänzen (oben: import argparse, json, os, subprocess, sys, urllib.request)
import argparse
import json
import os
import subprocess
import sys
import urllib.request

DEFAULT_BASE_URL = "https://demos-tilind.netlify.app"


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def write_configs(enriched, demo_fabrik_dir, force=False):
    """enriched: Liste {candidate, enrichment}. Schreibt Configs, überspringt
    bestehende (außer force). Gibt Liste der geschriebenen Slugs zurück."""
    cfg_dir = os.path.join(demo_fabrik_dir, "configs")
    os.makedirs(cfg_dir, exist_ok=True)
    written = []
    for item in enriched:
        cfg = build_config(item["candidate"], item.get("enrichment") or {})
        path = os.path.join(cfg_dir, cfg["slug"] + ".json")
        if os.path.exists(path) and not force:
            continue
        _write_json_atomic(path, cfg)
        written.append(cfg["slug"])
    return written


def _run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def verify_url(url, timeout=15):
    """True, wenn die URL mit HTTP 200 antwortet."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def cmd_select(args):
    leads = _load_json(args.leads)
    cands = select_candidates(leads, require_social=not args.no_require_social,
                              include_done=args.include_done)
    print(json.dumps(cands, ensure_ascii=False, indent=2))


def cmd_build(args):
    enriched = _load_json(args.enriched)
    written = write_configs(enriched, args.demo_fabrik, force=args.force)
    urls = {}
    if not args.no_deploy:
        gen = _run(["python3", "generate.py", "--all"], cwd=args.demo_fabrik)
        if gen.returncode != 0:
            sys.exit("FEHLER generate.py:\n" + gen.stderr)
        dep = _run([os.path.expanduser("~/.npm-global/bin/netlify"),
                    "deploy", "--prod", "--dir", "demos"], cwd=args.demo_fabrik)
        if dep.returncode != 0:
            sys.exit("FEHLER netlify deploy:\n" + dep.stderr)
    for item in enriched:
        slug = item["candidate"]["slug"]
        url = f"{args.base_url}/{slug}/"
        urls[item["candidate"]["company"]] = {"slug": slug, "url": url,
                                              "ok": verify_url(url) if not args.no_deploy else None}
    print(json.dumps({"written": written, "demos": urls}, ensure_ascii=False, indent=2))


def cmd_write_back(args):
    leads = _load_json(args.leads)
    mapping = _load_json(args.map)  # {company: url}
    hits = sum(update_lead_demo_url(leads, company, url) for company, url in mapping.items())
    _write_json_atomic(args.leads, leads)
    print(f"{hits} Lead(s) mit demoUrl aktualisiert.")


def main(argv=None):
    p = argparse.ArgumentParser(description="pitch-agent Pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("select")
    s.add_argument("--leads", required=True)
    s.add_argument("--no-require-social", action="store_true")
    s.add_argument("--include-done", action="store_true")
    s.set_defaults(func=cmd_select)

    b = sub.add_parser("build")
    b.add_argument("--enriched", required=True)
    b.add_argument("--demo-fabrik", required=True)
    b.add_argument("--force", action="store_true")
    b.add_argument("--no-deploy", action="store_true")
    b.add_argument("--base-url", default=DEFAULT_BASE_URL)
    b.set_defaults(func=cmd_build)

    w = sub.add_parser("write-back")
    w.add_argument("--leads", required=True)
    w.add_argument("--map", required=True)
    w.set_defaults(func=cmd_write_back)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_demo_pipeline -v`
Expected: PASS (alle Klassen grün).

- [ ] **Step 5: Commit**

```bash
git add scripts/demo_pipeline.py tests/test_demo_pipeline.py
git commit -m "feat: CLI-Subcommands select/build/write-back + write_configs"
git push origin main
```

---

### Task 6: Orchestrator-Skill (`skills/pitch-agent/SKILL.md`)

**Files:**
- Create: `skills/pitch-agent/SKILL.md`

**Interfaces:**
- Consumes: `demo_pipeline.py` CLI (`select`, `build`, `write-back`), Haiku-Subagenten.
- Produces: der `/pitch-agent`-Ablauf. Kein automatisierter Test (Prosa/Orchestrierung); Validierung durch manuellen Testlauf in Task 9 (Demo-Modus).

- [ ] **Step 1: SKILL.md schreiben**

Inhalt (vollständig), mit Platzhaltern `{{PITCH_AGENT_DIR}}`, `{{DEMO_FABRIK_DIR}}`, `{{LEADS_JSON}}`:

````markdown
---
name: pitch-agent
description: Erzeugt aus einer vorhandenen leads.json pro passendem Lead (kein Chatbot + Social-Profil vorhanden) automatisch eine live deployte, personalisierte Chatbot-Demo und einen fertigen Outreach-DM-Entwurf. Nutze diesen Skill wenn der User aus gefundenen Leads Demos + Outreach bauen will oder /pitch-agent aufruft. Vorbedingung: /lead-finder wurde gelaufen (leads.json gefüllt).
---

# pitch-agent — Lead → Demo → Deploy → Outreach

Setzt auf einer vorhandenen `leads.json` auf. Baut pro passendem Lead eine personalisierte
Chatbot-Demo (über `~/demo-fabrik`) und schreibt einen fertigen Outreach-DM-Entwurf.
**Kein Auto-Versand.** Nichts erfinden — Angaben stammen aus echter Website oder Fallback.

## Pfade (beim Installieren durch INSTALL.md gesetzt)
- Repo/Script: `{{PITCH_AGENT_DIR}}/scripts/demo_pipeline.py`
- Demo-Fabrik: `{{DEMO_FABRIK_DIR}}`
- Leads: `{{LEADS_JSON}}`

## Ablauf

### Schritt 1: Kandidaten wählen
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/demo_pipeline.py select --leads {{LEADS_JSON}} > /tmp/pitch-candidates.json
```
Kandidaten = status `new`, kein Chatbot, Social-Profil vorhanden, noch keine `demoUrl`.
Zeige dem User die Anzahl und die Namen. Keine Kandidaten → ehrlich sagen und stoppen.

### Schritt 2: Websites anreichern (Haiku-Subagenten, parallel)
Kandidaten mit `website != null` in Batches à ~6 aufteilen, pro Batch EIN Subagent,
alle Batches parallel in einem Block, `model: "haiku"`. Prompt-Vorlage:

```
Du besuchst Handwerker-Websites und extrahierst Fakten für eine Chatbot-Demo.
Für jede URL unten:
1. Lade Startseite + ggf. Leistungen/Impressum (max. 2 Seiten). Fehler/Timeout: alle Felder null.
2. gewerk: das Handwerk in 1-3 Wörtern (z.B. "Elektrotechnik", "Sanitär & Heizung").
3. stadt: Ort aus Impressum/Kontakt.
4. leistungen: 3-6 echte Leistungen, kommagetrennt, NUR was auf der Seite steht.
5. oeffnungszeiten: falls angegeben (z.B. "Mo-Fr 8-16 Uhr"), sonst null.
6. farbe: dominante Markenfarbe als Hex (#RRGGBB) aus Header/Logo/Buttons, sonst null.
REGELN: Nichts erfinden. Was nicht auf der Seite steht, ist null.
Antworte NUR mit JSON-Array:
[{"company":"...","gewerk":"...","stadt":"...","leistungen":"...","oeffnungszeiten":"...","farbe":"#..."}]

URLs: [Liste: company | website]
```

Für Kandidaten OHNE Website: keine Anreicherung, leeres `enrichment: {}` (Fallbacks greifen).
`faq` optional selbst ergänzen: 1 trade-typischer Satz, geerdet in den gescrapten Leistungen.

Ergebnisse zu `/tmp/pitch-enriched.json` zusammenführen, Format:
`[{"candidate": <Kandidat aus Schritt 1>, "enrichment": {gewerk,stadt,leistungen,oeffnungszeiten,farbe,faq}}]`

### Schritt 3: Bauen + Deployen + Verifizieren
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/demo_pipeline.py build \
  --enriched /tmp/pitch-enriched.json --demo-fabrik {{DEMO_FABRIK_DIR}}
```
Gibt `{written:[...], demos:{company:{slug,url,ok}}}` aus. `ok:false` = Demo lädt nicht →
im Summary rot markieren, nicht verschweigen.

### Schritt 4: Demo-URLs zurückschreiben
Aus der `demos`-Ausgabe eine `{company: url}`-Map nach `/tmp/pitch-map.json` schreiben, dann:
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/demo_pipeline.py write-back \
  --leads {{LEADS_JSON}} --map /tmp/pitch-map.json
```

### Schritt 5: Outreach-Texte (Haiku-Subagenten, parallel)
Pro Kandidat EIN kurzer DM-Entwurf. Batches à ~6, parallel, `model: "haiku"`. Prompt:

```
Schreib eine kurze, persönliche Erstkontakt-DM (Facebook/Instagram) an einen Handwerksbetrieb.
Kanal: Social-DM. Ton: locker-professionell, du-Form, kein Marketing-Sprech, max. 4 Sätze.
Inhalt: Betrieb beim Namen nennen, die konkrete Schwäche aufgreifen (aus "problem"),
die persönliche Demo verlinken, weiche Frage zum Anschauen. Nichts erfinden.
Gib NUR den Nachrichtentext.

Betrieb: [company] | Problem: [problem] | Demo: [demoUrl] | Kanal: [facebook oder instagram]
```

Alle Texte sammeln und schreiben nach `{{DEMO_FABRIK_DIR}}/outreach/<YYYY-MM-DD>.md`
(pro Betrieb: Überschrift, Kanal-Link, Demo-Link, Nachrichtentext).

### Schritt 6: Zusammenfassung
```
✅ pitch-agent fertig
- Kandidaten: N (kein Chatbot + Social)
- Angereichert von Website: A | Fallback (keine/kaputte Website): B
- Demos gebaut & deployt: K (davon OK/HTTP 200: K')
- Outreach-Entwürfe: → {{DEMO_FABRIK_DIR}}/outreach/<datum>.md
🎯 Tabelle: Betrieb | Demo-URL | Kanal | Status(ok?)
Nächster Schritt: Outreach-Texte durchlesen und selbst versenden.
```

## Gesetze (nicht verhandelbar)
1. **Nichts erfinden.** Jede Betriebs-Angabe aus echter Website oder dokumentiertem Fallback.
2. **Kein Auto-Versand.** Outreach ist immer nur Entwurf zum Durchlesen.
3. **Kein Überschreiben.** Bestehende Configs/Demos bleiben (nur mit `--force`).
4. **Ehrliche Unsicherheit.** Kaputte Website/fehlende Daten offen markieren, nicht kaschieren.
5. **Unabhängige Schritte parallel.** Anreicherung und Outreach als parallele Subagenten.
````

- [ ] **Step 2: Manuelle Validierung (Platzhalter & Struktur)**

Run: `grep -c "{{" skills/pitch-agent/SKILL.md`
Expected: > 0 (Platzhalter vorhanden, werden erst bei INSTALL ersetzt).
Sichtprüfung: Frontmatter `name: pitch-agent` + `description` vorhanden, 6 Schritte + Gesetze.

- [ ] **Step 3: Commit**

```bash
git add skills/pitch-agent/SKILL.md
git commit -m "feat: pitch-agent SKILL.md (6-Stufen-Orchestrator + Subagenten-Prompts)"
git push origin main
```

---

### Task 7: INSTALL.md (an Claude adressiert)

**Files:**
- Create: `INSTALL.md`

- [ ] **Step 1: INSTALL.md schreiben**

```markdown
# INSTALL.md — Anleitung für Claude Code

> **An Claude:** Diese Datei ist an dich adressiert. Dein User will den pitch-agent
> einrichten. Erkläre jeden Schritt kurz, BEVOR du ihn ausführst. Brich sauber ab
> und erkläre das Problem, wenn eine Voraussetzung fehlt.

## Schritt 1: Voraussetzungen prüfen

    python3 --version
    test -f ~/demo-fabrik/generate.py && echo "demo-fabrik OK" || echo "demo-fabrik FEHLT"
    ls ~/.npm-global/bin/netlify >/dev/null 2>&1 && echo "netlify OK" || echo "netlify FEHLT"
    test -f ~/.claude/agency-data/leads.json && echo "leads.json OK" || echo "leads.json FEHLT"

- `~/demo-fabrik` fehlt → der pitch-agent braucht die Demo-Fabrik (generate.py + template.html +
  konfiguriertes Netlify). Ohne sie kann er keine Demos bauen — mit dem User klären.
- `leads.json` fehlt/leer → zuerst `/lead-finder <PLZ>` laufen lassen (Vorbedingung).
- `netlify` fehlt → `npm install -g netlify-cli` und `netlify login` (mit dem User).

## Schritt 2: Skill installieren (mit Platzhalter-Ersetzung + Kollisions-Check)

    PITCH_AGENT_DIR="$(pwd)"                     # Repo-Wurzel (dieser Klon)
    DEMO_FABRIK_DIR="$HOME/demo-fabrik"
    LEADS_JSON="$HOME/.claude/agency-data/leads.json"

    ls ~/.claude/skills/pitch-agent/SKILL.md 2>/dev/null && echo "ACHTUNG: existiert schon — User fragen!"

    mkdir -p ~/.claude/skills/pitch-agent
    sed -e "s|{{PITCH_AGENT_DIR}}|$PITCH_AGENT_DIR|g" \
        -e "s|{{DEMO_FABRIK_DIR}}|$DEMO_FABRIK_DIR|g" \
        -e "s|{{LEADS_JSON}}|$LEADS_JSON|g" \
        skills/pitch-agent/SKILL.md > ~/.claude/skills/pitch-agent/SKILL.md

    grep -L "{{" ~/.claude/skills/pitch-agent/SKILL.md   # muss die Datei listen = kein Platzhalter mehr

Der letzte Befehl muss die Datei ausgeben (= alle Platzhalter ersetzt). Wenn nicht: prüfen.

## Schritt 3: Tests laufen lassen (Vertrauen)

    python3 -m unittest discover -s tests -v

Alle grün → der deterministische Kern funktioniert.

## Schritt 4: Erste Nutzung erklären

- Vorbedingung: `/lead-finder <PLZ>` füllt `leads.json`.
- Dann: `/pitch-agent` → wählt Kandidaten (kein Chatbot + Social), baut + deployt Demos,
  schreibt Outreach-Entwürfe nach `~/demo-fabrik/outreach/<datum>.md`.
- **Kein Auto-Versand:** die Outreach-Texte liest der User selbst durch und verschickt sie.
```

- [ ] **Step 2: Commit**

```bash
git add INSTALL.md
git commit -m "docs: INSTALL.md (an Claude adressiert, Platzhalter-Ersetzung)"
git push origin main
```

---

### Task 8: README anreichern + LICENSE

**Files:**
- Modify: `README.md`
- Create: `LICENSE`

- [ ] **Step 1: README.md füllen**

Die Challenge-Template-Abschnitte ausfüllen und nach Referenz-Vorbild anreichern:

```markdown
# pitch-agent — vom Lead zur fertigen Demo + Outreach

## Das Problem

Wer Handwerksbetriebe als Kunden für KI-Chatbots gewinnen will, muss pro Lead eine
personalisierte Demo bauen und eine Nachricht schreiben. Das kostet je Lead viele Minuten
Handarbeit — Website lesen, Infos abtippen, Demo bauen, deployen, Text formulieren — und
skaliert nicht. Ergebnis: viele halbfertige Leads, wenige echte Demos.

## Was der Agent macht

Input: eine vorhandene `leads.json` (aus dem Lead-Finder). Der Agent

1. **wählt** Leads ohne Chatbot, die ein Social-Profil haben (Kanal für die DM),
2. **liest** deren echte Website und zieht Leistungen, Ort, Öffnungszeiten und Markenfarbe,
3. **baut** daraus eine personalisierte Chatbot-Demo und **deployt** sie live,
4. **prüft** jede Demo-URL (HTTP 200),
5. **schreibt** einen fertigen, persönlichen Outreach-DM-Entwurf mit dem Demo-Link,
6. **fasst** alles in einer Tabelle zusammen.

Ergebnis: pro Lead ein Demo-Link + ein Nachrichtentext — zum Durchlesen und Senden.
**Kein Auto-Versand.**

## Stack

- [x] Claude Code (Agent / Skills)
- [ ] n8n
- [x] Sonstiges: Python 3 (stdlib-only), bestehende „demo-fabrik" (generate.py + Netlify)

## Voraussetzungen & Kosten

| Was | Kosten |
|---|---|
| Claude Code | Abo |
| „demo-fabrik" + Netlify | Netlify Free-Tier reicht |
| Lead-Suche (Vorbedingung, Lead-Finder) | Apify-Scrape, ~Cent pro PLZ-Lauf |
| Python-Deps | keine (nur Standardbibliothek) |

## Setup

Siehe **[INSTALL.md](INSTALL.md)** — an Claude adressiert. Kurz:

    Klone dieses Repo und lies die INSTALL.md — sie ist an dich adressiert. Prüfe meine
    Voraussetzungen (demo-fabrik, netlify, leads.json), installiere den pitch-agent-Skill
    global mit Platzhalter-Ersetzung und lass die Tests laufen. Erkläre jeden Schritt kurz,
    bevor du ihn ausführst.

## Was während der Challenge entstanden ist

- **Vorher schon da:** Lead-Finder (Finden/Priorisieren) und die demo-fabrik (generate.py +
  Netlify-Deploy).
- **Neu in der Challenge:** der pitch-agent — Website-Anreicherung, automatisches Bauen **und**
  Deployen, Deploy-Verifikation, Demo-URL-Rückschreiben und personalisierter Outreach-Entwurf.

## Grenzen (ehrlich)

- Für deutsche Handwerks-Leads gedacht.
- Markenfarbe wird best-effort erkannt; klappt das nicht, Standard-Orange.
- Kein Auto-Versand — Outreach ist immer nur ein Entwurf.
- Baut auf einer vom Lead-Finder gefüllten `leads.json` auf (findet nicht selbst).

## Was drin ist

    skills/pitch-agent/SKILL.md   Orchestrator (6 Stufen + Subagenten-Prompts)
    scripts/demo_pipeline.py      Deterministischer Kern (stdlib-only)
    tests/                        unittest-Tests + Fake-Fixtures
    INSTALL.md                    Installation, an Claude adressiert

---

**Demo-Video:** [Link folgt]

*SKAILE Academy Building Challenge — Juli 2026*
```

- [ ] **Step 2: LICENSE anlegen (MIT)**

Standard-MIT-Text mit `Copyright (c) 2026 Alexander Tilind`.

- [ ] **Step 3: Commit**

```bash
git add README.md LICENSE
git commit -m "docs: README angereichert + MIT-LICENSE"
git push origin main
```

---

### Task 9: End-to-End-Trockenlauf (Demo-Modus, ohne Deploy)

**Files:** keine (Validierung).

- [ ] **Step 1: select gegen echte leads.json**

Run: `python3 scripts/demo_pipeline.py select --leads ~/.claude/agency-data/leads.json`
Expected: JSON-Liste echter Kandidaten (kein Chatbot + Social). Anzahl plausibel (>0).

- [ ] **Step 2: build im Trockenlauf (kein Deploy, Wegwerf-demo-fabrik)**

Enriched-Testdatei aus 1 echtem Kandidaten bauen (enrichment leer), gegen ein Temp-Verzeichnis
mit Kopie von generate.py/template.html, mit `--no-deploy`:

Run: `python3 scripts/demo_pipeline.py build --enriched /tmp/pitch-enriched.json --demo-fabrik /tmp/df-test --no-deploy`
Expected: `written`-Liste enthält den Slug; `demos`-Map mit `ok:null` (kein Deploy). Config-Datei liegt in `/tmp/df-test/configs/`.

- [ ] **Step 3: Alle Tests**

Run: `python3 -m unittest discover -s tests -v`
Expected: alle grün.

- [ ] **Step 4: Commit (Abschluss)**

```bash
git add -A
git commit -m "chore: E2E-Trockenlauf verifiziert (select + build --no-deploy)"
git push origin main
```

---

## Hinweise zur Ausführung

- Der echte Live-Deploy (`build` ohne `--no-deploy`) und die Subagenten-Stufen (Anreicherung,
  Outreach) werden im echten `/pitch-agent`-Lauf getestet — das ist zugleich die Aufnahme fürs
  Abgabe-Video (Demo-Modus: von vorhandener leads.json starten).
- Reihenfolge strikt Task 1 → 9; jeder Task endet grün + committet + gepusht.
