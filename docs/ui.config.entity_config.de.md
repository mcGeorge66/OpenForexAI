[Zurück zu Config](ui.config.de.md)

# Entity Config — Event Composer (EC)

Die Seite `Entity Config` ist der Ort, wo **Event Composer** (ECs) erstellt, konfiguriert und verwaltet werden. Event Composer sind Python-Skripte, die als gleichwertige Mitglieder des Event-Busses neben Agenten laufen. Sie sind ein fundamentaler Baustein für Workflow-Logik, die keinen vollständigen LLM-Agenten-Zyklus erfordert.

---

## Was ist ein Event Composer?

Ein Event Composer ist ein Python-Skript das:
- Auf dem Event-Bus neben Agenten lebt
- Durch Ereignisse ausgelöst wird (genau wie Agenten)
- Beliebige registrierte Tools über den `tools`-Proxy aufrufen kann
- Optional ein LLM über `ask_llm()` aufrufen kann
- Ein `dict` zurückgibt um ein `ec_output`-Ereignis zu veröffentlichen, oder `None` um den Workflow zu stoppen

**Der wesentliche Unterschied zu Agenten:** Agenten rufen immer ein LLM als Kernoperation auf. Event Composer rufen KEIN LLM automatisch auf — sie sind reine Python-Logik mit optionalem LLM-Zugang. Das macht sie schnell, vorhersehbar und kostengünstig im Betrieb.

### Warum Event Composer existieren

In einem Multi-Agenten-Handelssystem erfordert nicht jede Entscheidung LLM-Reasoning. Viele Workflow-Schritte sind deterministisch:

- "Diese Analyse an den BA-Agenten weiterleiten" — kein LLM nötig, einfach weiterleiten
- "Workflow stoppen wenn kein Handelssignal vorhanden" — kein LLM nötig, einfach ein Feld prüfen
- "Nicht handeln wenn bereits eine Position offen ist" — kein LLM nötig, `get_open_positions` aufrufen
- "Kontomargendaten zur Analyse hinzufügen bevor der BA-Agent sie sieht" — kein LLM nötig, einfach anreichern

Event Composer erledigen all diese Fälle effizient. Sie bieten auch einen leichtgewichtigen Einstiegspunkt für den seltenen Fall, wo eine zweite LLM-Meinung sinnvoll ist (über `ask_llm()`).

### Position in der Workflow-Kette

Der typische AA → EC → BA Workflow:

```
1. AA-Agent läuft auf M5-Trigger
   → Analysiert Marktdaten
   → Veröffentlicht analysis_result-Ereignis

2. Event Routing: analysis_result von diesem AA → dieser EC
   → EC-Skript wird ausgeführt

3. EC-Skript:
   → Filtert, reichert an oder transformiert den Input optional
   → Gibt dict zurück → ec_output-Ereignis wird veröffentlicht
   → Gibt None zurück → Workflow stoppt, kein ec_output

4. Event Routing: ec_output von diesem EC → BA-Agent
   → BA-Agent empfängt die (optional angereicherte) Analyse
   → BA-Agent entscheidet ob eine Order aufgegeben wird
```

Diese Kette bietet eine saubere Trennung der Verantwortlichkeiten:
- **AA** kümmert sich um Marktanalyse
- **EC** kümmert sich um Workflow-Logik und Filterung
- **BA** kümmert sich um Order-Ausführung

---

## EC-ID-Format

Jeder Event Composer hat eine eindeutige ID nach diesem Format:

**`BROKER(5)-PAIR(6)-EC-NAME`**

Segmente:
- **BROKER** — 5-Zeichen Broker-Code (gleich wie bei Agent-IDs), z.B. `OXS_T`, `GLOBL`
- **PAIR** — 6-Zeichen Pair-Code, z.B. `EURUSD`, `ALL___`
- **EC** — festes Literal, immer `EC`, identifiziert dies als Event Composer (kein Agent)
- **NAME** — beschreibender Name, keine strikte Längenbegrenzung, aber kurz halten

