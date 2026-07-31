[Zurück zu Config](ui.config.de.md)

# AI-Assistant — Handbuch

Fast jeder Config-Editor in OpenForexAI hat oben rechts einen **AI Assistant**-Button, der ein Chat-Fenster öffnet, in dem man Fragen zur gerade bearbeiteten Konfiguration stellen kann — z. B. „warum liefert dieser tool_block keine Daten" oder „wie baue ich einen Session-Filter für die Londoner Session". Jeder dieser Assistenten wird durch eine eigene **Kontext-Datei** gesteuert — eine Markdown-Datei, die dem LLM erklärt, wofür dieser Editor da ist, welche Felder es gibt und worauf zu achten ist. Die Seite **AI-Assistant** ist der Editor für genau diese Kontext-Dateien.

Man landet hier typischerweise nicht, um selbst etwas zu konfigurieren, sondern um den Assistant in einem *anderen* Editor **besser zu machen** — z. B. nachdem er eine Frage falsch oder unvollständig beantwortet hat.

Gespeichert unter `config/llm_contexts/*.md`.

---

## 1. Wie der eingebettete Assistant funktioniert

Wenn man in einem Config-Editor (z. B. Snapshot Config, Decision Prompt, Bridge Tools, Chartshot Config, Entity Config) auf **AI Assistant** klickt, öffnet sich ein Chat-Fenster. Jede Nachricht wird zusammen mit drei Dingen an das LLM geschickt:

1. Der **Kontext-Datei-Inhalt** — das eigentliche „Wissen", was dieser Assistent über den jeweiligen Editor kennt.
2. Der **aktuelle Konfigurationszustand** (`context_data`) — ein JSON-Dump dessen, was gerade im Editor steht, damit sich Fragen wie „warum schlägt dieser Block fehl" auf die echten, aktuellen Werte beziehen.
3. Der bisherige **Gesprächsverlauf** in diesem Chat-Fenster.

Der Chatverlauf bleibt pro Kontext-Datei erhalten, auch wenn das Fenster geschlossen und wieder geöffnet wird — er geht erst beim Neuladen der Seite verloren. **Clear** leert ihn explizit.

**Achtung — Sicherheit:** Der aktuelle Konfigurationszustand (Punkt 2) wird **wörtlich** an das LLM geschickt. Wenn ein Config-Editor sensible Werte enthält (z. B. API-Keys im Klartext statt als `${ENV_VAR}`-Platzhalter), landen diese im Prompt des jeweiligen LLM-Providers. Sensible Werte grundsätzlich über Umgebungsvariablen referenzieren, nicht direkt eintragen — das ist ohnehin die empfohlene Praxis für Modul-Configs, gilt hier aber besonders, weil der Inhalt aktiv an einen externen Dienst gesendet wird.

---

## 2. Welche Kontext-Dateien es gibt

| Datei | Verwendet in |
|---|---|
| `agent_config_assistant.md` | Agent Config |
| `entity_config_assistant.md` | Entity Config, Helper Config |
| `snapshot_config_assistant.md` | Snapshot Config |
| `decision_prompt_assistant.md` | Decision Prompt |
| `bridge_tools_assistant.md` | Bridge Tools |
| `event_routing_assistant.md` | Event Routing |
| `chartshot_config_assistant.md` | Chartshot Config |
| `script_snapshot_transform_context.md` | Transform-Script-Editor (Snapshot Config, Prompt Workbench) |
| `script_snapshot_calculation_context.md` | Calculation-Block-Script-Editor |
| `script_snapshot_assembly_context.md` | Assembly-Transform-Script-Editor |
| `script_decision_prompt_context.md` | Decision-Prompt-Script-Editor |
| `script_decision_selector_context.md` | Decision-Selector-Script-Editor |
| `script_ec_context.md` | Event-Composer-Script-Editor |

