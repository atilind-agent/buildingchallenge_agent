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
