[Zurück zu Config](ui.config.de.md)

# Decision Prompt

Die Seite `Decision Prompt` verwaltet benannte Prompt-Profile, die steuern, welchen Instruktionstext ein Agent als System-Prompt während eines snapshotgestützten Laufs erhält.

Jeder snapshotgestützte Agentenzyklus hat zwei konfigurierbare Ebenen:

1. das **Snapshot-Profil** — welche Daten gesammelt und weitergegeben werden
2. das **Decision-Prompt-Profil** — welche Instruktion das LLM erhält

Diese Seite betrifft Ebene 2.

## Wann der Decision Prompt verwendet wird

Nachdem der Snapshot von der Snapshot-Engine aufgebaut wurde, initiiert der AA-Agent einen LLM-Aufruf. Der Aufruf ist wie folgt strukturiert:

- **System-Message**: der vom Decision-Prompt-Profil ausgewählte und assemblierte Text (die Instruktion an das LLM — die "Spielregeln")
- **User-Message**: der assemblierte Snapshot (die Marktdaten, über die das LLM argumentiert)

Das Decision-Prompt-Profil bestimmt, was in der System-Message erscheint. Das ist der direkteste Hebel zur Steuerung des LLM-Verhaltens: Es definiert die Strategie, den Argumentationsrahmen, das Ausgabeformat und die Entscheidungskriterien.

## Was ein Decision-Prompt-Profil ist

Ein Decision-Prompt-Profil ist ein benannter Satz aus folgenden Werten:

| Feld | Zweck |
|---|---|
| `name` | Eindeutige Kennung, über die das Profil einem Agenten zugewiesen wird |
| `description` | Kurze lesbare Bezeichnung, die in Listen und Dropdowns erscheint |
| `fallback_snapshot_profile` | Optional: Snapshot-Profil für Selector-Script-Daten, wenn kein reguläres Snapshot-Profil zugewiesen ist |
| `script` | Python-Selector-Script, das bestimmt, welche Prompt-Version verwendet wird |
| `prompts` | Array von Prompt-Einträgen; das Script wählt einen über seine `id` aus |

Jeder Eintrag in `prompts` enthält:

| Feld | Zweck |
|---|---|
| `id` | Ganzzahl, mit der das Selector-Script diesen Eintrag identifiziert |
| `description` | Lesbare Bezeichnung |
| `mode` | Wie der Prompt in den System-Prompt integriert wird (`replace` oder `append`) |
| `prompt` | Instruktionstext an das LLM; darf `{Platzhalter}`-Tokens enthalten |
| `use_placeholders` | Wenn aktiviert, werden `{key}`-Tokens im Prompt durch Werte aus `placeholders` ersetzt |

Alle Profile werden in `system.json5` unter dem Schlüssel `decision_prompt_profiles` gespeichert.

---

## Wie die Prompt-Auswahl funktioniert

Wenn ein Agent einen snapshotgestützten Zyklus ausführt:

1. Der Snapshot wird aufgebaut und als User-Message an das LLM übergeben.
2. Das **Selector-Script** läuft. Der Snapshot steht über mehrere Variablen bereit (s. unten).
3. Das Script schreibt eine Ganzzahl in `result` — das ist die zu verwendende Prompt-ID.
4. Das System sucht den Prompt-Eintrag mit dieser ID und verwendet dessen Text und Mode.
5. Stimmt keine ID überein, wird der erste Eintrag der Liste als Fallback verwendet.

Das Standard-Script `result = 1` wählt immer den Prompt mit der id `1`.

---

## Selector-Script

Das Selector-Script ist ein kurzes Python-Script, das bei jeder Ausführung eines Agentenzyklus läuft. Es bestimmt, welche Prompt-Version verwendet wird, und kann optional Platzhalter-Werte befüllen.

### Script-Variablen

Das Selector-Script hat folgende Variablen vorbelegt:

| Variable | Inhalt |
|---|---|
| `snapshot` | Das vollständige Snapshot-Dict, wie es das Snapshot-Profil aufgebaut hat |
| `tool_outputs` | Kürzel: `snapshot["tool_outputs"]` — die verarbeiteten Tool-Block-Ergebnisse |
| `assembled` | Kürzel: `snapshot["assembled"]` — die Ausgabe des Assembly-Transform-Scripts, falls konfiguriert |
| `placeholders` | Ein leeres `{}`-Dict; hier Werte eintragen, um `{Platzhalter}` im Prompt zu befüllen |
| `result` | Vorbelegt mit `1`; mit der gewünschten Prompt-ID überschreiben |

`tool_outputs` und `assembled` sind leere Dicts `{}`, wenn die entsprechenden Schlüssel im Snapshot nicht vorhanden sind.

Das Script hat Zugriff auf Standard-Python-Builtins: `int`, `float`, `str`, `dict`, `list`, `len`, `max`, `min`, `round`, `sorted`, `any`, `all`, `enumerate`, `zip`, `isinstance` u. a. Netzwerkzugriff und Datei-I/O sind nicht verfügbar.

Die Snapshot-Struktur, die im **Test Snapshot**-Panel rechts angezeigt wird, ist genau das, was das Script als `snapshot` empfängt.

### Beispiel: immer Prompt 1 verwenden

```python
result = 1
```

### Beispiel: Prompt anhand des Kontosaldos wählen

```python
balance = tool_outputs.get("get_account_status_1", {}).get("balance", 0)
result = 2 if balance < 1000 else 1
```

Prompt 2 wird gewählt, wenn der Kontostand unter 1000 liegt, sonst Prompt 1.

### Beispiel: Prompt anhand offener Positionen wählen

```python
positions = tool_outputs.get("get_open_positions_2", [])
result = 2 if len(positions) > 0 else 1
```

### Beispiel: Prompt anhand der Handelssession wählen

```python
session = snapshot.get("session", {})
is_london = session.get("london_open", False)
is_newyork = session.get("newyork_open", False)

if is_london and is_newyork:
    result = 3  # London/NY-Überschneidung — höchste Liquidität
elif is_london or is_newyork:
    result = 1  # Aktive Session — Standard-Prompt
else:
    result = 2  # Nebenstunden — Niedriger-Liquidität-Prompt
```

### Beispiel: Prompt anhand der ATR-Volatilität wählen

```python
atr = snapshot.get("atr_14", 0)
atr_hoch = snapshot.get("atr_high_threshold", 0.0020)
atr_niedrig = snapshot.get("atr_low_threshold", 0.0005)

if atr > atr_hoch:
    result = 3  # Hohe Volatilität — engerer Filter-Prompt
elif atr < atr_niedrig:
    result = 2  # Niedrige Volatilität — kein Trading-Prompt
else:
    result = 1  # Normale Volatilität — Standard-Prompt
```

---

## Platzhalter im Prompt

Ist **Placeholders** für einen Prompt-Eintrag aktiviert, werden `{key}`-Tokens im Prompt-Text durch Werte aus dem `placeholders`-Dict ersetzt, bevor der Prompt an das LLM gesendet wird.

Das Script ist dafür zuständig, `placeholders` zu befüllen. Die Werte können beliebige Strings sein — auch berechnete oder umgewandelte Werte, nicht nur rohe Zahlen aus dem Snapshot.

### Platzhalter im Selector-Script setzen

```python
acc = tool_outputs.get("get_account_status_1", {})
balance = acc.get("balance", 0)
positions = tool_outputs.get("get_open_positions_2", [])

placeholders["broker"]     = snapshot.get("broker_name", "")
placeholders["saldo"]      = str(balance)
placeholders["waehrung"]   = acc.get("currency", "USD")
placeholders["positionen"] = str(len(positions))
placeholders["status"]     = "ausreichend" if balance > 500 else "kritisch"

result = 1
```

### Prompt-Text mit Platzhaltern

```
Du verwaltest Konto {broker}. Aktueller Saldo: {saldo} {waehrung}.
Offene Positionen: {positionen}. Kontostatus: {status}.
Entscheide, ob eine neue Position eröffnet oder abgewartet werden soll.
```

Nach der Ersetzung erhält das LLM:

```
Du verwaltest Konto OXS_T. Aktueller Saldo: 9824.93 USD.
Offene Positionen: 0. Kontostatus: ausreichend.
Entscheide, ob eine neue Position eröffnet oder abgewartet werden soll.
```

### Erweitertes Platzhalter-Beispiel für den Forex-Handel

```python
# Marktdaten aus dem Snapshot
symbol = snapshot.get("symbol", "UNBEKANNT")
zeitrahmen = snapshot.get("timeframe", "M5")
trend = snapshot.get("trend_direction", "UNBEKANNT")
atr = snapshot.get("atr_14", 0)
session = snapshot.get("session_name", "UNBEKANNT")

# Kontodaten aus den Tools
acc = tool_outputs.get("get_account_status_1", {})
balance = acc.get("balance", 0)
equity = acc.get("equity", balance)
freie_margin = acc.get("margin_free", 0)

# Abgeleitete Werte
atr_pips = round(atr / 0.0001, 1)
risiko_kapazitaet = "HOCH" if equity > 5000 else ("MITTEL" if equity > 2000 else "NIEDRIG")

# Platzhalter befüllen
placeholders["symbol"]       = symbol
placeholders["zeitrahmen"]   = zeitrahmen
placeholders["trend"]        = trend
placeholders["atr_pips"]     = str(atr_pips)
placeholders["session"]      = session
placeholders["saldo"]        = f"{balance:.2f}"
placeholders["equity"]       = f"{equity:.2f}"
placeholders["freie_margin"] = f"{freie_margin:.2f}"
placeholders["kapazitaet"]   = risiko_kapazitaet

result = 1
```

Prompt mit allen Platzhaltern:

```
Du bist ein erfahrener Forex-Trader und analysierst {symbol} auf dem {zeitrahmen}-Chart.
Aktuelle Session: {session}.
Trendrichtung: {trend}.
ATR (14): {atr_pips} Pips.

Kontostand: Saldo {saldo} USD | Equity {equity} USD | Freie Margin {freie_margin} USD.
Risikokapazität: {kapazitaet}.

Deine Aufgabe ist es, den aktuellen Markt-Snapshot zu analysieren und eine strukturierte Handelsentscheidung zurückzugeben.
```

### Platzhalter-Regeln

- Nur Schlüssel, die in `placeholders` vorhanden sind, werden ersetzt; unbekannte Tokens wie `{foo}` bleiben erhalten.
- `None`-Werte werden zu einem leeren String aufgelöst.
- Platzhalter sind nur aktiv, wenn **Placeholders** für diesen Prompt-Eintrag aktiviert ist.
- Ist **Placeholders** deaktiviert, wird der Prompt-Text wörtlich übergeben, `{Tokens}` eingeschlossen.

---

## Mode — replace vs append

### replace

Der Prompt-Text ersetzt den Basis-System-Prompt des Agenten vollständig.

Verwende diesen Modus, wenn:
- du die volle Kontrolle über die gesamte LLM-Instruktion haben willst
- der Agent einen generischen oder leeren Basis-Prompt hat und dieser Prompt die vollständige Instruktion darstellt
- du einen zweckgebundenen Prompt für einen bestimmten Agenten- oder Strategietyp schreibst

Das ist die häufigste Einstellung.

### append

Der Prompt-Text wird an den Basis-System-Prompt des Agenten angehängt.

Verwende diesen Modus, wenn:
- der Agent bereits eine permanente Basisinstruktion hat, die immer vorhanden sein soll
- der Decision Prompt situationsbezogene Anweisungen ergänzt
- du einen gemeinsamen Basis-Prompt über mehrere Agenten teilen und nur die angehängte Ebene variieren willst

Beispielstruktur mit append-Modus:

**Agenten-Basis-System-Prompt** (in Agent Config gesetzt):
```
Du bist OpenForexAI, ein automatisiertes Forex-Handelssystem.
Du gibst immer strukturierte JSON-Antworten zurück.
Du weichst nie vom vorgegebenen Ausgabeformat ab.
```

**Decision Prompt (append-Modus)**:
```
Die aktuelle Handelssession ist {session}.
Strategiefokus heute: {trend}-Folgeeinstiege auf {symbol}.
Hochkonfidente Setups mit R:R über 1,5 bevorzugen.
```