**Beispiele:**
- `OXS_T-EURUSD-EC-RELAY` — EURUSD-Relay-EC für OXS Test-Broker
- `OXS_T-USDJPY-EC-RELAY` — USDJPY-Relay-EC für OXS Test-Broker
- `OXS_T-GBPUSD-EC-FILTER` — GBPUSD-Signal-Filter-EC
- `GLOBL-ALL___-EC-ECHO` — Globaler Echo-/Debug-EC für alle Paare
- `OXS_T-EURUSD-EC-RISK` — EURUSD-Risikoprüfungs-EC

---

## Editor-Layout

Die Entity Config-Seite hat drei Hauptbereiche:

1. **EC-Listen-Panel** — linke Seitenleiste mit allen vorhandenen ECs und einem "New EC"-Button
2. **Editor-Tabs** — mittleres Panel mit Script-, Config- und Test-Tabs
3. **Metadaten-Felder** — rechtes Panel oder eingebettet mit EC-ID, enable, pair, broker und allen Konfigurationsfeldern

### EC-Listen-Panel

Listet alle registrierten Event Composer auf. Auf einen EC klicken lädt ihn in den Editor. Jeder Eintrag zeigt:
- EC-ID
- Enable-Status (aktiv/inaktiv Badge)
- Skript-Status (letzter Speicher- oder Fehlerindikator)

**New-EC-Button:** Erstellt einen leeren EC-Eintrag mit leerem Skript und Config. Es muss eine gültige EC-ID eingegeben und gespeichert werden bevor der EC aktiv wird.

---

## Tab 1: Script

Der Script-Tab enthält einen Monaco-Code-Editor (derselbe Editor wie in VS Code) mit:
- Python-Syntax-Hervorhebung
- Automatischer Einrückung
- Zeilennummern
- Suchen/Ersetzen (Strg+H)
- Horizontalem und vertikalem Scrollen

### Skript-Vertrag

Jedes EC-Skript muss eine `async def main(input, config, tools)`-Funktion definieren. Dies ist der einzige erforderliche Einstiegspunkt.

```python
async def main(input, config, tools) -> dict | None:
    """
    input:  Die auslösende Ereignis-Payload (Python-Dict).
            Bei analysis_result-Ereignissen ist das die vollständige Analyse-JSON.
    config: Das config_json aus der EC-Konfiguration, als Python-Dict geparst.
            Enthält alle benutzerdefinierten Einstellungen (Schwellenwerte, Flags, etc.).
    tools:  ToolsProxy-Objekt zum Aufrufen registrierter Tools.
    
    Gibt zurück:
        dict  → wird als ec_output-Ereignis veröffentlicht
        None  → Workflow stoppt, kein ec_output wird veröffentlicht
    """
    ...
```

### Injizierte Funktionen

Zusätzlich zu den drei Parametern sind folgende Funktionen direkt im Skript-Scope verfügbar (kein Import nötig):

**`await tools.call("tool_name", **kwargs)`**

Ruft ein beliebiges registriertes Tool mit Schlüsselwort-Argumenten auf. Gibt das Tool-Ergebnis als Python-Dict oder -Liste zurück.

```python
candles = await tools.call("get_candles", pair="EURUSD", timeframe="H1", count=20)
positions = await tools.call("get_open_positions")
account = await tools.call("get_account_status")
```

**`await ask_llm(llm_modul, frage_oder_nachrichten, ...)`**

Ruft ein LLM auf ohne die vollständige Agenten-Pipeline zu durchlaufen. Zwei Verwendungsformen:

Einfache Form (String-Frage):
```python
response = await ask_llm(
    "azure_azmin",
    "Soll ich angesichts dieser Analyse einen BUY-Trade eingehen? Antworte nur mit JA oder NEIN."
)
antwort = response.content  # String
```

Vollständige Form (Nachrichten-Liste):
```python
response = await ask_llm(
    "azure_azmin",
    messages=[
        {"role": "user", "content": "Bitte dieses Trade-Setup prüfen: ..."}
    ],
    system_prompt="Du bist ein konservativer Risikomanager.",
    tools=[]  # optionale Tool-Liste für den LLM-Aufruf
)
```

Das `response`-Objekt hat ein `.content`-Attribut mit der Text-Antwort des LLMs.

### Was ein gutes Skript ausmacht

