[Zurück zu Action](ui.action.de.md)

# Event Log — Handbuch

Das **Event Log** ist das durchsuchbare, **persistierte** Archiv aller Events, die das System jemals in die Datenbank geschrieben hat. Es ist bewusst getrennt vom [Monitor](ui.monitor.de.md): der Monitor zeigt den **Live-Strom** der letzten paar hundert Events, verliert seinen Inhalt beim Neuladen der Seite und zeigt nur, was gerade passiert. Das Event Log fragt stattdessen die Datenbank ab — es findet auch Events von vor Tagen oder Wochen und überlebt einen Browser-Neustart.

**Faustregel, wann welches Werkzeug:** Beobachtest du etwas, das gerade passiert oder gleich passieren wird → Monitor. Untersuchst du etwas, das bereits passiert ist (ein Trade von gestern, ein Fehler von letzter Woche) → Event Log.

---

## 1. Kopfleiste und Filter

| Element | Funktion |
|---------|---------|
| **Roots / All** | `Roots` zeigt nur **Trace-Root-Events** — die Startpunkte einer Ereigniskette (z. B. `m5_candle_trigger`, `order_request`). `All` zeigt jedes persistierte Event, auch die, die Teil einer größeren Kette sind. |
| **event_type** | Filtert auf einen exakten oder teilweisen Event-Typ-Namen. |
| **source agent** | Filtert auf den auslösenden Agenten/Modul. |
| **correlation id** | Filtert auf eine bestimmte Korrelations-ID, um eine zusammenhängende Kette zu finden. |
| **From time / To time** | Zeitraum-Filter (lokale Datum/Uhrzeit-Auswahl). |
| **min–max (Chain)** | Filtert Trace-Root-Events nach der Größe ihrer Ereigniskette. |
| **Search** | Wendet die aktuellen Filter an und lädt neu. |
| **Clear** | Setzt alle Filterfelder zurück. |
| **Refresh-Icon** (oben rechts) | Lädt die aktuelle Filterauswahl neu. |

**Empfehlung:** Fast immer im `Roots`-Modus anfangen. Er zeigt genau einen Eintrag pro abgeschlossenem Vorgang (z. B. einem kompletten Analyse-Zyklus), statt Dutzende Einzel-Events, die alle zu demselben Vorgang gehören — deutlich schneller zu überblicken. Erst wenn man einen bestimmten Zwischenschritt sucht, der in der Trace-Ansicht (Abschnitt 3) nicht auftaucht, auf `All` wechseln.

**Chain min/max sinnvoll nutzen:** Ein sehr niedriger Chain-Wert (z. B. max. 2) findet typischerweise fehlgeschlagene oder früh abgebrochene Zyklen — der Agent wurde getriggert, hat aber kaum etwas ausgelöst. Ein sehr hoher Wert findet ungewöhnlich lange, verzweigte Ketten, die es sich lohnt genauer anzusehen (z. B. weil ein EC mehrfach nachgefragt oder ein Tool wiederholt fehlgeschlagen und erneut versucht hat).

Ergebnisse werden seitenweise geladen (50 pro Seite); **Load more** am Ende der Tabelle lädt die nächste Seite nach.

---

## 2. Tabellenspalten

| Spalte | Inhalt |
|--------|--------|
| **Time** | Erstellungszeitpunkt in der system-konfigurierten Zeitzone. |
| **Event Type** | Farbcodiert nach Kategorie. |
| **Source** | Der auslösende Agent bzw. das Modul. |
| **Events / Chain** | Im `Roots`-Modus: Anzahl der Folge-Events in dieser Kette (`+N`). Im `All`-Modus: Vorfahren/Nachkommen (`↑N`/`↓N`). |
| **Trace** (Verzweigungs-Icon) | Öffnet die Trace-Ansicht für dieses Event. |

Ein Klick auf eine beliebige Zeile öffnet ebenfalls die Trace-Ansicht (erneuter Klick schließt sie).

---

## 3. Trace-Ansicht

