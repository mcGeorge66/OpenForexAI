[Zurück zu Config](ui.config.de.md)

# Information

`Information` ist ein Freeform-Markdown-Editor für die Datei `config/config.md`. Er bietet einen Lesen/Bearbeiten-Umschalter für Projektdokumentation, Strategie-Notizen und beliebige Referenzinhalte, die neben der Trading-Konfiguration aufbewahrt werden sollen. Die Datei wird vom System nicht verwendet — sie existiert ausschließlich als Referenz für den Menschen am Steuer.

---

## Was ist config/config.md?

`config/config.md` ist eine einfache Markdown-Datei im Konfigurationsverzeichnis. Sie hat keinen Einfluss auf das Systemverhalten: Kein Agent liest sie, kein Snapshot referenziert sie, und kein LLM erhält ihren Inhalt. Sie ist reine Dokumentation für die Personen, die das System betreiben.

Änderungen werden direkt über die Management API auf der Disk gespeichert und sind nach einem Reload der Information-Seite sofort sichtbar.

---

## Oberfläche

### Ansichtsmodus

Der Standardzustand. Rendert `config/config.md` als formatiertes Markdown: Überschriften, Fett/Kursiv, Tabellen, Code-Blöcke, Links und horizontale Trennlinien werden korrekt dargestellt.

### Bearbeitungsmodus

Wird durch die **Edit**-Schaltfläche aktiviert. Zeigt den rohen Markdown-Quellcode in einem Texteditor.

### Steuerelemente

| Steuerelement | Funktion |
|---|---|
| **Edit** | Wechselt vom Ansichtsmodus in den Bearbeitungsmodus |
| **Save** | Schreibt den aktuellen Editor-Inhalt in `config/config.md` und kehrt zum Ansichtsmodus zurück |
| **Cancel** | Verwirft nicht gespeicherte Änderungen und kehrt ohne Speichern zum Ansichtsmodus zurück |

---

## Was hier hineingehört

Die Information-Seite ist eine leere Leinwand. Sie kann für alles genutzt werden, was dabei hilft, das System zu verstehen und zu betreiben. Die folgenden Abschnitte beschreiben häufige praktische Verwendungszwecke.

### Handelsstrategie-Dokumentation

Die Strategie dokumentieren, auf die die Agenten konfiguriert sind. Das ist wertvoller Kontext, wenn man die Konfiguration Monate später noch einmal durchgeht oder eine andere Person die Betriebsführung übernimmt.

Nützliche Inhalte:

- Strategiename und Beschreibung
- Entry-Bedingungen, nach denen das LLM sucht
- Exit- und Stop-Loss-Logik
- Für welche Paare und Zeitrahmen die Strategie ausgelegt ist
- Performance-Erwartungen und bekannte Schwächen
- Begründung für wichtige Prompt-Entscheidungen

Beispiel:

```markdown
## Strategie: EUR/USD H1 Trendfortsetzung

Dieses Setup sucht H1-Trendfortsetzung mit M5-Entry-Timing.

**Entry-Bedingungen:**
- H1 EMA20 > EMA50 (bullish) oder EMA20 < EMA50 (bearish)
- Preis hat zu H1 EMA20 zurückgezogen
- M5 zeigt Rejection-Kerze oder Momentum-Wende
- ATR > 10 Pips (ausreichende Volatilität)

**No-Trade-Bedingungen:**
- Innerhalb von 30 Min. eines größeren News-Events
- H1 ATR expandiert stark (News-Spikes vermeiden)
- DXY bewegt sich kräftig gegen die beabsichtigte Richtung
```

### Risiko-Regeln und Positionsgrößenbestimmung

Risikomanagement-Regeln dokumentieren, damit sie neben der Konfiguration sichtbar sind, die sie umsetzt.

```markdown
## Risiko-Regeln

- Max. Risiko pro Trade: 1% des Eigenkapitals
- Max. gleichzeitig offene Trades: 3
- Max. gesamtes offenes Risiko: 3% des Eigenkapitals
- Kein Trading zwischen 22:00–01:00 UTC (geringe Liquidität)
- Stop-Loss immer bei ATR × 1,5 vom Entry
- Take-Profit bei ATR × 2,5 (min. 1:1,67 R:R)
```

### Broker- und Konto-Einrichtungsnotizen

Broker-spezifische Informationen festhalten, die bei der Fehlersuche oder beim Einarbeiten neuer Personen nützlich sind.

```markdown
## Broker-Einrichtung

**Broker:** OANDA
**Kontotyp:** Live / Standard
**Basiswährung:** EUR
**Modul-Datei:** config/adapters/broker_oanda_live.json5

**Konfigurierte Symbole:**
- EURUSD (Pip-Größe: 0,0001, Lot: 100.000)
- GBPUSD (Pip-Größe: 0,0001, Lot: 100.000)
- USDJPY (Pip-Größe: 0,01, Lot: 100.000)

**Hinweise:**
- OANDA verwendet Fraktional-Pips — Preise haben 5 Dezimalstellen
- Minimale Lot-Größe: 0,001 (1.000 Einheiten)
```

### LLM-Modell-Notizen

Dokumentieren, welche Modelle verwendet werden und warum, sowie Beobachtungen zu deren Verhalten.

