# pitch-agent v2 — Closing-Loop Design

> Baut auf v1 auf (`2026-07-23-pitch-agent-design.md`). v1 endet bei „Outreach-Entwurf
> geschrieben, du sendest selbst". v2 macht daraus den geschlossenen Kreislauf bis zum
> Abschluss — als echtes tägliches Agentur-Tool.

**Datum:** 2026-07-24
**Scope:** Umfang A (On-Demand-Kreislauf, keine neue Infrastruktur).

## Ziel

Ein Claude-Code-Agent, der einen Lead über die ganze Pipeline führt — von der Demo über
personalisierte Follow-ups mit deterministischer Cadence bis zur Antwort-Reaktion und
Abschluss — und dabei nie mehr Handarbeit verlangt als nötig (kein Auto-Versand, du
sendest und meldest Antworten selbst).

## Architektur-Prinzip (dieselbe DNA wie v1)

**Agent = Regie, Code = Kamera.** Ein deterministischer Python-Kern entscheidet **WANN/OB**
ein Lead bewegt wird (Cadence, Stage-Übergänge, Aufgeben-Regel, QA); Haiku-Subagenten
entscheiden **WAS** geschrieben wird (Nudge-Text, Antwort-Reaktion). Alles über der einen
Wahrheit `leads.json`.

## Was schon existiert (reuse map — nicht neu bauen)

- **`~/.claude/agency-data/leads.json`** — alleinige Wahrheit, 89 Leads, reiches CRM-Schema.
  `crm.json` enthält nur `{monthlyGoal}` (Config, kein Lead-Store) → kein Doppel-Speicher.
- **`scripts/demo_pipeline.py`** (v1) — Acquire-Kern `select/build/write-back`, bleibt unverändert.
- **`agency-dashboard/index.html`** — existierendes Kanban über leads.json (Stages inkl.
  `CONTACTED`, `nextAction`, „pipeline"/„kanban"). Wird nur minimal erweitert.
- **demo-fabrik + Netlify** — Demo-Bau/Deploy, unverändert.

## Die 4 Phasen (Subcommands von `/pitch-agent`, je einzeln aufrufbar)

1. **Acquire** — v1-Ablauf unverändert: `select → build/deploy → outreach-Entwurf`. Setzt Lead
   auf `CONTACTED`, `touchCount=1`, `lastTouch=heute`.
2. **Advance** — Cadence-Engine listet fällige `CONTACTED`-Leads (kein Reply, Tage seit
   `lastTouch` ≥ Schwelle) → Haiku entwirft Follow-up-Nudges.
3. **React** — du meldest „Lead X hat geantwortet: «Text»" → Haiku klassifiziert → Engine setzt
   deterministisch die neue Stage → Haiku entwirft die Reaktion.
4. **Review** — Laufzeit-CRM-QA prüft die ganze Pipeline auf Widersprüche, repariert Triviales,
   flaggt Graufälle + Zusammenfassung + Dashboard offen.

## Datenmodell (leads.json erweitern, nichts Paralleles)

- **`status` = die Stage.** Kanonisch: `NEW → CONTACTED → REPLIED → IN_TALKS → WON | LOST`.
  Bestehende `NEW/new`-Mischung wird per idempotentem `migrate` normalisiert.
