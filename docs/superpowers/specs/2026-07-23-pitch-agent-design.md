# Design: pitch-agent

**Datum:** 2026-07-23
**Kontext:** SKAILE Building Challenge #2 — ein Agent, der ein echtes, wiederkehrendes Problem löst.
**Repo:** `buildingchallenge_agent` (öffentlich)

## Das Problem

Der bestehende `lead-finder`-Skill findet Handwerksbetriebe per PLZ und legt Demo-Configs
in `~/demo-fabrik/configs/` an — **aber nur mit Platzhaltern** (Leistungen, Öffnungszeiten,
Markenfarbe, FAQ bleiben Defaults). Das Anreichern mit echten Infos, das Bauen der Demo,
das Deployen und das Schreiben eines Outreach-Textes passiert danach **pro Lead von Hand**.
Folge: 12 Configs liegen da, aber nur 3 fertige Demos. Jeder Lead kostet manuelle Minuten,
die sich nicht skalieren lassen. Genau diese Lücke schließt `pitch-agent`.

## Was der Agent macht

**Input:** die bereits gefüllte `leads.json` (Vorbedingung: `/lead-finder` wurde gelaufen),
optional auf eine PLZ/Quelle eingegrenzt.
**Output:** pro passendem Lead eine **live deployte, personalisierte Chatbot-Demo** plus einen
**fertigen Outreach-DM-Entwurf** mit dem Demo-Link — zum Prüfen und Senden, **ohne Auto-Versand**.

**Filter (bewusstes Kriterium):** Bearbeitet werden nur Leads, die **keinen Chatbot** haben
**und** ein **Social-Media-Profil** (Facebook/Instagram) besitzen. Grund: Der Outreach-Kanal ist
die Social-DM (Cold-Mail ist in DE nach §7 UWG heikel). Kein Social-Profil = kein Kanal = übersprungen.

## Abgrenzung (was ist NEU in der Challenge)

- **Existierte vorher:** `lead-finder`-Skill (Finden/Priorisieren), `~/demo-fabrik/` mit
  `generate.py` + `template.html` + Netlify-Deploy.
- **Neu in der Challenge:** der `pitch-agent` — die Pipeline vom Lead zum versandfertigen Pitch:
  Website-Anreicherung mit echten Inhalten, automatisches Bauen **und** Deployen, Deploy-Verifikation
  und personalisierter Outreach-Text. Das ist die bewertete Arbeit.

Der neue Agent setzt bewusst **auf einer vorhandenen `leads.json` auf** (scharfe Grenze:
`pitch-agent` = genau der Delta-Schritt), statt `lead-finder` intern zu duplizieren.

## Architektur — 6 Stufen

| Stufe | Wer | Was |
|---|---|---|
| 1. Finden (Vorbedingung) | bestehender `lead-finder` | PLZ → Apify → `leads.json`. Nicht Teil dieses Agenten, nur Input. |
| 2. Auswählen | `demo_pipeline.py select` | `leads.json` filtern: kein Chat-Widget **und** Social-Profil vorhanden → Kandidaten (JSON). |
| 3. Anreichern | Haiku-Subagenten (parallel) | Echte Website scrapen → `leistungen`, `oeffnungszeiten`, `farbe` (Markenfarbe best-effort). **Nichts erfinden.** |
| 4. Bauen + Deployen | `demo_pipeline.py build` | Config schreiben (Maps + gescrapte Daten + Defaults, kein Überschreiben), `generate.py`, `netlify deploy`, Demo-URL per curl auf HTTP 200 prüfen. |
| 5. Outreach | Haiku-Subagenten (parallel) | Pro Lead personalisierte DM (Betriebsname, konkrete Schwäche, Demo-Link), deutsch, kurz, geerdet in echten Lead-Daten. |
| 6. Zusammenfassung | Skill (`SKILL.md`) | Tabelle Lead → Demo-URL → Outreach-Status, mit Zahlen. |

### Zwei Bausteine im Repo