Kombinierter Prompt, den das LLM erhält:
```
Du bist OpenForexAI, ein automatisiertes Forex-Handelssystem.
Du gibst immer strukturierte JSON-Antworten zurück.
Du weichst nie vom vorgegebenen Ausgabeformat ab.

Die aktuelle Handelssession ist London.
Strategiefokus heute: BULLISH-Folgeeinstiege auf EURUSD.
Hochkonfidente Setups mit R:R über 1,5 bevorzugen.
```

---

## Fallback-Snapshot-Profil

Ein Decision-Prompt-Profil kann optional auf ein **Fallback-Snapshot-Profil** verweisen.

Das Feld `fallback_snapshot_profile` im Profilformular auf den Namen eines vorhandenen Snapshot-Profils setzen.

**Wann es greift:** wenn einem Agenten ein Decision-Prompt-Profil zugewiesen ist, aber kein Snapshot-Profil. In einem normalen snapshotgestützten Zyklus liefert der reguläre Snapshot Daten sowohl an das Selector-Script als auch an das LLM. Ohne zugewiesenes Snapshot-Profil erhält das LLM keine Snapshot-Daten — das Selector-Script benötigt aber trotzdem Marktdaten für eine sinnvolle Entscheidung.

Das Fallback-Snapshot wird mit dem genannten Snapshot-Profil aufgebaut. Seine Daten stehen dem Selector-Script über dieselben Variablen zur Verfügung (`snapshot`, `tool_outputs`, `assembled`, `placeholders`). Der Fallback-Snapshot wird **nicht** als User-Message an das LLM weitergegeben — er dient ausschließlich dazu, die Prompt-Auswahl und die Platzhalter-Befüllung zu steuern.

**Anwendungsfall:** ein Agent, dessen LLM für einen anderen Zweck als die Marktanalyse eingesetzt wird (z. B. Trade-Verwaltung, Kommentierung), der aber trotzdem anhand des aktuellen Kontostands oder der Marktlage einen Prompt auswählen soll.

---

## Profile und Agentenzuweisung

Ein Profil ist nicht eigenständig aktiv — es muss einem Agenten zugewiesen werden.

Die Zuweisung erfolgt in `Config → Agent Config`. Jeder Agent hat ein Feld `decision_prompt_profile`, das ein Profil über seinen Namen referenziert.

Ablauf:

1. Profil hier unter `Decision Prompt` anlegen oder bearbeiten.
2. Zu `Config → Agent Config` wechseln.
3. Agenten auswählen.
4. Feld `decision_prompt_profile` auf den Profilnamen setzen.
5. Speichern.

Mehrere Agenten können dasselbe Profil verwenden. Eine Änderung am Profil wirkt sich beim nächsten Lauf auf alle Agenten aus, die es referenzieren.

---

## Praktische Anwendungsfälle

### Anwendungsfall 1: Einzelne Strategie, immer derselbe Prompt

Die einfachste Konfiguration: ein Prompt, immer gewählt.

```python
result = 1
```

Prompt 1 (replace-Modus): eine vollständige, in sich geschlossene Trading-Strategie-Instruktion. Keine Platzhalter nötig.

Geeignet, wenn:
- eine einzelne, stabile Strategie vorliegt
- ein oder zwei Paare mit identischer Logik gehandelt werden
- die Strategie sich nicht an Marktbedingungen anpassen muss

### Anwendungsfall 2: Strategie wechselt je nach Session

Verschiedene Sessions haben unterschiedliche Marktcharakteristika. London tendiert zum Trend, die asiatische Session zur Seitwärtsbewegung.

```python
session = snapshot.get("session_name", "")
if "london" in session.lower() or "newyork" in session.lower():
    result = 1  # Trendfolgender Prompt
else:
    result = 2  # Range-Trading-Prompt
```

Prompt 1: weist das LLM an, Trendfortsetzungs-Einstiege zu bevorzugen, höhere R:R-Ziele.
Prompt 2: weist das LLM an, Mean-Reversion-Einstiege nahe Range-Grenzen zu bevorzugen, engere R:R.

