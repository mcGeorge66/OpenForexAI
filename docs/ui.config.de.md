[Zurück zum UI-Handbuch](ui.de.md)

# Config

Der Bereich `Config` ist die Hauptoberfläche für Profile, Routing und Modul-Definitionen. Jeder Aspekt des OpenForexAI-Verhaltens — welche Agenten aktiv sind, welche Daten das LLM erhält, wie Orders gefiltert werden, welcher Broker oder LLM-Provider verwendet wird — wird über die Config-Seiten gesteuert.

## Unterseiten

| Seite | Zweck |
|-------|-------|
| [Agent Config](ui.config.agent_config.de.md) | Agenten-Definitionen, Handelspaare, LLM-Bindungen, Risiko-Einstellungen |
| [Entity Config](ui.config.entity_config.de.md) | Handelbare Entitäten (Symbole) definieren — NEU |
| [Snapshot Config](ui.config.snapshot_config.de.md) | Markt-Snapshot-Assembly; welche Daten das LLM erhält |
| [Decision Prompt](ui.config.decision_prompt.de.md) | LLM-System-Prompts; Selector-Scripts; Platzhalter-Substitution |
| [Event Routing](ui.config.event_routing.de.md) | Regeln, die bestimmen, welche Agenten welche Events empfangen |
| [System Config](ui.config.system_config.de.md) | Zentrale system.json5 globale Parameter |
| [LLM Modules](ui.config.llm_modules.de.md) | LLM-Provider-Verbindungen (Azure OpenAI / Anthropic) |
| [Broker Modules](ui.config.broker_modules.de.md) | Broker-Adapter-Verbindungen (MT5 / OANDA) |
| [Information](ui.config.information.de.md) | Editierbarer README-artiger Informationsinhalt |
| [Bridge Tools](ui.config.bridge_tools.de.md) | Tool-Freigaben und Bridge-artige Tool-Konfigurationen |
| [Helper Config](ui.config.helper_config.de.md) | Python-Hilfsfunktionen für Snapshot-Transform-Scripts |
| [Package Manager](ui.config.package_manager.de.md) | Konfigurationspakete exportieren und importieren |

Aktuelle Menü-Reihenfolge in der UI:

1. `Information`
2. `Agent Config`
3. `Snapshot Config`
4. `Decision Prompt`
5. `Entity Config`
6. `Bridge Tools`
7. `Event Routing`
8. `System Config`
9. `Helper Config`
10. `Package Manager`
11. `Broker Modules`
12. `LLM Modules`

Vorgesehener Screenshot:
- [Config-Menüreihenfolge](image/ui-13-config-menu-overview.png)

---

## Information

Diese Seite dient für allgemeine editierbare Informations- oder README-Inhalte, die über die Management API bereitgestellt werden.

Auf dieser Seite kann Freitext gespeichert werden, der die Systemkonfiguration, die verwendete Strategie oder Betriebsnotizen beschreibt. Der Inhalt ist über die Management API zugänglich und kann als lebende Dokumentationsschicht für die eigene Installation genutzt werden.

---

## Agent Config

`Agent Config` wird verwendet, um die Laufzeitkonfiguration eines bestimmten Agenten zu bearbeiten.

Wichtige aktuelle Felder:

- Agentenidentität und Runtime-Einstellungen
- erlaubte Tools
- Auswahl des Snapshot-Profils
- Auswahl des Decision-Prompt-Profils

### Agenten-Typen

OpenForexAI verwendet mehrere Agenten-Typen:

| Typ | Rolle |
|-----|-------|
| AA (Analyse-Agent) | Empfängt Kerzen-Events; baut Snapshot; ruft LLM für Marktanalyse auf; erzeugt Handelssignale |
| BA (Broker-Agent) | Empfängt genehmigte Signale; berechnet Positionsgröße; platziert und verwaltet Orders beim Broker |
| EC Relay | Wendet regelbasierte Filter auf Signale an, bevor sie den BA-Agenten erreichen |

### Wichtige Agent-Config-Felder

**Für AA-Agenten:**
- `snapshot_profile`: welches Snapshot-Profil für die Daten-Assembly verwendet wird
- `decision_prompt_profile`: welches Decision-Prompt-Profil die LLM-Systeminstruktion liefert
- `llm_module`: welcher LLM-Provider/-Modell für die Analyse verwendet wird
- `symbols`: Liste der Handelspaare, die dieser Agent analysiert
- `timeframes`: welche Zeitrahmen abonniert werden (M5, M15, H1 usw.)
- `risk_per_trade_pct`: Prozentsatz des Kontokapitals, der pro Trade riskiert wird

