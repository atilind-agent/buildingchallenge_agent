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
