#!/usr/bin/env python3
"""pitch-agent: deterministischer Kern.

Liest leads.json, wählt Kandidaten (kein Chatbot + Social vorhanden),
baut demo-fabrik-Configs und schreibt Demo-URLs nach leads.json zurück.
Nur Standardbibliothek. Tests: python3 -m unittest discover.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

DEFAULT_BASE_URL = "https://demos-tilind.netlify.app"

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


def update_lead_demo_url(leads, company, url):
    """Setzt demoUrl beim Lead mit passendem company. True wenn getroffen."""
    for lead in leads:
        if lead.get("company") == company:
            lead["demoUrl"] = url
            return True
    return False


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