**Für BA-Agenten:**
- `broker_module`: welche Broker-Verbindung für die Ausführung verwendet wird
- `max_total_risk_pct`: maximales Gesamtrisiko über alle Positionen (Standard 3 %)
- `atr_sl_multiplier`: ATR-Multiplikator für den Stop-Loss-Abstand
- `atr_tp_multiplier`: ATR-Multiplikator für den Take-Profit-Abstand

Vorgesehener Screenshot:
- [Agent Config mit Snapshot- und Decision-Prompt-Profilen](image/ui-14-agent-config-profiles.png)

---

## Entity Config

`Entity Config` ist ein neuerer Bereich zur Definition handelbarer Entitäten (Symbole/Instrumente) und ihrer Eigenschaften.

Dieser Bereich ist von der Broker-Modul-Konfiguration getrennt: Das Broker-Modul definiert die Verbindung, während Entity Config die Eigenschaften jedes handelbaren Instruments definiert, die das System kennen soll.

### Was Entity Config definiert

Jede Entität (Symbol) kann mit folgenden Eigenschaften konfiguriert werden:

- **Anzeigename**: menschenlesbares Label (z. B. "Euro / US-Dollar")
- **Pip-Größe**: der Pip-Wert dieses Instruments (z. B. 0,0001 für EURUSD)
- **Lot-Größe**: Standard-Lot-Definition
- **Handelszeiten**: wann dieses Symbol für den Handel verfügbar ist
- **Spread-Modell**: erwarteter typischer Spread (wird in Risikoberechnungen verwendet)
- **Kategorie**: Forex-Major, Forex-Minor, Exotisch, Index, Rohstoff usw.

### Warum Entity Config wichtig ist

Eine korrekte Entitätskonfiguration ist für die korrekte Positionsgröße unerlässlich. Die Positionsgrößenformel erfordert die Kenntnis des Pip-Werts für das Instrument. Wenn eine Entität falsch konfiguriert ist (falsche Pip-Größe oder Lot-Definition), sind alle Positionsgrößenberechnungen für dieses Symbol falsch — was sich direkt auf das Risikomanagement auswirkt.

Immer Entity Config prüfen, wenn ein neues Symbol zum Handel hinzugefügt wird.

---

## Snapshot Config

`Snapshot Config` wird verwendet, um festzulegen, welche Daten gesammelt, interpretiert und in einen snapshotgestützten Agentenlauf weitergegeben werden.

Der Snapshot ist die User-Message, die das LLM erhält. Er enthält den gesamten Marktkontext, den das LLM für eine Handelsentscheidung benötigt. Qualität und Relevanz des Snapshots bestimmen direkt die Qualität der LLM-Analyse.

### Snapshot-Struktur

Ein Snapshot-Profil definiert eine Menge von **Calculation Blocks**. Jeder Block ist eine Datenquelle oder Transformation:

- **Tool-Blocks**: ein System-Tool aufrufen und seine Ausgabe einschließen (z. B. aktuelle OHLCV-Daten abrufen, ATR abrufen, Swing-Levels abfragen)
- **Transform-Blocks**: ein Python-Script ausführen, um Tool-Ausgaben zu verarbeiten, zu kombinieren oder zusammenzufassen
- **Assembly-Block**: ein abschließendes Python-Script, das alle Block-Ausgaben in den Text/JSON assembliert, der zur LLM-User-Message wird

### Gestaltungsprinzipien

- Nur aufnehmen, was die Strategie benötigt. Mehr Daten sind nicht immer besser.
- Daten klar strukturieren. Das LLM arbeitet besser, wenn Daten beschriftet und logisch geordnet sind.
- Transform-Blocks verwenden, um Metriken abzuleiten (z. B. ob der Preis über oder unter einem Swing-Level liegt), anstatt rohe Zahlen dem LLM zur Interpretation zu überlassen.
- Snapshots mit dem Test-Snapshot-Panel in Decision Prompt oder dem Tool Executor testen.

Siehe die dedizierte Seite: [Snapshot Config](ui.config.snapshot_config.de.md)

Vorgesehener Screenshot:
- [Snapshot Config Profileditor](image/ui-15-snapshot-config-editor.png)

---

## Decision Prompt

`Decision Prompt` dient zur Pflege benannter snapshotbezogener Prompt-Profile für snapshotgestützte Agentenläufe.

Diese Profile sind nicht auf AA-Läufe beschränkt. Sie bilden die Laufzeit-Promptebene, die mit jedem Agenten kombiniert werden kann, der ein Snapshot-Profil verwendet.

### Was Decision Prompt steuert