Neue `.md`-Dateien, die in `config/llm_contexts/` abgelegt werden, erscheinen automatisch im Dropdown dieser Seite.

---

## 3. Editor-Oberfläche

| Element | Funktion |
|---------|---------|
| **Dateiauswahl-Dropdown** | Wählt, welche Kontext-Datei bearbeitet wird. |
| **Edit / Split / Preview** | Reiner Editor, geteilte Ansicht, oder nur die gerenderte Vorschau. |
| **Save** | Schreibt die Datei zurück. Nur aktiv bei ungespeicherten Änderungen. |

**Empfehlung:** Beim Schreiben immer `Split` verwenden — Markdown-Tabellen und Codeblöcke sehen im rohen Text leicht anders aus, als sie am Ende gerendert werden (und genau die gerenderte Struktur macht sie für ein LLM gut lesbar).

---

## 4. Eine Kontext-Datei gut schreiben

Da der Inhalt direkt dem LLM als Hintergrundwissen übergeben wird, gilt für diese Dateien dasselbe wie für System-Prompts:

- **Konkret bleiben:** Welche Felder gibt es, was bewirken sie, welche Werte sind typisch/gültig.
- **Häufige Fehler benennen:** Wenn Nutzer regelmäßig dieselbe Frage stellen oder denselben Fehler machen, gehört die Antwort/Erklärung in die Kontext-Datei.
- **Nicht zu lang:** Der Inhalt geht bei jeder Chat-Nachricht erneut mit — unnötig lange Dateien verlangsamen und verteuern jede Antwort ohne Mehrwert.
- **Beispiele einbauen:** Ein kurzes Beispiel für einen typischen Konfigurationseintrag hilft dem LLM oft mehr als eine abstrakte Beschreibung.

**Beispiel — schlechter vs. besserer Eintrag** (Ausschnitt aus einer fiktiven `bridge_tools_assistant.md`):

Schlecht (zu abstrakt, kein Beispiel):
> „Das Feld `allowed_tools` steuert, welche Tools freigegeben sind."

Besser (konkret, mit Beispiel und Warnung):
> „Das Feld `allowed_tools` ist eine Liste von Tool-Namen, die dieser Bridge-Eintrag freigibt, z. B. `[\"get_candles\", \"get_account_status\"]`. Ein leeres Array blockiert alle Tools — das ist die häufigste Ursache dafür, dass ein Bridge-Aufruf mit ‚tool not allowed' fehlschlägt, obwohl der Eintrag sonst korrekt aussieht."

Der zweite Eintrag beantwortet direkt die Frage, die ein Nutzer wahrscheinlich stellen wird, statt nur das Feld zu benennen.

---

## 5. Typischer Ablauf: einen Assistant nach einer falschen Antwort verbessern

1. Im jeweiligen Config-Editor (z. B. Bridge Tools) stellt man dem AI Assistant eine Frage, und die Antwort ist falsch oder zu unspezifisch.
2. Zur Seite **AI-Assistant** wechseln und über das Dropdown die passende Kontext-Datei wählen (z. B. `bridge_tools_assistant.md`).
3. In den `Split`-Modus wechseln.
4. Genau den Punkt ergänzen, den der Assistant nicht wusste — am besten im Beispiel-Stil aus Abschnitt 4 (konkretes Feld, konkretes Verhalten, ggf. eine bekannte Fehlerursache).
5. `Save` klicken — wirkt sofort, ohne Neustart.
6. Zurück zum ursprünglichen Editor wechseln und dieselbe Frage erneut stellen, um die Verbesserung zu bestätigen.

**Tipp:** Wenn mehrere Nutzer denselben Assistant verwenden, lohnt es sich, wiederkehrende Fragen systematisch in die Kontext-Datei aufzunehmen, statt sie jedes Mal im Chat neu zu beantworten — die Kontext-Datei ist damit auch eine Art lebendes FAQ für den jeweiligen Editor.
