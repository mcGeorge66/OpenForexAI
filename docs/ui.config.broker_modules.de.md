[Zurück zu Config](ui.config.de.md)

# Broker Modules

Broker Modules ist ein direkter Editor für die Konfigurationsdateien einzelner Broker-Adapter-Module. Jeder Broker-Adapter hat eine eigene Konfigurationsdatei, die hier ausgewählt und bearbeitet werden kann. Diese Seite richtet sich an Operatoren, die Verbindungsparameter, Symbolzuordnungen, Polling-Intervalle, Synchronisierungseinstellungen oder adapterspezifische Optionen für ihre Broker-Verbindungen direkt anpassen müssen.

---

## Inhaltsverzeichnis

1. [Broker-Architektur-Übersicht](#broker-architektur-übersicht)
2. [Oberfläche](#oberfläche)
3. [Speicherverhalten](#speicherverhalten)
4. [Wie Broker-Module registriert werden](#wie-broker-module-registriert-werden)
5. [Gemeinsame Konfigurationsfelder](#gemeinsame-konfigurationsfelder)
6. [MT5-Adapter-Konfiguration](#mt5-adapter-konfiguration)
7. [OANDA-Adapter-Konfiguration](#oanda-adapter-konfiguration)
8. [Das short_name-Feld](#das-short_name-feld)
9. [Candle-Polling und Synchronisierung](#candle-polling-und-synchronisierung)
10. [broker_candle_utc_offset_hours und das Broker-Modul](#broker_candle_utc_offset_hours-und-das-broker-modul)
11. [Symbol-Maps](#symbol-maps)
12. [Mehrere Broker-Module](#mehrere-broker-module)
13. [Typischer Ablauf](#typischer-ablauf)
14. [Broker-Verbindungsprobleme beheben](#broker-verbindungsprobleme-beheben)

---

## Broker-Architektur-Übersicht

Broker-Adapter sind die Grenze zwischen OpenForexAI und der Außenwelt. Jeder Adapter verwaltet:

- **Candle-Synchronisierung**: Polling beim Broker für neue M5-Kerzen und Speicherung in der Datenbank
- **Konto-Anfragen**: Kontosaldo, Eigenkapital, Margin und offene Positionen auf Anfrage bereitstellen
- **Order-Ausführung**: Trades platzieren, modifizieren und schließen
- **Echtzeit-Updates**: Kerzen-Updates und Positionsänderungen auf dem Event Bus veröffentlichen

### Event-Bus-Integration

Broker-Adapter registrieren sich auf dem Event Bus als `{BROKER}-ALL___-BK-CONN`. Für Broker `OXS_T` lautet die Bus-Mitglieds-ID `OXS_T-ALL___-BK-CONN`. Routing-Regeln senden Order-Anfragen, Kontostatus-Anfragen und Positions-Anfragen an diese ID.

Der Adapter empfängt:
- `order_request` → Order ausführen
- `account_status_request` → aktuellen Kontozustand abfragen und zurückgeben
- `positions_request` → Liste offener Positionen zurückgeben
- `position_close_request` → angegebene Position schließen
- `order_modify_request` → SL/TP einer offenen Position modifizieren

Der Adapter veröffentlicht:
- `m5_candle_saved` → nach jeder neuen gespeicherten Kerze
- `account_status_response` → als Antwort auf account_status_request
- `positions_response` → als Antwort auf positions_request
- `order_result` → nach einem Order-Platzierungsversuch
- `position_opened` / `position_closed` → proaktive Positionszustandsänderungen

---

## Oberfläche

### Kopfleiste

| Element | Funktion |
|---------|----------|
| **Modul-Auswahl** | Dropdown mit allen Broker-Modulen aus `modules.broker` in `system.json5` |
| **Dateipfad** | Vollständiger Pfad zur Konfigurationsdatei des gewählten Moduls |
| **Refresh** | Aktuelle Dateiversion von der Festplatte neu laden (nur aktiv wenn Modul gewählt) |
| **Save** | Validieren und Datei schreiben (nur aktiv wenn Modul gewählt) |
| **Position** | Aktuelle Cursor-Position als Zeile:Spalte |

### Modul-Auswahl

Das Dropdown wird aus dem `modules.broker`-Array in `system.json5` befüllt. Jeder Eintrag ist ein Dateipfad; das Dropdown zeigt den Dateinamen-Teil (z.B. `oxs_mt5.json5`). Nach der Auswahl lädt der Editor den Dateiinhalt.

### Editor-Textarea

Freitext-JSON5-Bearbeitung mit Syntax-Hervorhebung (Keys: Cyan, Strings: Grün, Booleans: Amber, Null: Grau, Zahlen: Lila).

### Status-Meldungen

- **„Saved."** — Datei erfolgreich geschrieben
- **Fehlermeldung** — Parse-Fehler; Datei nicht geschrieben

---

## Speicherverhalten

1. Inhalt wird als JSON5 geparsed
2. Ergebnis der obersten Ebene muss ein JSON-Objekt sein
3. Bei Fehler: Fehlermeldung angezeigt, Datei nicht geschrieben
4. Bei Erfolg: Datei auf Festplatte geschrieben

Der Broker-Adapter übernimmt neue Konfiguration beim nächsten Systemstart oder Adapter-Reload. Verbindungsparameter-Änderungen (Endpunkt, Zugangsdaten) erfordern einen vollständigen Neustart.

---

## Wie Broker-Module registriert werden

Pfad-Kettenprozess für ein Broker-Modul:

1. `config/system.json5` hat `modules.broker: ["config/broker/oxs_mt5.json5"]`
2. Beim Start liest das System diesen Pfad und lädt `oxs_mt5.json5`
3. Der Adapter wird instanziiert und als `{short_name}-ALL___-BK-CONN` auf dem Bus registriert
4. Das `short_name`-Feld in der Konfig bestimmt das Broker-Segment der Bus-ID
5. Routing-Regeln und Agent-IDs die diesen Broker referenzieren verwenden den `short_name`-Wert

Beispiel: `short_name: "OXS_T"` → Bus-ID `OXS_T-ALL___-BK-CONN`, und Agenten für diesen Broker haben IDs wie `OXS_T-EURUSD-AA-ANLYS`.

---

## Gemeinsame Konfigurationsfelder

Felder die über alle Broker-Adapter-Typen geteilt werden:

| Feld | Typ | Pflicht | Beschreibung |
|------|-----|---------|--------------|
| `adapter` | string | ja | Adapter-Implementierung: `mt5`, `oanda` oder benutzerdefiniert |
| `short_name` | string | ja | Broker-Bezeichner in allen Agent-IDs und Bus-Routing. Siehe dedizierten Abschnitt. |
| `enabled` | boolean | nein | Ob dieser Adapter beim Systemstart gestartet werden soll. Standard: `true`. |
| `sync_interval_seconds` | integer | nein | Wie oft auf neue Kerzen gepollt wird. Standard: 60. |
| `pairs` | array | ja | Liste der Forex-Paare, die dieser Adapter überwacht. |
| `timeframes` | array | nein | Zu synchronisierende Zeitrahmen. Standard: `["M5", "M15", "H1"]`. |
| `max_candle_sync_count` | integer | nein | Maximale Kerzen in einem einzelnen Sync-Request. Standard: 500. |
| `candle_gap_fill_lookback_bars` | integer | nein | Lookback-Bars zur Lückenprüfung beim Start. Standard: 200. |
| `connection_timeout_seconds` | integer | nein | Verbindungsversuch-Timeout. Standard: 30. |
| `request_timeout_seconds` | integer | nein | Request-Timeout. Standard: 60. |

---

## MT5-Adapter-Konfiguration

Der MT5-Adapter verbindet sich mit einem MetaTrader-5-Terminal, das auf derselben Maschine läuft. MT5 muss installiert, mit dem Broker-Konto eingeloggt und das MT5-Python-Bridge aktiviert sein.

```json5
{
  adapter: "mt5",
  short_name: "OXS_T",
  enabled: true,
  
  // MT5-Verbindung
  mt5_path: "C:/Program Files/MetaTrader 5/terminal64.exe",
  login: 12345678,
  password_env: "MT5_OXS_T_PASSWORD",
  server: "OXSTrading-Server",
  
  // Paare und Zeitrahmen
  pairs: ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD"],
  timeframes: ["M5", "M15", "H1"],
  
  // Sync-Einstellungen
  sync_interval_seconds: 60,
  max_candle_sync_count: 500,
  candle_gap_fill_lookback_bars: 200,
  
  // Order-Standards
  default_deviation_points: 10,
  default_magic_number: 20241001,
  
  // Symbol-Map (wenn Broker nicht-standardisierte Symbole verwendet)
  symbol_map: {
    "EURUSD": "EURUSDm",
    "GBPUSD": "GBPUSDm",
  }
}
```

### MT5-spezifische Felder

| Feld | Beschreibung |
|------|--------------|
| `mt5_path` | Pfad zur MT5-Terminal-Executable. Nur nötig wenn MT5 nicht am Standard-Installationsort ist. |
| `login` | MT5-Kontonummer. |
| `password_env` | Name der Umgebungsvariable mit dem MT5-Konto-Passwort. |
| `password` | Klartext-Passwort (nicht empfohlen). |
| `server` | MT5-Broker-Servername genau wie in MT5 angezeigt (Groß-/Kleinschreibung beachten). |
| `default_deviation_points` | Maximale Preisabweichung in Punkten für Market-Order-Ausführung. |
| `default_magic_number` | Magic-Nummer die allen vom System platzierten Orders beigefügt wird. Erlaubt Filterung von System-Orders gegenüber manuellen Orders in MT5. |
| `symbol_map` | Zuordnung von Standard-Paarnamen zu Broker-spezifischen Symbolen. |

### MT5-Verbindungsanforderungen

Der MT5-Adapter erfordert:
1. MetaTrader-5-Terminal auf der Maschine installiert, auf der OpenForexAI läuft
2. Terminal mit aktivem Konto eingeloggt
3. Auto-Trading im Terminal aktiviert
4. MT5-Python-Paket in der OpenForexAI-Python-Umgebung installiert (`pip install MetaTrader5`)
5. Das Terminal muss laufen wenn OpenForexAI startet

### MT5-Terminal-Zeit (Broker-Server-Zeit)

MT5-Kerzen-Zeitstempel sind in der Broker-Server-Lokalzeit. Die `broker_candle_utc_offset_hours`-Einstellung in `system.json5` muss mit dem Broker-Server-UTC-Offset übereinstimmen damit die Session-Filterung korrekt funktioniert. Für eine vollständige Erklärung siehe [System Config](ui.config.system_config.de.md).

---

## OANDA-Adapter-Konfiguration

Der OANDA-Adapter verbindet sich mit OANDAs REST-v20-API. Kein lokales Handels-Terminal erforderlich.

```json5
{
  adapter: "oanda",
  short_name: "OANDA",
  enabled: true,
  
  // OANDA-API-Verbindung
  account_id: "001-001-12345678-001",
  api_key_env: "OANDA_API_KEY",
  environment: "practice",   // oder "live"
  
  // Paare und Zeitrahmen
  pairs: ["EUR_USD", "GBP_USD", "USD_JPY"],
  timeframes: ["M5", "M15", "H1"],
  
  // Sync-Einstellungen
  sync_interval_seconds: 60,
  max_candle_sync_count: 500,
  
  // Symbol-Map (OANDA verwendet Unterstrich-Notation)
  symbol_map: {
    "EURUSD": "EUR_USD",
    "GBPUSD": "GBP_USD",
    "USDJPY": "USD_JPY",
  }
}
```

### OANDA-spezifische Felder

| Feld | Beschreibung |
|------|--------------|
| `account_id` | OANDA-Kontoidentifikator. Im OANDA Hub unter den Kontodetails zu finden. |
| `api_key_env` | Umgebungsvariablenname für den OANDA-API-Key (persönliches Zugriffstoken). |
| `api_key` | Klartext-API-Key (nicht empfohlen). |
| `environment` | `"practice"` für Demo/Paper-Trading, `"live"` für Echtgeld. |

### OANDA-Zeitzonenhinweis

Die OANDA-API gibt Kerzen-Zeitstempel in UTC zurück. Bei Verwendung des OANDA-Adapters `broker_candle_utc_offset_hours: 0` in `system.json5` setzen. Der Session-Filter vergleicht dann UTC-Kerzenzeiten mit UTC-Session-Grenzen ohne Offset.

---

## Das short_name-Feld

`short_name` ist das wichtigste Feld in einer Broker-Modul-Konfiguration. Es bestimmt:

1. **Die Broker-Bus-Mitglieds-ID**: `{short_name}-ALL___-BK-CONN`
2. **Alle Agent-IDs für diesen Broker**: `{short_name}-{PAAR}-AA-ANLYS`, `{short_name}-ALL___-BA-ANLYS` usw.
3. **Event-Routing-Templates**: Regeln die `{sender.broker}` verwenden lösen sich zu diesem Wert auf
4. **Log-Einträge**: Alle Logs für diesen Broker zeigen den short_name als Präfix

### short_name wählen

Regeln:
- Großbuchstaben
- Keine Leerzeichen (Unterstriche wenn nötig)
- 3–8 Zeichen (längere sind in Logs und IDs schwerer lesbar)
- Muss über alle konfigurierten Broker eindeutig sein
- Stabil — eine Änderung macht alle bestehenden Agent-IDs und Routing-Regeln ungültig

Beispiele:
- `OXS_T` — OXS-Trading-Broker
- `OANDA` — OANDA
- `IC_MKT` — IC Markets
- `FP_MKT` — FP Markets

### Was passiert wenn short_name geändert wird

Wenn `short_name` geändert wird nachdem das System bereits lief:
- Der Broker-Adapter registriert sich mit einer neuen Bus-ID
- Alle bestehenden Routing-Regeln die den alten Namen referenzieren funktionieren nicht mehr
- Alle Agent-IDs ändern sich — die Datenbank hat noch Einträge unter alten IDs
- Alle Agenten (AA, BA, EC) müssen ihre `id`-Felder aktualisieren

**Empfehlung**: `short_name` sorgfältig vor der ersten Verwendung wählen und danach nicht ändern.

---

## Candle-Polling und Synchronisierung

### Wie Candle-Sync funktioniert

1. Der Adapter führt eine Polling-Schleife alle `sync_interval_seconds` aus
2. Für jedes Paar und jeden Zeitrahmen in `pairs` × `timeframes` fragt er den Broker nach neuesten Kerzen
3. Neue Kerzen (noch nicht in der Datenbank) werden gespeichert
4. Für jede gespeicherte M5-Kerze veröffentlicht der Adapter `m5_candle_saved` auf dem Event Bus
5. Der AgentDispatcher (AD) hört auf `m5_candle_saved` und feuert `m5_agent_trigger` wenn angemessen

### sync_interval_seconds

Standard: 60 Sekunden.

Das Polling-Intervall sollte ungefähr der M5-Kerzen-Dauer (300 Sekunden) oder kürzer gesetzt werden. Ein 60-Sekunden-Intervall stellt sicher, dass neue Kerzen kurz nach dem Schließen abgerufen werden. Nicht unter 10 Sekunden setzen — übermäßiges Polling kann Broker-API-Rate-Limits auslösen.

### Lückenerkkennung und -füllung

Beim Start und periodisch während des Betriebs prüft der Adapter auf Lücken in der gespeicherten Kerzenhistorie:
- `candle_gap_fill_lookback_bars`: wie viele Bars für Lückenprüfung zurückgeschaut wird (Standard: 200)
- Bei gefundener Lücke: Adapter holt fehlende Kerzen und veröffentlicht `candle_gap_detected`
- Lückenfüllung läuft einmal beim Start und erneut nach Konnektivitätsunterbrechungen

### max_candle_sync_count

Maximale Kerzen in einem einzelnen API-Request. Standard: 500.

Bei der initialen Einrichtung oder nach einer langen Lücke müssen möglicherweise Hunderte historischer Kerzen abgerufen werden. Der API-Request wird in Batches von `max_candle_sync_count` aufgeteilt wenn mehr benötigt werden.

---

## broker_candle_utc_offset_hours und das Broker-Modul

Die Broker-Modul-Konfigurationsdatei enthält die UTC-Offset-Einstellung selbst nicht. Diese Einstellung liegt in `config/system.json5` unter `system.broker_candle_utc_offset_hours`.

Das Broker-Modul bestimmt jedoch welcher Offset-Wert korrekt ist:
- MT5-Broker liefern Kerzen typischerweise in Broker-Lokalzeit (UTC+2 oder UTC+3 je nach Sommerzeit)
- OANDA liefert Kerzen in UTC

Beim Wechsel von einem MT5-Broker zu OANDA oder beim Hinzufügen eines OANDA-Adapters neben einem MT5-Adapter:
- `broker_candle_utc_offset_hours` auf den aktiven Datenquellen-Offset anpassen
- Für MT5: typischerweise `3` (Sommer/EEST) oder `2` (Winter/EET)
- Für OANDA: `0` (UTC)

Für eine vollständige Erklärung dieser Einstellung siehe [System Config](ui.config.system_config.de.md#broker_candle_utc_offset_hours--kritische-einstellung).

---

## Symbol-Maps

Verschiedene Broker verwenden verschiedene Symbol-Namen. OpenForexAI verwendet intern Standard-6-Zeichen-Namen (EURUSD, GBPUSD usw.). Wenn ein Broker andere Symbole verwendet, bietet das `symbol_map`-Feld die Übersetzung.

### Wann eine Symbol-Map benötigt wird

- **MT5 mit Suffix**: Viele MT5-Broker fügen Suffixe an Symbole an (z.B. `EURUSDm`, `EURUSD.a`, `EURUSD_ecn`)
- **OANDA**: Verwendet Unterstrich-getrennte Notation (`EUR_USD`)
- **Index-Symbole**: Nicht-standardisierte Symbol-Namen für Indizes oder Metalle

### Symbol-Map-Format

```json5
symbol_map: {
  // Interner Name → Broker-Symbol
  "EURUSD": "EURUSDm",
  "GBPUSD": "GBPUSDm",
  "USDJPY": "USDJPYm",
  "XAUUSD": "GOLD",
}
```

Die linke Seite ist der interne Name in OpenForexAI-Agent-IDs und Konfigurationen. Die rechte Seite ist der exakte Symbol-Name wie er im MT5-Terminal oder der API des Brokers erscheint.

### Pairs vs. Symbol-Map

Das `pairs`-Array verwendet interne Namen. Die `symbol_map` wird nur beim Ausführen von API-Aufrufen an den Broker konsultiert. Wenn ein Paar in `pairs` keinen Eintrag in `symbol_map` hat, wird der interne Name direkt für API-Aufrufe verwendet.

---

## Mehrere Broker-Module

OpenForexAI unterstützt mehrere gleichzeitig laufende Broker-Adapter:

```json5
// In system.json5:
modules: {
  broker: [
    "config/broker/oxs_mt5.json5",
    "config/broker/oanda.json5"
  ]
}
```

Jeder Adapter registriert sich unabhängig auf dem Bus mit seinem eigenen `short_name`. Agenten werden pro Broker konfiguriert: EURUSD bei OXS_T verwendet `OXS_T-EURUSD-AA-ANLYS`, während EURUSD bei OANDA `OANDA-EURUSD-AA-ANLYS` verwendet.

Routing-Regeln mit Templates leiten automatisch zum richtigen Broker-Adapter basierend auf dem Broker-Segment des Absenders.

### Anwendungsfälle für mehrere Broker

- **Live + Demo**: Dieselbe Strategie live bei einem Broker und gleichzeitig auf einem Demo-Konto ausführen
- **Vergleich**: Identische Paare bei zwei Brokern überwachen um Spread- oder Fill-Unterschiede zu erkennen
- **Redundanz**: Wenn eine Verbindung ausfällt, hält der andere Brokers Daten das System teilweise betriebsfähig
- **Verschiedene Paare**: Jeder Broker verwaltet die Paare die er am besten unterstützt

---

## Typischer Ablauf

### Verbindungszugangsdaten ändern

1. Modul aus dem Dropdown auswählen
2. **Refresh** klicken
3. `password_env` oder `api_key_env` aktualisieren (und Umgebungsvariable auf neuen Wert setzen)
4. **Save** klicken
5. System neu starten
6. Verbindung in System Monitor überprüfen

### Neues Handelspaar hinzufügen

1. Modul auswählen
2. Paarnamen zum `pairs`-Array hinzufügen (z.B. `"AUDNZD"`)
3. Wenn Broker nicht-standardisierte Symbole verwendet, Eintrag zu `symbol_map` hinzufügen
4. **Save** klicken
5. System neu starten (oder Adapter neu laden)
6. Prüfen ob Kerzendaten innerhalb von 1–2 Sync-Zyklen in System Monitor erscheinen
7. AA-Agent und EC-Entität für dieses Paar in Agent Config und Entity Config konfigurieren

### Neuen Broker-Adapter hinzufügen

1. Neue Konfigurationsdatei erstellen (z.B. `config/broker/neuer_broker.json5`)
2. Geeignete `adapter`, `short_name`, `pairs` und Zugangsdaten setzen
3. Pfad zu `modules.broker` in `system.json5` hinzufügen
4. System neu starten
5. Prüfen ob Adapter in System Monitor registriert
6. Agenten für die Paare des neuen Brokers hinzufügen

---

## Broker-Verbindungsprobleme beheben

### Symptom: Adapter schlägt beim Start fehl

Für MT5:
- Läuft MT5-Terminal und ist eingeloggt?
- Ist das Konto-Passwort korrekt?
- Ist der `server`-Name exakt wie in MT5 angezeigt (Groß-/Kleinschreibung)?
- Ist das MT5-Python-Paket in der richtigen Python-Umgebung installiert?
- Ist Auto-Trading im MT5-Terminal aktiviert?

Für OANDA:
- Ist der API-Key gültig und nicht abgelaufen?
- Ist die `account_id` korrekt (im OANDA Hub prüfen)?
- Ist `environment` korrekt gesetzt (`practice` vs. `live`)?

### Symptom: Kerzen werden nicht abgerufen

- Prüfen ob `pairs` die gewünschten Paare enthält
- Prüfen ob `timeframes` die benötigten Zeitrahmen enthält
- Für MT5: prüfen ob Symbol-Namen in MT5 Market Watch existieren (ggf. hinzufügen)
- Bei Symbol-Nichtübereinstimmungen: `symbol_map`-Einträge prüfen
- `sync_interval_seconds` prüfen — bei sehr großem Wert läuft der erste Sync ggf. noch nicht

### Symptom: Session-Filter feuert zu falschen Zeiten

- `broker_candle_utc_offset_hours` in `system.json5` stimmt nicht mit Broker-Server-Zeitzone überein
- Für MT5: Broker-Serverzeit im MT5-Terminal prüfen (in der Statusleiste angezeigt)
- Für OANDA: sollte `0` sein (OANDA verwendet UTC)

### Symptom: Orders werden nicht ausgeführt

- Event Routing prüfen: gibt es eine Regel die `order_request` an die BK-CONN dieses Brokers leitet?
- Broker-Adapter registriert (in System Monitor sichtbar)?
- Für MT5: ist Auto-Trading im Terminal aktiviert? Auto-Trading-Schaltfläche in der Toolbar prüfen.

### Log-Meldungen

| Log-Meldung | Bedeutung |
|-------------|-----------|
| `[BK] Connected to broker X` | Adapter erfolgreich verbunden |
| `[BK] Connection failed: <error>` | Verbindungsversuch fehlgeschlagen |
| `[BK] Candle sync complete: N new candles` | Sync-Lauf abgeschlossen |
| `[BK] Gap detected at <time> for <pair>/<tf>` | Lücke gefunden, wird gefüllt |
| `[BK] Order placed: ticket=NNNN` | Order erfolgreich |
| `[BK] Order failed: <error>` | Order-Platzierungsfehler |
| `[BK] Reconnecting (attempt N)` | Verbindung verloren, wird erneut versucht |

---

*Dieses Dokument behandelt Broker Modules in OpenForexAI v0.7+. Für die Zeitzonen-Offset-Einstellung siehe [System Config](ui.config.system_config.de.md). Für Agenten-Konfiguration die an einen Broker gebunden ist, siehe [Agent Config](ui.config.agent_config.de.md).*