- **Fokussiert halten:** Ein EC sollte eine Sache gut machen — weiterleiten, filtern, anreichern oder prüfen
- **None explizit zurückgeben** wenn der Workflow gestoppt werden soll — keine Exceptions für Flusskontrolle
- **Config für Schwellenwerte nutzen:** Keine Werte wie max_spread oder min_confidence im Skript hartkodieren — in config_json auslagern damit sie ohne Skriptänderungen angepasst werden können
- **Fehlende Felder robust behandeln:** `.get()` mit Defaults statt direktem Schlüsselzugriff verwenden — Analyse-Payloads können sich im Laufe der Zeit verändern
- **Vorsicht mit ask_llm:** Jeder LLM-Aufruf hat Kosten und Latenz. Sparsam einsetzen und nur wenn echtes LLM-Reasoning einen Mehrwert bietet den deterministische Logik nicht leisten kann

---

## Tab 2: Config

Der Config-Tab enthält einen JSON-Editor für das `config_json`-Feld. Das ist ein frei definiertes JSON-Objekt — es hat kein festes Schema.

Die Config wird dem `main()`-Funktion als `config`-Python-Dict übergeben. Damit werden Werte ausgelagert die möglicherweise ohne Skriptänderungen angepasst werden müssen:

```json
{
  "max_spread": 20,
  "min_confidence": 0.65,
  "allowed_decisions": ["BUY", "SELL"],
  "position_limit": 1,
  "debug_mode": false
}
```

Im Skript:
```python
max_spread = config.get("max_spread", 20)
min_confidence = config.get("min_confidence", 0.65)
```

Gute Kandidaten für config_json-Werte:
- Numerische Schwellenwerte (Spread-Limits, Konfidenz-Untergrenzen, ATR-Vielfache)
- Feature-Flags (spezifische Prüfungen aktivieren/deaktivieren)
- LLM-Modul-Namen für `ask_llm`-Aufrufe
- Pair-spezifische Überschreibungen
- Nachrichtenvorlagen

---

## Tab 3: Test

Der Test-Tab ermöglicht das sofortige Ausführen des EC-Skripts gegen das laufende System mit einer benutzerdefinierten Input-Payload.

### Test-Workflow

1. JSON-Test-Payload im Input-Editor schreiben (simuliert das auslösende Ereignis)
2. **Run** klicken
3. Skript läuft gegen das Live-System (echte Tools, echte Daten)
4. Ergebnisse erscheinen im Output-Panel

**Wichtig:** Es muss **gespeichert** werden bevor getestet wird. Der Test-Tab führt immer die gespeicherte Version des Skripts aus, nicht die aktuell im Editor geöffnete Version wenn nicht gespeichert. Speichern lädt den EC im laufenden System automatisch neu.

### Input-Editor

Ein JSON-Editor für die Test-Payload. Typischerweise ein Beispiel einer `analysis_result`-Ereignis-Payload:

```json
{
  "agent_id": "OXS_T-EURUSD-AA-ANLYS",
  "pair": "EURUSD",
  "decision": "BUY",
  "confidence": 0.78,
  "order_start_signal": "YES",
  "entry": 1.0921,
  "stop_loss": 1.0885,
  "take_profit": 1.0990,
  "analysis_summary": "Bullischer Ausbruch über wichtigen Widerstand...",
  "spread": 8
}
```

### Output-Panel

Nach der Ausführung zeigt das Output-Panel:

| Element | Beschreibung |
|---|---|
| Status-Badge | Grünes "Success" oder rotes "Error" |
| Latenz | Ausführungszeit in Millisekunden |
| Output-JSON | Das von `main()` zurückgegebene Dict, formatiert mit Zeilenumbrüchen |
| Kopieren-Button | Kopiert das vollständige JSON-Output in die Zwischenablage |

Wenn `main()` `None` zurückgegeben hat, zeigt das Output `null` mit einem Hinweis dass der Workflow gestoppt worden wäre.

Wenn das Skript eine Exception ausgelöst hat, erscheint das Fehler-Badge mit Fehlermeldung und Traceback.

---

## Alle Konfigurationsfelder

### ec_id

**Pflichtfeld.** Der eindeutige Bezeichner für diesen Event Composer.

