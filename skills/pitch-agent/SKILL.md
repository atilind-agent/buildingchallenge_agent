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

## v2 — Closing-Loop (4 Phasen)

`/pitch-agent` ohne Argument = **Acquire** (oben). Mit Phasenwort: `advance`, `react …`, `review`.
Engine: `python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py`. Einmalig zuerst:
`… migrate --leads {{LEADS_JSON}}` (idempotent, normalisiert Status + initialisiert Felder).

### Phase 2: Advance (fällige Follow-ups)
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py due --leads {{LEADS_JSON}} > /tmp/pitch-due.json
```
Keine fälligen Leads → sagen und stoppen. Sonst pro fälligem Lead EIN Nudge-Entwurf via Haiku-
Subagenten (parallel, `model: "haiku"`), Ton eskaliert mit `touchCount` (#2 freundliche Erinnerung,
#3 kurz mit Mehrwert, #4 letzte weiche Meldung). Prompt bekommt `company, problem, demoUrl,
touchCount`. Nichts erfinden. Entwürfe dem User zeigen. Erst NACH Senden (User bestätigt):
`{company:true}`-Map nach `/tmp/pitch-sent.json`, dann
`… advance-apply --leads {{LEADS_JSON}} --sent /tmp/pitch-sent.json`.

### Phase 3: React (Antwort verarbeiten)
User meldet: „Lead X hat geantwortet: «Text»". Haiku klassifiziert in genau eine Klasse
`interessiert | frage | einwand | später | nein` und entwirft die Reaktion. Klasse unklar →
User fragen, nicht raten. Dann:
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py react-apply --leads {{LEADS_JSON}} \
  --company "X" --reply-class <klasse> [--snooze YYYY-MM-DD] --reply-text "«Text»"
```
(`später` braucht `--snooze`.) Reaktion dem User zum Senden zeigen — kein Auto-Versand.

### Phase 4: Review (CRM-QA)
```bash
python3 {{PITCH_AGENT_DIR}}/scripts/pipeline_engine.py qa --leads {{LEADS_JSON}} --repair
```
Druckt `status/warnungen/graufaelle/aktion_noetig/aufgeben_kandidaten`. `--repair` fixt Triviales
(followUpDue, fehlende nextAction). Graufälle + „Aktion nötig" (REPLIED) dem User auflisten,
nichts verschweigen.