Öffnet sich rechts neben der Tabelle und zeigt die **vollständige Ereigniskette** zu einem Event als vertikale Zeitleiste — vom Root-Event bis zum angeklickten Ziel-Event (Ziel zusätzlich mit „← target" markiert).

Pro Eintrag: Event-Typ, Zeitstempel, relative Zeit zum Root-Event (z. B. `+842ms`), Quell-/Ziel-Agent, Korrelations-ID. Ein Klick klappt den Eintrag auf und zeigt zusätzlich die vollständige Event-ID, die Korrelationskette und das vollständige JSON-Payload.

**Empfehlung:** Die relative Zeit (`+842ms` usw.) ist der schnellste Weg, eine Performance-Auffälligkeit zu finden — ein Sprung von z. B. `+120ms` auf `+4200ms` zwischen zwei aufeinanderfolgenden Schritten zeigt sofort, welcher Teilschritt (LLM-Aufruf, Tool-Aufruf, Broker-Antwort) den gesamten Zyklus verlangsamt hat, ohne dass man Zeitstempel manuell subtrahieren muss.

**Export**-Button: lädt die komplette Kette als `.json5`-Datei herunter. Nützlich, um einen Vorfall zu sichern, bevor er aus praktischen Gründen (z. B. Datenbank-Aufräumen) nicht mehr auffindbar ist, oder um ihn außerhalb der UI zu teilen — z. B. an einen Kollegen oder in ein Ticket, ohne dass dieser selbst Zugriff auf die laufende Instanz braucht.

---

## 4. Typische Arbeitsabläufe

### 4.1 Einen abgelehnten Trade untersuchen

1. `Roots`-Modus, nach `event_type` z. B. `order_result` oder `signal_rejected` filtern.
2. Zeitraum auf den fraglichen Tag eingrenzen (`From time`/`To time`).
3. Passendes Event anklicken, um die Trace-Ansicht zu öffnen.
4. Die Kette vom Trigger bis zur Ablehnung durchklicken — jeder aufgeklappte Schritt zeigt das vollständige Payload dieses Zwischenschritts. Meist findet sich die eigentliche Begründung nicht im Root-Event, sondern in einem `ec_run_output`- oder `broker_http_response`-Eintrag weiter unten in der Kette.
5. Bei Bedarf **Export** klicken, um die Kette zu sichern, bevor man mit einem Kollegen oder Support darüber spricht.

### 4.2 Herausfinden, ob ein Problem einmalig war oder ein Muster ist

Ein einzelner Vorfall lässt sich leicht überinterpretieren. Bevor man eine Konfigurationsänderung vornimmt, lohnt sich der Blick, ob dasselbe Muster öfter auftritt:

1. `event_type` auf den vermuteten Fehlertyp setzen (z. B. `agent_trigger_skipped` oder `order_result`).
2. Zeitraum bewusst weit fassen (z. B. die letzten 7 Tage).
3. Ergebnisliste durchsehen — tritt der Fehler regelmäßig zur gleichen Tageszeit auf (Hinweis auf Session-Filter oder Marktöffnungszeiten), oder nur bei einem bestimmten Pair (Hinweis auf ein Konfigurationsproblem bei genau diesem Agenten)?
4. Erst mit diesem Gesamtbild eine Änderung vornehmen — sonst besteht die Gefahr, einen Einzelfall zu „reparieren", der eigentlich normales, erwartetes Verhalten war.

**Warnung:** Das Event Log zeigt nur, was tatsächlich als Event veröffentlicht wurde. Wenn ein Agent z. B. wegen `runtime_paused` nie ausgelöst hat, erscheint dazu ein `agent_trigger_skipped`-Event — aber wenn die Runtime insgesamt gar nicht lief, fehlen unter Umständen auch diese Skip-Events komplett. Ein leeres Suchergebnis bedeutet nicht zwingend „nichts ist passiert", sondern manchmal „das System lief in diesem Zeitraum gar nicht". Im Zweifel den Systemstatus auf der Initial-Seite für den fraglichen Zeitraum gegenprüfen.