Format: `BROKER(5)-PAIR(6)-EC-NAME`

Darf nicht mit einer bestehenden EC- oder Agent-ID kollidieren. Das `EC`-Literal an Position 3 unterscheidet EC-IDs von Agent-IDs.

### enable

`true` — Der EC ist aktiv und empfängt Ereignisse.
`false` — Die EC-Konfiguration ist gespeichert aber inaktiv.

Ermöglicht das vorübergehende Deaktivieren ohne Löschen. Hot-Reload-sicher — Deaktivierung tritt ohne Neustart in Kraft.

### pair

Der Währungspaar-Kontext für diesen EC. Wird verwendet wenn Tools ohne explizites Pair-Argument aufgerufen werden. Auch für Event-Routing-Matching verwendet.

Beispiel: `EURUSD`

`ALL___` setzen für ECs die Signale von mehreren Paaren verarbeiten.

### broker

Das Broker-Modul mit dem dieser EC assoziiert ist. Wird als Standard-Kontext für Tool-Aufrufe verwendet die einen Broker benötigen (z.B. `get_open_positions`).

### timer

Periodische Aktivierung unabhängig von Ereignissen.

```json
{
  "enabled": true,
  "interval_seconds": 300
}
```

Die meisten ECs verwenden keine Timer — sie reagieren auf Ereignisse. Timer für ECs verwenden die eine periodische Prüfung benötigen (z.B. offene Positionen alle 5 Minuten überwachen).

### AnyCandle

Ganzzahl-Divisor der auf `m5_agent_trigger`-Ereignisse angewendet wird. Funktioniert identisch zur Agenten-AnyCandle-Einstellung.

- `1` — jede M5-Kerze
- `3` — alle 15 Minuten
- `6` — alle 30 Minuten
- `12` — jede Stunde

Nur relevant wenn `m5_agent_trigger` in event_triggers ist.

### event_triggers

Liste von Ereignistypen die diesen EC aktivieren. Gleiche Ereignisnamen wie bei Agenten.

Häufige Werte:
- `analysis_result` — Ausgabe von AA-Agenten (am häufigsten für Relay-ECs)
- `ec_output` — Ausgabe eines anderen ECs (verkettete ECs)
- `m5_agent_trigger` — neue M5-Kerze
- `timer` — periodische Aktivierung

### session_filter

Gleiches Format wie Agenten-session_filter. Schränkt ein wann der EC Ereignisse verarbeitet.

```json
[
  {"session": "london", "pre": 10, "post": 0},
  {"session": "new_york", "pre": 0, "post": -30}
]
```

Den gleichen Session Filter wie der gepaarte AA-Agent verwenden um konsistentes Verhalten sicherzustellen.

### tool_config

Steuert die Tool-Ausführung innerhalb des EC-Skripts.

```json
{
  "allowed_tools": ["get_open_positions", "get_account_status", "get_candles"],
  "max_tool_turns": 5,
  "script_timeout_seconds": 60
}
```

| Feld | Beschreibung |
|---|---|
| `allowed_tools` | Liste der Tools die das Skript aufrufen darf. Aufrufe anderer Tools werden abgelehnt. |
| `max_tool_turns` | Maximale Anzahl an Tool-Aufrufen die das Skript pro Ausführung machen darf. Standard: 10. |
| `script_timeout_seconds` | Maximale Ausführungszeit für das Skript in Sekunden. Standard: 60. Skripte die dieses Limit überschreiten werden beendet. |

### config_json

JSON-String der als `config`-Parameter an `main()` übergeben wird. Beliebige benutzerdefinierte Einstellungen hier definieren. Kein festes Schema — vollständig frei.

### script

Der Python-Skript-Inhalt. Wird im Script-Tab definiert. Als String in der Konfiguration gespeichert.

---

## Die Workflow-Kette im Detail

### Schritt 1: AA-Agent-Analyse

Der AA-Agent für EURUSD läuft auf M5-Kerzen (alle 15 Minuten mit AnyCandle=3). Er erstellt einen Markt-Snapshot, analysiert Bedingungen und veröffentlicht ein `analysis_result`-Ereignis:

```json
{
  "event_type": "analysis_result",
  "source_agent": "OXS_T-EURUSD-AA-ANLYS",
  "pair": "EURUSD",
  "decision": "BUY",
  "confidence": 0.82,
  "order_start_signal": "YES",
  "entry": 1.0921,
  "stop_loss": 1.0885,
  "take_profit": 1.0990
}
```

### Schritt 2: Event Routing

Die Event-Routing-Konfiguration leitet `analysis_result`-Ereignisse von `OXS_T-EURUSD-AA-ANLYS` an `OXS_T-EURUSD-EC-RELAY`.

### Schritt 3: EC-Ausführung

Das EC-Skript läuft mit `input` = der obigen Analyse-Payload. Das Skript wendet seine Logik an und gibt entweder ein Dict oder None zurück.

### Schritt 4: ec_output veröffentlicht

Wenn das Skript ein Dict zurückgegeben hat, veröffentlicht das System ein `ec_output`-Ereignis mit dem zurückgegebenen Dict als Payload.

### Schritt 5: BA-Agent empfängt

Event Routing leitet `ec_output` von `OXS_T-EURUSD-EC-RELAY` an `OXS_T-ALL___-BA-ANLYS`. Der BA-Agent empfängt die Payload über `pass_trigger=true` und trifft seine Ausführungsentscheidung.

---

## Vollständige Skript-Beispiele

### Beispiel 1: Transparentes Relay

Der einfachstmögliche EC — leitet die Analyse unverändert weiter. Als Startpunkt verwenden wenn das EC-Framework ohne Filterlogik gewünscht wird.

```python
async def main(input, config, tools):
    return input  # unverändert weiterleiten, als ec_output veröffentlichen
```

**Wann verwenden:** Wenn die EC-Infrastruktur (für zukünftige Filterung oder Anreicherung) benötigt wird, aber heute noch keine Logik erwünscht ist. Das Relay-Muster ermöglicht späteres Hinzufügen von Logik durch Änderung nur des EC-Skripts, ohne Agent-Konfigurationen zu ändern.

---

### Beispiel 2: Signal-Filter (Bei fehlendem Signal stoppen)

Stoppt den Workflow wenn der AA-Agent kein Handelssignal erzeugt hat.

```python
async def main(input, config, tools):
    # Nur weiterfahren wenn ein aktives Handelssignal vorhanden ist
    if input.get("order_start_signal") != "YES":
        return None  # stopp - kein Handelssignal, BA-Agent wird nicht laufen
    
    # Nur weiterfahren bei direktionalen Entscheidungen
    decision = input.get("decision", "NEUTRAL")
    if decision == "NEUTRAL":
        return None  # stopp - neutrale Entscheidung, nichts zu handeln
    
    # Nur weiterfahren wenn Konfidenz über Schwellenwert
    min_confidence = config.get("min_confidence", 0.70)
    confidence = input.get("confidence", 0)
    if confidence < min_confidence:
        return None  # stopp - Konfidenz zu niedrig
    
    return input  # alle Prüfungen bestanden, an BA-Agent weiterleiten
```

**config_json-Beispiel:**
```json
{
  "min_confidence": 0.70
}
```

**Wann verwenden:** Das ist der Standard-Filter-EC für jedes Handelspaar. Er verhindert dass der BA-Agent bei jedem Analyse-Zyklus läuft und weckt ihn nur wenn eine echte Handelsmöglichkeit besteht.

---

### Beispiel 3: Positions-Wächter (Doppelte Positionen verhindern)

Prüft ob bereits eine Position für dieses Pair offen ist bevor eine neue Order erlaubt wird.

```python
async def main(input, config, tools):
    # Zuerst auf aktives Signal prüfen
    if input.get("order_start_signal") != "YES":
        return None
    
    pair = input.get("pair", "EURUSD")
    
    # Auf bestehende offene Positionen prüfen
    positions = await tools.call("get_open_positions", pair=pair)
    
    max_positions = config.get("max_positions", 1)
    if positions and len(positions) >= max_positions:
        # Position bereits vorhanden - keine weitere öffnen
        return None
    
    return input  # keine bestehende Position, Trade erlauben
```

**config_json-Beispiel:**
```json
{
  "max_positions": 1
}
```