```markdown
## LLM-Konfiguration

**Analyse-Agenten (AA):** GPT-4o
- Temperature: 0,2
- Max Tokens: 800
- Gewählt wegen konsistenter strukturierter Ausgabe und zuverlässigem Tool-Einsatz

**Broker-Agenten (BA):** GPT-4o-mini
- Temperature: 0,1
- Max Tokens: 400
- Niedrigere Kosten; BA-Entscheidungen folgen Regeln, keine komplexe Analyse

**Beobachtungen:**
- GPT-4o neigt zur Überqualifizierung von Signalen wenn ATR grenzwertig ist
- Prompt-Änderung 2026-04-10: "do not hedge in uncertainty — choose one direction" verbesserte Signalrate
```

### Konfigurationsänderungs-Protokoll

Wesentliche Konfigurationsänderungen festhalten, um nachvollziehen zu können, was wann geändert wurde.

```markdown
## Änderungsprotokoll

### 2026-06-01
- Bridge Tool `ask_ga_outlook` zu EUR/USD- und GBP/USD-AA-Agenten hinzugefügt
- BA-Agenten-Timeout von 30 auf 60 Sekunden erhöht nach Timeout-Fehlern in volatilen Sessions

### 2026-05-15
- AA-Agenten von GPT-4o-mini auf GPT-4o umgestellt — Qualitätsverbesserung spürbar
- ATR-Multiplikatoren angepasst: SL von 1,2 auf 1,5; TP von 2,0 auf 2,5

### 2026-05-01
- Erste Live-Bereitstellung
- EUR/USD H1- und GBP/USD H1-Agenten aktiv
```

### Agenten-Architektur-Notizen

Für komplexe Deployments mit vielen Agenten die beabsichtigte Architektur dokumentieren.

```markdown
## Agenten-Architektur

### Aktive Agenten

| Agent-ID | Rolle | Paar | Zeitrahmen |
|---|---|---|---|
| GLOBL-ALL___-GA-ANLYS | Globale Analyse | Alle | Stündlicher Trigger |
| OAPR1-EURUSD-AA-ANLYS | Paar-Analyse | EUR/USD | H1 |
| OAPR1-GBPUSD-AA-ANLYS | Paar-Analyse | GBP/USD | H1 |
| OAPR1-EURUSD-BA-TRADE | Trade-Ausführung | EUR/USD | Signal-getriggert |
| OAPR1-GBPUSD-BA-TRADE | Trade-Ausführung | GBP/USD | Signal-getriggert |

### Signal-Fluss

1. H1-Kerzen-Schluss → triggert AA-Agenten für jedes Paar
2. AA-Agent fragt optional GA-Agenten über Bridge Tool
3. AA-Agent erzeugt analysis_result-Event mit Signal (oder No-Trade)
4. EC Relay wendet Zeit-/News-Filter an
5. BA-Agent empfängt genehmigtes Signal, berechnet Positionsgröße, platziert Order
```

### Session- und Zeitzonen-Referenz

Eine schnelle Referenz für den Handelssessions-Zeitplan bereithalten.

```markdown
## Session-Referenz

Alle Zeiten in UTC:

| Session | Öffnung | Schließung | Hinweise |
|---|---|---|---|
| Sydney | 22:00 | 07:00 | Geringe Liquidität für Majors |
| Tokio | 00:00 | 09:00 | JPY-Paare am aktivsten |
| London | 07:00 | 16:00 | Höchste EUR/GBP-Liquidität |
| New York | 13:00 | 22:00 | USD-Paare am aktivsten |
| London/NY Überlappung | 13:00 | 16:00 | Höchstes Volumen-Fenster |

**Konfigurierte No-Trade-Stunden:** 22:00–01:00 UTC (Event-Routing-Regel)
```

### Performance-Notizen

Beobachtungen zur Live-Performance festhalten, um zukünftige Prompt- und Konfigurationsänderungen zu informieren.

```markdown
## Performance-Beobachtungen

### EUR/USD H1 (Stand 2026-06-01)
- Trefferquote: ~58% über letzte 30 Trades
- Beste Performance: London-Session, Trendingtage
- Schlechteste Performance: Montag Asia-Session, choppy Range
- Bekanntes Problem: Agent manchmal zu selbstsicher bei News-Tagen — News-Gate in Betracht ziehen

### GBP/USD H1
- Niedrigere Signal-Frequenz als EUR/USD (konservativerer Prompt)
- Durchschnittliches R:R bei gewinnenden Trades: 1,8 — leicht unter Ziel von 2,0
- ATR-TP-Multiplikator leicht reduzieren erwägen
```

---

## Markdown-Formatierungs-Referenz

Alle Standard-Markdown-Formatierungen werden unterstützt:

```markdown
# Überschrift 1
## Überschrift 2
### Überschrift 3

**Fetter Text**
*Kursiver Text*

- Aufzählungspunkt
- Weiterer Punkt
  - Eingerückter Punkt

1. Nummerierte Liste
2. Zweiter Punkt

| Spalte 1 | Spalte 2 |
|---|---|
| Zelle | Zelle |

`Inline-Code`

\```python
# Code-Block
def beispiel():
    pass
\```

> Zitat-Text

---
(horizontale Trennlinie)
```

---

## Siehe auch

- [System Config](ui.config.system_config.de.md) — system.json5 direkt bearbeiten
- [Agent Config](ui.config.agent_config.de.md) — Agenten-Definitionen und Einstellungen
- [Decision Prompt](ui.config.decision_prompt.de.md) — LLM-System-Prompts
- [Package Manager](ui.config.package_manager.de.md) — Konfigurationspakete exportieren und importieren