Das Decision-Prompt-Profil definiert:
1. **Die Systeminstruktion**, die das LLM erhält (die "Spielregeln" für die KI)
2. **Wie diese Instruktion ausgewählt wird** (über ein Python-Selector-Script — verschiedene Marktbedingungen können verschiedene Prompts auslösen)
3. **Dynamische Platzhalter-Werte**, die zur Laufzeit in den Prompt-Text eingefügt werden

### Wichtigste Konfigurationsseite

Für die Anpassung der Trading-Performance ist Decision Prompt typischerweise die wichtigste Konfigurationsseite. Das Ändern des Prompts verändert alles daran, wie das LLM über den Markt argumentiert.

Vollständige Anleitung: [Decision Prompt](ui.config.decision_prompt.de.md)

Vorgesehener Screenshot:
- [Decision Prompt Editor](image/ui-17-decision-prompt-editor.png)

---

## Bridge Tools

`Bridge Tools` dient zur Definition oder Pflege von Tool-Freigaben und bridgeartigen Tool-Konfigurationen, die später Agenten zugewiesen oder durch Snapshot-Profile verwendet werden können.

Bridge Tools ermöglichen es, externe Tools oder APIs über ein standardisiertes Interface dem Agentensystem zugänglich zu machen. Das erlaubt:
- Benutzerdefinierte Datenquellen (proprietäre Indikatoren, externe Preisfeeds)
- Externe API-Integrationen (Sentiment-Daten, News-APIs)
- Benutzerdefinierte Berechnungsdienste

Vorgesehener Screenshot:
- [Bridge Tools Konsole](image/ui-18-bridge-tools-console.png)

---

## Event Routing

`Event Routing` dient zur Pflege der Regeln, die entscheiden, welche Agenten welche Events empfangen.

Event Routing ist die Konfigurationsschicht des EC Relay. Es definiert:
- Welcher Agent welchen Event-Typ empfängt
- Filterbedingungen (Tageszeit, Symbol, Signal-Stärke-Schwellwert)
- Ob ein Event weitergeleitet, blockiert oder vor der Zustellung transformiert wird

### Häufige Event-Routing-Muster

**Tageszeit-Filter**: Signal-Weiterleitung zwischen 22:00 und 01:00 UTC blockieren, um Handel bei geringer Liquidität zu vermeiden

**News-Sperre**: Signal-Weiterleitung 30 Minuten vor und nach hochimpact-Wirtschaftsereignissen blockieren

**Konfidenz-Schwellwert**: nur Signale weiterleiten, bei denen die LLM-Konfidenz einen Mindestwert überschreitet (z. B. 70)

**Symbolspezifisches Routing**: EURUSD-Signale an Agent A und GBPUSD-Signale an Agent B routen

Vorgesehener Screenshot:
- [Event Routing Editor](image/ui-19-event-routing-editor.png)

---

## System Config

`System Config` dient zur Bearbeitung der zentralen `system.json5`.

Das ist die Konfigurationsseite mit der größten Auswirkung, weil sie globales Laufzeitverhalten beeinflusst. Die Datei system.json5 enthält:

- globale Runtime-Einstellungen
- Agenten-Definitionen (oder Verweise auf diese)
- alle Snapshot-Profile
- alle Decision-Prompt-Profile
- Event-Routing-Regeln
- Modul-Referenzen

Die direkte Bearbeitung von system.json5 ermöglicht vollständige Kontrolle, erfordert aber sorgfältige JSON5-Syntax. Validierungsfehler hier können verhindern, dass das System startet.

**Empfehlung**: Die dedizierten Config-Seiten (Agent Config, Snapshot Config, Decision Prompt, Event Routing) für Routineänderungen verwenden. System Config nur einsetzen, wenn Änderungen nötig sind, die über die einzelnen Seiten nicht zugänglich sind, oder beim Importieren/Exportieren der vollständigen Konfiguration.

Vorgesehener Screenshot:
- [System Config Editor](image/ui-20-system-config-editor.png)

---

## Helper Config

`Helper Config` dient zur Bearbeitung von `config/snapshot_helpers.py`, also der optionalen Python-Hilfsfunktionen für Snapshot-Transform-Scripts.

Der Editor ist bewusst einfach gehalten, aber beim Speichern wird serverseitig immer ein finaler Python-Syntaxcheck ausgeführt, bevor die Datei geschrieben wird.

Hier definierte Hilfsfunktionen stehen als Imports in allen Snapshot-Transform-Scripts zur Verfügung. Das ermöglicht es, gemeinsame Logik (z. B. eine Zahl als Pips formatieren, eine Trendrichtung klassifizieren, einen Zeitbereich formatieren) einmal zu definieren und in mehreren Snapshot-Profilen wiederzuverwenden.