**Wann verwenden:** In jedem System wo strikte Ein-Position-pro-Pair-Disziplin gewünscht wird. Verhindert Pyramidisieren, es sei denn `max_positions` wird explizit höher gesetzt.

---

### Beispiel 4: Spread-Filter (Bei hohem Spread überspringen)

Verhindert das Handeln wenn der Broker-Spread zu weit ist (häufig bei News-Ereignissen und Marktöffnung/-schließung).

```python
async def main(input, config, tools):
    if input.get("order_start_signal") != "YES":
        return None
    
    spread = input.get("spread", 0)
    max_spread = config.get("max_spread", 20)
    
    if spread > max_spread:
        # Spread zu weit - dieses Signal überspringen
        return None
    
    return input
```

**config_json-Beispiel:**
```json
{
  "max_spread": 20
}
```

**Wann verwenden:** Spread-Prüfung immer in Produktions-Handelssystemen einschließen. Der AA-Agent berechnet den Spread und schließt ihn in die Analyse-Payload ein. Der EC prüft ihn vor der Ausführung.

Hinweis: Der Spread-Wert in der Analyse-Payload ist in broker-nativen Einheiten (typischerweise Pips × 10 bei Standard-5-stelliger Preisgestaltung). Ein Wert von `20` entspricht typischerweise 2,0 Pips.

---

### Beispiel 5: LLM-Zweitmeinung (Risikomanager)

Nutzt `ask_llm()` um ein konservatives LLM das Trade-Setup prüfen zu lassen bevor es weitergeleitet wird.

```python
async def main(input, config, tools):
    if input.get("order_start_signal") != "YES":
        return None
    
    analysis_summary = input.get("analysis_summary", "Keine Analyse vorhanden")
    decision = input.get("decision", "NEUTRAL")
    confidence = input.get("confidence", 0)
    
    llm_module = config.get("llm_module", "azure_azmin")
    
    # Zweites LLM um Prüfung des Trades bitten
    prompt = (
        f"Trade-Prüfungsanfrage:\n"
        f"Richtung: {decision}\n"
        f"Konfidenz: {confidence:.0%}\n"
        f"Analyse: {analysis_summary}\n\n"
        f"Soll dieser Trade durchgeführt werden? Nur JA oder NEIN antworten."
    )
    
    response = await ask_llm(
        llm_module,
        prompt,
        system_prompt=(
            "Du bist ein konservativer Risikomanager. "
            "Deine Aufgabe ist es schlechte Trades zu verhindern, nicht gute zu fördern. "
            "Im Zweifelsfall NEIN sagen."
        )
    )
    
    answer = response.content.strip().upper()
    
    if "NEIN" in answer or "NO" in answer:
        return None  # Zweitmeinung sagt Nein
    
    # Risikobewertungs-Notiz zum Output hinzufügen
    return {
        **input,
        "risk_review": "GENEHMIGT",
        "risk_reviewer": llm_module
    }
```

**config_json-Beispiel:**
```json
{
  "llm_module": "azure_azmin"
}
```

**Wann verwenden:** Hochwertiger Handel wo eine Zweitmeinung echte Risikominimierung bietet. Hinweis: Das fügt Latenz (ein zusätzlicher LLM-Aufruf pro Handelssignal) und Kosten hinzu. Sparsam einsetzen.

---

### Beispiel 6: Daten-Anreicherung (Kontext-Injektion)

Reichert die Analyse-Payload mit zusätzlichem Marktkontext an bevor sie an den BA-Agenten weitergegeben wird.

```python
async def main(input, config, tools):
    if input.get("order_start_signal") != "YES":
        return None
    
    pair = input.get("pair", "EURUSD")
    
    # Zusätzlichen Kontext sammeln den der AA-Agent nicht enthielt
    h4_candles = await tools.call("get_candles", pair=pair, timeframe="H4", count=5)
    open_positions = await tools.call("get_open_positions")
    account = await tools.call("get_account_status")
    
    # Input mit zusätzlichen Daten anreichern
    enriched = {
        **input,
        "h4_context": h4_candles,
        "existing_positions": open_positions,
        "account_balance": account.get("balance"),
        "margin_free": account.get("margin_free"),
        "margin_level_pct": account.get("margin_level_pct")
    }
    
    # Risikoprüfung: nicht handeln wenn Margin-Level gefährlich niedrig
    margin_level = account.get("margin_level_pct", 999)
    min_margin_level = config.get("min_margin_level_pct", 200)
    
    if margin_level < min_margin_level:
        return None  # unzureichender Margin-Level
    
    return enriched
```