### Anwendungsfall 3: Dynamischer Prompt mit Kontokontext

Für verwaltete Konten oder risikobewusstes Trading, bei dem der Prompt die aktuelle Kontogesundheit widerspiegeln soll:

```python
acc = tool_outputs.get("get_account_status_1", {})
drawdown_pct = acc.get("drawdown_percent", 0)

placeholders["symbol"] = snapshot.get("symbol", "")
placeholders["session"] = snapshot.get("session_name", "")

if drawdown_pct > 10:
    result = 3  # Defensiver Modus: sehr konservativ, Kapitalschutz Priorität
    placeholders["modus"] = "DEFENSIV"
elif drawdown_pct > 5:
    result = 2  # Vorsichtiger Modus: Guidance für reduzierte Positionsgröße
    placeholders["modus"] = "VORSICHTIG"
else:
    result = 1  # Normaler Modus: Standardstrategie
    placeholders["modus"] = "NORMAL"
```

Jede Prompt-Version weist das LLM unterschiedlich bezüglich Risikobereitschaft und Einstiegskriterien an.

### Anwendungsfall 4: Multi-Paar-Spezialisierung

Verschiedene Paare profitieren von unterschiedlichen Instruktionen. GBPUSD hat ein anderes typisches Spread-, Volatilitäts- und Newssensitivitätsprofil als EURUSD.

```python
symbol = snapshot.get("symbol", "")
placeholders["symbol"] = symbol
placeholders["session"] = snapshot.get("session_name", "")

if symbol == "GBPUSD":
    result = 2  # GBP-spezifischer Prompt mit Guidance für breiteren Spread
elif symbol == "USDJPY":
    result = 3  # JPY-spezifischer Prompt mit Carry-Trade-Kontext
else:
    result = 1  # Standard-EURUSD / generischer Prompt
```

---

## Den Editor verwenden

### Linkes Panel

Enthält das Profilformular: `name`, `description`, das Selector-Script und die Prompts-Liste.

**Selector Script** — die Script-Textarea mit einem **Copy**-Button und einem **Test**-Button. Der Test-Button öffnet das Testfenster (s. unten).

**Prompts** — auf **+ New Prompt** klicken, um einen neuen Eintrag hinzuzufügen. Jede Karte enthält:
- `ID` — Ganzzahl (muss innerhalb des Profils eindeutig sein)
- `Description` — lesbare Bezeichnung
- `Mode` — `replace` oder `append`
- Checkbox **Placeholders** — aktiviert `{Token}`-Ersetzung für diesen Eintrag
- Prompt-Textarea mit **Copy**-Button
- Buttons **Duplicate** und **Delete**

### Rechtes Panel — Test Snapshot

Einen **Agenten** und optional ein **Snapshot-Profil** aus den Dropdowns wählen, dann auf **Load Snapshot** klicken, um einen Live-Snapshot aus dem aktuellen Marktkontext des Agenten zu generieren. Das Snapshot-JSON wird mit einem **Copy**-Button angezeigt.

Der geladene Snapshot wird beim Öffnen des Testfensters vorausgefüllt.

### Speichern

- **Update** — überschreibt das aktuell gewählte Profil
- **Save as New** — erstellt ein neues Profil unter dem im Feld `name` eingetragenen Namen
- **Delete** — entfernt das gewählte Profil aus `system.json5`

Umbenennen: `name` ändern und auf **Update** klicken. Der alte Eintrag wird ersetzt. Agenten, die den alten Namen referenziert haben, müssen in `Agent Config` aktualisiert werden.

### Validierung

Das Speichern ist blockiert, bis:
- `name` nicht leer und über alle Profile hinweg eindeutig ist
- `description` nicht leer ist
- Prompt-IDs innerhalb des Profils eindeutig sind

---

## Script testen

**Test** neben dem Selector-Script klicken, um das Testfenster zu öffnen.

**Linke Seite — Snapshot Input**
Bearbeitbares JSON, vorausgefüllt aus dem rechten Panel (oder `{}`, wenn kein Snapshot geladen wurde). Frei bearbeiten, um verschiedene Bedingungen zu simulieren.