- **Neue Felder:**
  - `lastTouch` — ISO-Datum des letzten Ausgangs (z. B. `"2026-07-24"`), Basis der Cadence.
  - `touchCount` — Anzahl gesendeter Nachrichten (int, für Aufgeben-Regel).
  - `followUpDue` — berechneter ISO-Cache (z. B. `"2026-07-27"`), damit das Dashboard „fällig/
    überfällig" anzeigen kann. **Einziger Schreiber ist die Engine**, die ihn bei jedem Lauf neu
    rechnet (Cache, keine zweite Wahrheit).
  - `snoozeUntil` — optionales ISO-Datum; bis dahin nicht fällig (für Antwort „später").
- **Wiederverwendet:** `nextAction` (Engine schreibt Empfehlung rein, z. B. „Follow-up #2 fällig
  seit 24.07."), `notes` (append-only Historie: Kontakte + Antworten), `demoUrl`.

Beispiel-Record (synthetisch):

```json
{
  "company": "Muster Elektro", "status": "CONTACTED",
  "demoUrl": "https://demos-tilind.netlify.app/muster-elektro/",
  "lastTouch": "2026-07-24", "touchCount": 2,
  "followUpDue": "2026-07-31", "snoozeUntil": null,
  "nextAction": "Follow-up #3 fällig am 31.07.",
  "notes": ["2026-07-20 Erst-DM (FB)", "2026-07-24 Nudge #2 (FB)"]
}
```

## Deterministische Engine — `scripts/pipeline_engine.py` (stdlib-only, unit-getestet)

### Stage-Semantik (wer ist am Zug)

- `CONTACTED` = **Ball bei ihnen** → Cadence-Nudges greifen.
- `REPLIED` = **Ball bei uns** → kein Auto-Nudge, erscheint als „Aktion nötig".
- `IN_TALKS` = aktives Gespräch, menschgeführt, keine Auto-Cadence.
- `NEW` = Anfang; `WON` / `LOST` = Endzustände (Engine terminal; manueller Override immer möglich).

### Übergangstabelle (Engine erzwingt genau diese; alles andere = invalider Übergang)

| von | nach | Auslöser |
|---|---|---|
| NEW | CONTACTED | Acquire (braucht `demoUrl`) |
| CONTACTED | CONTACTED | Follow-up-Nudge gesendet (`touchCount++`) |
| CONTACTED | REPLIED | Antwort gemeldet |
| CONTACTED | LOST | Aufgeben-Regel erreicht |
| REPLIED | IN_TALKS | Antwort = interessiert |
| REPLIED | CONTACTED | Antwort = Frage/Einwand (wir antworten) oder „später" (`snoozeUntil`) |
| REPLIED | LOST | Antwort = nein |
| IN_TALKS | WON / LOST | manuell |

### Cadence-Regeln (in `config.json`, jederzeit änderbar)

- Erst-Outreach = touch #1. Fällig danach: **+3 Tage** → Nudge #2, **+7** → Nudge #3, **+14** → Nudge #4.
  (`thresholds = {1: 3, 2: 7, 3: 14}`, Tage seit `lastTouch` je nach aktuellem `touchCount`.)
- **Aufgeben:** `touchCount ≥ 4` ohne Antwort → Engine empfiehlt `LOST` (`maxTouches = 4`).
- `due_for_followup(lead, today)` = `status=="CONTACTED"` UND kein offener Reply UND
  `snoozeUntil` leer/vergangen UND `(today − lastTouch) ≥ thresholds[touchCount]`.

### Reine Funktionen (Interfaces)

- arbeitet auf Lead-Dicts.
- `valid_transition(from_stage, to_stage) -> bool`
- `due_for_followup(lead, today) -> bool`
- `select_due(leads, today) -> list[lead]`  (Advance-Input)
- `apply_reply(lead, reply_class, today, snooze_until=None) -> lead`  (setzt Stage + `nextAction`)
- `mark_sent(lead, today) -> lead`  (`touchCount++`, `lastTouch`, `followUpDue` neu)
- `recompute_due(lead, today) -> lead`  (nur `followUpDue`-Cache)
- `crm_qa(leads, today) -> report`  (siehe unten)

### Laufzeit-CRM-QA (Phase Review; Sebastians Muster: Triviales auto-fixen, Rest flaggen)

- **Struktur:** gültige Stage; `CONTACTED/REPLIED/IN_TALKS/WON` ⇒ hat `demoUrl`; `CONTACTED` ⇒ hat `lastTouch`.
- **Aufgeben-Kandidaten:** `CONTACTED` mit `touchCount ≥ 4` → Graufall „aufgeben?".
- **Ball bei uns:** alle `REPLIED` → „Aktion nötig"-Liste.
- **Waisen:** nicht-terminaler Lead ohne `nextAction`.
- **Auto-Repair:** `followUpDue` neu rechnen, fehlende `nextAction` setzen. Rest → Graufall.
- **Ausgabe:** `PASS / N Warnungen / M Graufälle` (im Review gedruckt, nichts verschwiegen).

## LLM-Stufen (Haiku-Subagenten, wie v1 — die sprachlich-unsicheren Stellen)

- **Advance → Nudge:** pro fälligem Lead ein Entwurf. Prompt bekommt `company, problem, demoUrl,
  touchCount` → Ton eskaliert: #2 freundliche Erinnerung, #3 kurz mit Mehrwert, #4 letzte weiche
  Meldung. Nichts erfinden; Kanal aus dem Social-Profil.
- **React → Klassifikation + Antwort:** Input = eingefügter Antworttext → Haiku liefert
  `{klasse ∈ interessiert|frage|einwand|später|nein, antwort_entwurf}`. **Die Engine macht daraus
  deterministisch den Stage-Move** (`apply_reply`). Ist die Klasse unklar → Haiku sagt das → wir
  fragen den User, statt zu raten (ehrliche Unsicherheit).

## Orchestrator / CLI

- **`demo_pipeline.py`** (v1): `select`, `build`, `write-back` — unverändert.
- **`pipeline_engine.py`** (neu):
  - `migrate --leads <path>` — idempotent: `status` normalisieren, `touchCount=0`, `lastTouch`/
    `followUpDue` initialisieren/backfillen.
  - `due --leads <path> [--today <ISO>]` — druckt fällige Leads (Advance-Input).
  - `advance-apply --leads <path> --sent <map.json> [--today <ISO>]` — nach Senden: `mark_sent`.
  - `react-apply --leads <path> --company <name> --reply-class <klasse> [--snooze <ISO>]` —
    deterministischer Stage-Move + `nextAction`.
  - `qa --leads <path> [--repair] [--today <ISO>]` — CRM-QA-Report, optional Auto-Repair.
- **SKILL** `skills/pitch-agent/SKILL.md`: 4 Phasen-Abschnitte; Aufruf `/pitch-agent` (Acquire
  default) oder mit Phasenwort („advance" / „react …" / „review").

## Dashboard-Anschluss (minimal, bestehendes `index.html`)

- „fällig/überfällig"-Badge aus `followUpDue`.
- Optionaler „Antwort erfassen"-Knopf (setzt `status=REPLIED` + speichert Text in `notes`); die
  React-Phase liest solche Leads auf. Hauptweg bleibt „du meldest es Claude".
- **Planungs-Check (nicht raten):** ob das Dashboard überhaupt zurückschreiben kann — es gibt ein
  `dashboard-server.log`, evtl. lokaler Server. Falls read-only, bleibt der Badge Anzeige-only und
  Reply-Capture läuft ausschließlich über Claude.

## Test-Strategie

- **Engine + QA** (reine Funktionen) → **~25–30 Unit-Tests** (das Qualitäts-Gate):
  Fälligkeit exakt an der Schwelle (Grenzwerte), Aufgeben bei `touchCount==4`, jeder Übergang
  gültig/ungültig, `apply_reply` je Klasse, `snoozeUntil` blockiert Fälligkeit, `migrate` zweimal =
  identisch (Idempotenz), `crm_qa` auf konstruierten Fixtures.
- **LLM-Stufen** → Dry-Run + Sichtprüfung (wie v1), nicht unit-getestet.
- **E2E-Trockenlauf** → `migrate → due → advance-apply → qa` auf einer Fixture, deterministisch
  asserted (kein echter Versand).

## Migration (die 89 bestehenden Leads)

- `status` normalisieren (`NEW/new → NEW`), `touchCount=0`, `lastTouch` wo möglich aus `date`
  backfillen, `followUpDue`/`snoozeUntil` initialisieren.
- Die 9 Leads mit `demoUrl` bleiben `NEW` (Demo bereit, aber noch nicht per DM kontaktiert) —
  Migration markiert nichts fälschlich als `CONTACTED`.
- Idempotent: zweiter Lauf ändert nichts.

## Bewusst weggelassen (YAGNI)

- Kein Auto-Versand (Gesetz), kein DM-Auto-Pull aus FB/IG (brüchig, abgelehnt).
- Kein n8n / kein geplanter Morgen-Job (das ist Umfang B, späterer Nachrüst-Schritt).
- Kein neues Dashboard-Framework — bestehendes `index.html` erweitern.
- Genau 5 Reply-Klassen, keine feinere Sentiment-Analyse.

## Offene Planungs-Checks (in writing-plans klären, nicht raten)

1. Dashboard-Rückschreibpfad (Server vs. read-only) — bestimmt, wie viel „Antwort erfassen"-Knopf
   machbar ist.
2. Exakter Ort/Shape von `config.json` (liegt in `~/.claude/agency-data/config.json`) — Cadence-
   Parameter dort ablegen oder Engine-Defaults + optionaler Override.
3. `lastTouch`-Backfill-Quelle: Feld `date` vs. Datum aus `demo-fabrik/outreach/<datum>.md`.

## Dateistruktur (neu / geändert)

```
scripts/pipeline_engine.py     NEU  — Stage-Maschine + Cadence + CRM-QA (stdlib, getestet)
tests/test_pipeline_engine.py  NEU  — ~25–30 Unit-Tests + Fixtures
tests/fixtures/leads.pipeline.sample.json  NEU — Fake-Leads über alle Stages/Cadence-Fälle
skills/pitch-agent/SKILL.md    GEÄNDERT — 4-Phasen-Orchestrator (Acquire/Advance/React/Review)
scripts/demo_pipeline.py       UNVERÄNDERT (Acquire-Kern)
agency-dashboard/index.html    GEÄNDERT (minimal) — Fällig-Badge, optional Reply-Knopf
README.md / INSTALL.md         GEÄNDERT — v2-Phasen dokumentieren
```