**config_json-Beispiel:**
```json
{
  "min_margin_level_pct": 200
}
```

**Wann verwenden:** Wenn der System Prompt des BA-Agenten Kontodaten oder H4-Kontext referenziert den der AA-Agent nicht sammelt. Der EC übernimmt die Anreicherung damit der BA-Agent alles Benötigte in einer einzigen Payload erhält.

---

## Mehrere Prüfungen kombinieren

In der Praxis kombinieren die meisten Produktions-ECs mehrere Prüfungen in einem einzigen Skript:

```python
async def main(input, config, tools):
    pair = input.get("pair", "EURUSD")
    
    # 1. Signalprüfung
    if input.get("order_start_signal") != "YES":
        return None
    
    if input.get("decision") == "NEUTRAL":
        return None
    
    # 2. Konfidenzprüfung
    min_confidence = config.get("min_confidence", 0.65)
    if input.get("confidence", 0) < min_confidence:
        return None
    
    # 3. Spread-Prüfung
    max_spread = config.get("max_spread", 25)
    if input.get("spread", 0) > max_spread:
        return None
    
    # 4. Positionsprüfung
    positions = await tools.call("get_open_positions", pair=pair)
    if positions and len(positions) >= config.get("max_positions", 1):
        return None
    
    # 5. Margin-Prüfung
    account = await tools.call("get_account_status")
    margin_level = account.get("margin_level_pct", 999)
    if margin_level < config.get("min_margin_level_pct", 150):
        return None
    
    # Alle Prüfungen bestanden — anreichern und weiterleiten
    return {
        **input,
        "available_margin": account.get("margin_free"),
        "existing_positions_count": len(positions) if positions else 0
    }
```

**config_json-Beispiel:**
```json
{
  "min_confidence": 0.65,
  "max_spread": 25,
  "max_positions": 1,
  "min_margin_level_pct": 150
}
```

Dieser einzelne EC übernimmt Signal-Filterung, Konfidenz-Gating, Spread-Filterung, Positions-Begrenzung und Margin-Prüfung — alles in einem schnellen Python-Skript ohne LLM-Aufruf.

---

## Verkettete ECs

ECs können verkettet werden: EC A veröffentlicht `ec_output` → Event Routing sendet es an EC B → EC B verarbeitet und veröffentlicht ein weiteres `ec_output` → BA-Agent.

Das ist nützlich wenn unterschiedliche Belange in unabhängige Skripte getrennt werden sollen:

```
AA-Agent → EC-FILTER (Signalprüfung) → EC-ENRICH (Datenanreicherung) → BA-Agent
```

Jeder EC in der Kette kann None zurückgeben um den Workflow an einem beliebigen Punkt zu stoppen.

Verkettung in Event Routing konfigurieren:
- `analysis_result` von AA → EC-FILTER routen
- `ec_output` von EC-FILTER → EC-ENRICH routen
- `ec_output` von EC-ENRICH → BA routen

---

## Speichern und Hot Reload

Beim Speichern eines ECs (Update-Button):
1. Skript und Konfiguration werden in die Systemkonfiguration geschrieben
2. Der EC wird sofort im laufenden System neu geladen
3. Das nächste auslösende Ereignis wird die neue Skript-Version ausführen

**Vor dem Testen speichern:** Der Test-Tab führt immer die gespeicherte Version aus. Wenn das Skript bearbeitet und ein Test ohne Speichern ausgeführt wird, wird die alte Version getestet. Immer zuerst speichern.

Hot Reload ist sicher und beeinflusst keine aktuell laufenden EC-Instanzen. Laufende oder ausstehende Ausführungen werden mit dem alten Skript abgeschlossen; nachfolgende Trigger verwenden die neue Version.

---

## Häufige Probleme beheben

### EC läuft aber produziert kein ec_output

