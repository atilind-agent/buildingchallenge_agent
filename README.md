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