**Rechte Seite — Script Result**
**Run** klicken, um das Script auszuführen. Das Ergebnis zeigt:
- die in `result` geschriebene Ganzzahl
- den übereinstimmenden Prompt-Eintrag (id, description, mode, bis ~400 Zeichen Prompt-Text)
- ist **Placeholders** für den Eintrag aktiv: einen **Resolved**-Bereich mit dem Prompt-Text nach der `{Token}`-Ersetzung, inklusive eigenem **Copy**-Button
- etwaige Script-Fehler (haben keine Auswirkung auf das gespeicherte Profil)

Das Snapshot-JSON kann bearbeitet und das Script wiederholt ausgeführt werden, um verschiedene Szenarien zu testen.

### Test-Tipps

- Einen echten Snapshot aus dem Test-Snapshot-Panel kopieren und dann bestimmte Felder ändern, um Randfälle zu testen
- Mit einem leeren Snapshot `{}` testen, um zu prüfen, ob das Script fehlende Daten korrekt behandelt
- Alle Zweige testen — wenn das Script drei `if`-Bedingungen hat, alle drei testen
- Platzhalter-Werte in der Resolved-Ansicht prüfen, bevor in den Live-Betrieb gegangen wird

---

## Laufzeit-Override

Die Funktion `Agent Chat → Execute` unterstützt den Parameter `decision_prompt_profile_override`. Damit kann ein geändertes Profil für einen einzelnen Lauf getestet werden, ohne es in `system.json5` zu speichern. Der Override gilt nur für diesen Lauf und hat keine Auswirkung auf andere Agenten oder über den Lauf hinaus.

---

## Richtlinien für das Schreiben von Prompts

Ein gut geschriebener Decision Prompt ist spezifisch, strukturiert und eindeutig. Folgende Richtlinien gelten:

**Ausgabeformat explizit definieren.**
Das LLM muss eine maschinenlesbare Antwort zurückgeben. Die genaue JSON-Struktur definieren:

```
Gib deine Entscheidung als JSON mit dieser genauen Struktur zurück:
{
  "signal": "BUY" | "SELL" | "NO_SIGNAL",
  "confidence": <Ganzzahl 0-100>,
  "entry": <float>,
  "stop_loss": <float>,
  "take_profit": <float>,
  "reasoning": "<String>"
}
```

**Definieren, was ein gültiges Signal ausmacht.**
Das nicht der Interpretation überlassen:

```
Nur BUY oder SELL zurückgeben, wenn ALLE folgenden Bedingungen erfüllt sind:
- Trendrichtung durch mindestens zwei der folgenden bestätigt: EMA-Ausrichtung, Strukturbruch, Momentum
- Der Einstiegspunkt liegt an einem validen Support-/Resistance-Level oder Swing-Punkt
- ATR-basierter Stop-Abstand liegt zwischen 1,0x und 2,5x ATR
- Keine hochimpact-News-Events innerhalb von 30 Minuten
Sonst NO_SIGNAL zurückgeben.
```

**Konfidenz klar definieren.**
Das LLM mit einer Rubrik für Konfidenzwerte ausstatten:

```
Konfidenz-Bewertung:
90-100: Mehrere bestätigende Faktoren, Lehrbuch-Setup, liquiditätsstarke Session
70-89: Klarer Richtungsbias mit mindestens zwei bestätigenden Faktoren
50-69: Signal vorhanden, aber ein Faktor unsicher oder widersprüchlich
Unter 50: Stattdessen NO_SIGNAL zurückgeben
```

**Strategietyp spezifizieren.**
Ein trendfolgender Prompt und ein Mean-Reversion-Prompt sind grundlegend verschieden:

```
Strategie: Trendfortsetzung
Nur in Richtung des übergeordneten Trends einsteigen.
Keine Moves faden. Nicht an Extremen einsteigen.
Pullbacks zu Strukturpunkten als Einstiegsmöglichkeiten suchen.
```

Vorgesehener Screenshot:
- [Decision Prompt Editor mit Multi-Version-Profil](image/ui-17-decision-prompt-editor.png)