Prüfen ob das Skript für den erwarteten Fall ein Dict (nicht None) zurückgibt. Temporär eine Debug-Rückgabe hinzufügen:

```python
async def main(input, config, tools):
    # Temporär: alles zurückgeben um zu sehen was ankommt
    return {"debug": True, "input_received": input}
```

Test-Tab mit repräsentativer Payload zur Überprüfung verwenden.

### EC löst einen KeyError aus

Die Input-Payload enthielt den erwarteten Schlüssel nicht. `.get()` mit einem Standard-Wert verwenden:

```python
# Unsicher
signal = input["order_start_signal"]

# Sicher
signal = input.get("order_start_signal", "NO")
```

### EC läuft in Timeout

Das Skript hat `script_timeout_seconds` überschritten. Häufige Ursachen:
- Ein Tool-Aufruf der hängt (Broker antwortet nicht)
- Eine Schleife die nicht terminiert
- `ask_llm()` dauert zu lange

`script_timeout_seconds` in tool_config erhöhen wenn das Skript legitim mehr Zeit benötigt, oder die Grundursache untersuchen.

### ask_llm gibt unerwarteten Inhalt zurück

`response.content` ist ein roher String vom LLM. Prüfen ob die Parse-Logik Variationen behandelt: `"JA"`, `"Ja"`, `"JA, dieser Trade sieht gut aus"`. `.strip().upper()` verwenden und mit `"JA" in antwort` statt `antwort == "JA"` prüfen.

---

## Test-Tab im Detail

### Effektiver Test-Workflow

1. **Repräsentative Payload erstellen:** Eine typische `analysis_result`-Payload verwenden die einem echten AA-Agenten-Output ähnelt. Sicherstellen dass alle Felder enthalten sind die das Skript prüft.

2. **Edge Cases testen:**
   - Payload mit `order_start_signal = "NO"` — EC sollte None zurückgeben
   - Payload mit `decision = "NEUTRAL"` — EC sollte None zurückgeben
   - Payload mit `confidence = 0.3` (unter Schwellenwert) — EC sollte None zurückgeben
   - Payload mit `spread = 50` (über max_spread) — EC sollte None zurückgeben
   - Vollständig valide Payload — EC sollte das Dict weiterleiten

3. **Latenz beobachten:** Das Output-Panel zeigt `latency_ms`. Tool-Aufrufe (wie `get_open_positions`) fügen echte Netzwerklatenz hinzu. Wenn die Gesamt-EC-Latenz 500ms überschreitet, erwägen ob alle Tool-Aufrufe wirklich nötig sind.

4. **Output verifizieren:** Prüfen dass das zurückgegebene Dict alle erwarteten Felder enthält, speziell wenn Datenanreicherung durchgeführt wird.

### Warum Tests fehlschlagen können

- **Skript nicht gespeichert:** Die gespeicherte Version läuft, nicht die aktuelle Editor-Version
- **Tool nicht in allowed_tools:** Tool-Aufrufe werden abgelehnt wenn das Tool nicht in `tool_config.allowed_tools` steht
- **Broker nicht erreichbar:** Wenn der Broker offline ist schlagen Tool-Aufrufe fehl
- **Ungültige JSON-Payload:** Der Input-Editor muss gültiges JSON enthalten

---

## Zusammenfassung: EC vs. Agent

| Merkmal | Event Composer (EC) | Agent |
|---|---|---|
| LLM-Aufruf | Optional (`ask_llm()`) | Immer |
| Trigger-Typen | Ereignisse, Timer, Kerze | Ereignisse, Timer, Kerze |
| Snapshot-Profil | Nicht unterstützt | Unterstützt |
| Skript-Sprache | Python (`async def main`) | System Prompt (natürliche Sprache) |
| Ausführungsgeschwindigkeit | Schnell (kein Pflicht-LLM) | Langsamer (LLM bei jedem Lauf) |
| Kosten | Niedrig (nur Tools, LLM optional) | Höher (LLM bei jedem Lauf) |
| Am besten für | Filterung, Routing, Anreicherung | Analyse, Entscheidungsfindung |
| Gibt zurück | `dict` (weiter) oder `None` (stopp) | Veröffentlicht Ereignis mit LLM-Output |