Beispiel-Hilfsfunktion:

```python
def format_pips(price_diff, pip_size=0.0001):
    """Preisdifferenz in Pips umrechnen."""
    return round(price_diff / pip_size, 1)

def classify_trend(ema_fast, ema_slow):
    """'BULLISH', 'BEARISH' oder 'NEUTRAL' basierend auf EMA-Verhältnis zurückgeben."""
    if ema_fast > ema_slow * 1.001:
        return "BULLISH"
    elif ema_fast < ema_slow * 0.999:
        return "BEARISH"
    return "NEUTRAL"
```

Siehe die Snapshot-Referenz: [Snapshot Config](ui.config.snapshot_config.de.md)

---

## Package Manager

`Package Manager` wird verwendet, wenn ausgewählte Teile der Runtime-Konfiguration exportiert oder importiert werden sollen.

Aktuell unterstützte Paketbereiche:

- Agents
- Snapshot Profiles
- Decision Prompt Profiles
- Bridge Tools
- Event Routing
- System Config

### Typische Einsatzfälle

**Konfiguration zwischen Umgebungen übertragen**: eine getestete Konfiguration aus einer Staging-Umgebung exportieren und in die Produktion importieren.

**Funktionierende Einstellungen sichern**: vor größeren Änderungen die aktuelle Konfiguration als Backup exportieren.

**Konfigurationen teilen**: ein Konfigurationspaket exportieren, um es mit einer anderen OpenForexAI-Installation zu teilen.

**Versionskontrolle**: Konfigurationen regelmäßig exportieren und zusammen mit dem Code in einem Versionskontrollsystem speichern.

### Import-Verhalten

Beim Importieren eines Pakets:
- vorhandene Profile mit demselben Namen werden überschrieben (mit Bestätigung)
- neue Profile werden hinzugefügt
- Profile, die nicht im Paket enthalten sind, bleiben unverändert

Immer den Paketinhalt prüfen, bevor in eine Live-Umgebung importiert wird.

Vorgesehener Screenshot:
- [Package Manager Export-Import-Workflow](image/ui-21-package-manager.png)

---

## Broker Modules

`Broker Modules` dient zur direkten Bearbeitung von Broker-Moduldateien.

Diese Seiten richten sich an fortgeschrittene Operatoren, die Adaptermodule direkt anpassen müssen und nicht nur das Verhalten auf Agentenebene.

Jede Broker-Moduldatei definiert:
- Verbindungstyp (MT5 / OANDA)
- Serveradresse und Zugangsdaten
- Kontobezeichner
- Verbindungsparameter (Timeout, Retry-Richtlinie, Polling-Intervall)

Änderungen an Broker-Modulen erfordern einen Runtime-Neustart.

**Sicherheitshinweis**: Broker-Moduldateien enthalten API-Zugangsdaten. Diese Dateien niemals in öffentliche Versionskontrolle einpflegen. Wo möglich Umgebungsvariablen für sensible Werte verwenden.

Vorgesehener Screenshot:
- [Broker Modules Editor](image/ui-22-broker-modules-editor.png)

---

## LLM Modules

`LLM Modules` dient zur direkten Bearbeitung von LLM-Moduldateien.

Jede LLM-Moduldatei definiert:
- Provider (azure_openai / anthropic)
- Modellname (gpt-4o, gpt-4o-mini, claude-sonnet-4-5, claude-haiku-3-5 usw.)
- API-Endpunkt und Zugangsdaten
- Anfrageparameter (Temperature, max_tokens, Timeout)
- Retry-Richtlinie

### Modellauswahl-Empfehlungen

| Einsatzzweck | Empfohlenes Modell |
|--------------|-------------------|
| Produktions-Live-Trading | GPT-4o oder Claude Sonnet |
| Strategie-Test / Validierung | GPT-4o-mini oder Claude Haiku |
| Hochfrequenz M5 (kostensensitiv) | GPT-4o-mini oder Claude Haiku |
| Komplexe Multi-Faktor-Strategien | GPT-4o oder Claude Sonnet |

**Temperature**: für Handelssignale niedrige Temperature verwenden (0,1–0,3), um konsistentere, deterministischere Ausgaben zu erhalten. Hohe Temperature führt zu unnötiger Varianz in der Signalrichtung.

**Max Tokens**: hoch genug setzen, um eine vollständige Analyseantwort zu erhalten. 500–1000 Tokens sind für ein strukturiertes Handelssignal typisch.

Vorgesehener Screenshot:
- [LLM Modules Editor](image/ui-23-llm-modules-editor.png)