- **`skills/pitch-agent/SKILL.md`** — das Orchestrator-Gehirn (Skill-Trigger + `/pitch-agent`).
  Steuert den Fluss, dispatcht die Haiku-Subagenten für die „fuzzy" Stufen (3 + 5). Baut auf dem
  Muster des bestehenden `lead-finder`-Skills auf. Diszipliniertes Frontmatter
  (name/description/model/effort) + ein kurzer „Gesetze"-Block, geerdet in der Denklogik
  (Vorbild: `agent/video-cutter.md` aus Sebastians Repo mit seinen „10 Gesetzen").
- **`scripts/demo_pipeline.py`** — die **deterministische** Glue-Logik: Filtern (`select`),
  Config-Merge mit Slug-Generierung + Überschreibschutz, Build, Deploy, Deploy-Verifikation
  (`build`). **Nur Python-Stdlib, keine externen Deps** (bewusst — keine `requirements.txt` nötig).
  Das ist der testbare, stabile Kern (Bewertungskriterium „stabil & sauber").

### Warum diese Aufteilung
Deterministische Datei-/Deploy-Logik gehört in ein testbares Script; sprachlich-unsichere
Arbeit (Website-Inhalte lesen, Text schreiben) gehört zu LLM-Subagenten. Klare Grenze,
jeder Teil einzeln verständlich und testbar.

## Datenfluss & Privacy (Repo ist öffentlich!)

- **Kundendaten** (`leads.json`, Configs, gebaute Demos, Outreach-Texte) bleiben in
  `~/demo-fabrik/` bzw. `~/.claude/agency-data/` — **kommen NIE ins öffentliche Repo.**
- **Das Repo enthält nur den Agenten:** `SKILL.md`, `demo_pipeline.py`, Tests, `README.md`,
  `INSTALL.md` und **Fixtures mit erfundenen Beispiel-Betrieben** (keine echten Kunden).
- Outreach-Texte → `~/demo-fabrik/outreach/<datum>.md` (lokal, zum Durchlesen vor dem Senden).

## Konfigurations-Felder (Ziel der Anreicherung)

Aus `~/demo-fabrik/generate.py` (bestehendes Schema):

| Feld | Quelle |
|---|---|
| `slug`, `name` | Pflicht, aus Lead (Name → Slug) |
| `gewerk` | Maps `categoryName` (aus leads.json ableitbar) |
| `stadt` | Adresse aus Lead |
| `notfall_nummer` | echte Telefonnummer aus Lead |
| `leistungen` | **Stufe 3: von echter Website** |
| `oeffnungszeiten` | **Stufe 3: von echter Website** (sonst Default) |
| `farbe` | **Stufe 3: Markenfarbe best-effort**, Fallback `#F97316` |
| `faq` | trade-typische Fragen, Antworten geerdet in gescrapten Leistungen |
| `cal_link`, `webhook` | Defaults aus generate.py |

## Fehlerbehandlung

- Website nicht erreichbar / keine Inhalte → Lead nutzt Defaults, wird markiert, Pipeline bricht **nicht** ab.
- `netlify deploy` schlägt fehl → Fehler klar melden, gebaute Configs bleiben erhalten (idempotent erneut deploybar).
- Deploy-Verifikation: jede Demo-URL per curl auf HTTP 200 prüfen; nicht-200 im Summary rot markieren.
- Bestehende Config in `~/demo-fabrik/configs/` wird **nicht überschrieben** (nur mit explizitem `--force`).

## Testing (Bewertungskriterium)

`demo_pipeline.py` bekommt Unit-Tests gegen eine **Fake-Fixture-`leads.json`** (keine echten Kunden):
- `select`: Filter-Logik (kein Chat **und** Social → Kandidat; sonst nicht).
- Config-Merge: Slug-Generierung korrekt, Maps+Scrape+Defaults zusammengeführt, Überschreibschutz greift.

Die scraping-/outreach-Stufen (LLM/Subagenten) sind nicht deterministisch unit-testbar; getestet
wird die deterministische Glue-Logik.

## Demo-Modus fürs Abgabe-Video

Der Agent startet von einer schon gefüllten `leads.json` (Stufe 1 ist Vorbedingung), also läuft das
2–3-Min-Video **nicht** durch den langen Apify-Scrape. Ablauf im Video: `/pitch-agent` → 3 Kandidaten
→ 3 live Demos + 3 Outreach-Texte. Ein Durchlauf, ungeschnitten.

## Repo-Deliverables & Doku (nach Vorbild `claude-video-cutter`)

Sebastians Referenz-Repo zeigt, was ein „richtig gut gemachtes" Challenge-Repo ausmacht.
Übernommen wird:

### `INSTALL.md` — an Claude adressiert (wie `START.md`)
Schritt für Schritt, jeder Schritt kurz erklärt BEVOR er ausgeführt wird:
1. **Voraussetzungen prüfen:** `~/demo-fabrik` mit `generate.py` + `template.html` vorhanden,
   `netlify`-CLI eingeloggt (Site-ID in `.netlify/state.json`), Apify-Token in `~/.mcp.json`,
   `leads.json` unter `~/.claude/agency-data/`.
2. **Skill global installieren mit Kollisions-Check:** existiert schon `~/.claude/skills/pitch-agent`?
   → User fragen. Platzhalter ersetzen (siehe unten), dann nach `~/.claude/skills/` kopieren.
3. **Erste Nutzung erklären:** `/lead-finder <PLZ>` (Vorbedingung) → `/pitch-agent` → live Demos + Outreach.

### Platzhalter-Pattern (Teilbarkeit)
Skill + Script enthalten `{{DEMO_FABRIK_DIR}}` und `{{LEADS_JSON}}`. `INSTALL.md` ersetzt sie
per `sed` durch die echten absoluten Pfade beim Installieren (Vorbild: `{{CUTTER_DIR}}`).
So ist der Agent nicht auf die Pfade des Autors festgenagelt.

### `README.md` — Challenge-Template-Abschnitte, angereichert
Die vom Template geforderten Abschnitte bleiben (Das Problem, Was der Agent macht, Stack, Setup,
Was während der Challenge entstanden ist, Learnings, Demo-Video). Angereichert nach Referenz-Vorbild:
- „Was der Agent macht" als **nummerierte 1–6-Liste** (wie Referenz)
- **Voraussetzungen** + **Kosten-Tabelle** (Apify-Scrape-Kosten, Netlify Free-Tier)
- **„Installation (ein Prompt)"** — ein Copy-Paste-Prompt, der Claude die ganze Einrichtung machen lässt
- **„Was drin ist"** — Datei-Baum
- **„Grenzen (ehrlich)"** — z.B. Markenfarbe best-effort, nur deutsche Handwerks-Leads, kein Auto-Versand
- „Setup" verweist auf `INSTALL.md`

### `LICENSE` — MIT (wie Referenz)

## Repo-Struktur (nur der Agent, keine Kundendaten)

```
buildingchallenge_agent/
├── README.md                       Challenge-README (angereichert)
├── INSTALL.md                      An Claude adressiert, Schritt für Schritt
├── LICENSE                         MIT
├── ABGABE.md                       (aus Template, am Ende ausgefüllt)
├── skills/pitch-agent/SKILL.md     Das Orchestrator-Gehirn
├── scripts/demo_pipeline.py        Deterministische Glue-Logik (stdlib-only)
├── tests/
│   ├── fixtures/leads.sample.json  Fake-Betriebe (KEINE echten Kunden)
│   └── test_demo_pipeline.py       Unit-Tests für select + config-merge
└── docs/superpowers/specs/         Dieses Design-Dokument (Build Journal)
```

## Nicht im Scope (YAGNI)

- Kein Auto-Versand der Outreach-DMs (nur Entwurf).
- Kein erneutes Finden/Scrapen von Google Maps (macht `lead-finder`).
- Kein Batch-Scheduling / Cron — manueller Aufruf.
- Keine Markenfarb-Perfektion — best-effort mit Fallback reicht.
