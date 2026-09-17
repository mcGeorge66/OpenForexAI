# A/B: Die Überdehnungs-Regel ist nicht die Bremse

**17.09.2026 · USDJPY · Ergebnis: negativ, die Änderung wirkt nicht**

## Die Frage

Der Agent erkennt einen Trend, nennt ihn richtig und steigt nicht ein. Am
16.09. lief der USDJPY zwischen 17:55 und 20:10 UTC um **127 Pips über 27
Kerzen**; der Agent durchlief 14 Zyklen, sagte 11-mal `BIAS_LONG` und 13-mal
`WAIT`. Begründung jedes Mal sinngemäß: überdehnt, kein Rücksetzer, nahe dem
Extrem.

Vermutung: die Überdehnungs-Regel im System-Prompt blockiert. Diese Messung
prüft sie.

## Das FOMAK-Tor ist es nicht

Das seit dem 17.09. scharfe Tor (`A=S` und `V>=2`) hätte während der Rally
**23 von 28 Kerzen offen gestanden** (82 %), ab 18:30 durchgehend 21 Kerzen am
Stück. Es war nie die Bremse.

## Aufbau

Nicht im Simulator, sondern als Wiedergabe aus dem Event-Log: die
aufgezeichnete Anfrage wird wörtlich erneut gestellt, geändert wird **nur** der
System-Prompt. Der Config-Prompt steckt wortwörtlich in der Aufzeichnung (die
Laufzeit hängt nur einen `RUNTIME OVERRIDE`-Block an), eine Änderung dort ist
also gleichbedeutend mit einer Änderung in der Config.

- **21 Fälle** — alle `WAIT`-Entscheidungen bei offenem Tor ab 16.09., deren
  Anfrage mit dem heute gültigen Prompt (`96530023`) aufgezeichnet ist. Ältere
  Serien fallen raus: der Prompt hat sich seit dem 07.09. fünfmal geändert.
- **Parameter aus der Aufzeichnung**: `reasoning_effort='low'`,
  `temperature=1.0`, `max_tokens=4096`. Temperatur 1,0 → 3 Läufe je Variante.
- **126 Aufrufe**, 37 Minuten, 10 davon `504 Gateway Timeout`.
- Die Fälle sind nicht einseitig: bei 6 von 21 war Warten richtig.

**Variante B** änderte drei Dinge auf einmal: die wortgleiche Dublette der
Regel entfernt, „mehrere Kerzen in dieselbe Richtung" gilt nicht mehr als
Überdehnung, und eine Ausnahme für den Fall ohne Barriere voraus.

## Ergebnis

| | A (heute) | B (geändert) |
|---|---|---|
| `WAIT_FOR_TRIGGER` | 83 % | 75 % |
| `NO_TRADE` | 5 % | **13 %** |
| `EXECUTABLE_NOW` | 6 % | **3 %** |
| Einstiege gesamt | 4 / 59 | 2 / 57 |

**B ist zurückhaltender geworden, nicht mutiger.** In keinem der Rally-Fälle
(18:30–20:50, alle mit Ausgang +30 Pips) steigt eine der beiden Varianten ein.
Der Unterschied in den erwarteten Pips (−6,7 gegen +18,3) hängt an ein bis zwei
einzelnen Läufen von 60 und ist bei dieser Stichprobe Rauschen.

Ausgang nachgelaufen mit Stop 20 / Ziel 30 Pips über 4 h, Kerze für Kerze,
High und Low — es zählt, was zuerst berührt wird.

## Was damit ausgeschlossen ist

| Vermutung | Befund |
|---|---|
| Das FOMAK-Tor blockiert | 82 % offen während der Rally |
| Die Überdehnungs-Regel blockiert | Änderung ohne Wirkung |
| Der „Widerstand" ist das eigene Hoch der Bewegung | 3 von 21 |
| Die Slope_S-Sperrzone (±0,3) greift | 0 von 21; in der Rally 8–15 |

## Was die Daten stattdessen zeigen

In **84 %** aller 216 `WAIT`-Begründungen bei offenem Tor (ab 01.09.) nennt der
Agent einen **Widerstand voraus** — häufiger als Überdehnung (42 %), fehlende
Bestätigung (26 %) oder ein zu nahes Ziel (21 %).

Und dieser Widerstand ist meist real und **sehr nah**: in 12 der 21 Fälle liegt
`nearest_resistance` zwischen **0,1 und 18 Pips** über dem Kurs, die Mehrzahl
unter 7 Pips. Bei einem Spread von 1,1–1,6 ist die Ablehnung dort rechnerisch
richtig, kein Fehler.

In den übrigen **9 Fällen — fast alle aus der Rally — meldet der Snapshot
`nearest_resistance: null`**, also gar keinen Widerstand, und der Agent wartet
trotzdem. Genau diesen Fall adressierte Variante B ausdrücklich, ohne Wirkung.

Ein Einzelfall zeigt zusätzlich, wie der Widerstand entstehen kann: um 18:50
meldete der Snapshot `nearest_resistance: 155.92` — das **Hoch der Kerze von
18:35**, fünfzehn Minuten alt, der Extremwert der laufenden Bewegung selbst
(`"extreme": 155.92, "candles_since_extreme": 3`). Systematisch ist das aber
nicht: 3 von 21.

## Schluss

Die Überdehnungs-Regel ist **nicht** die Bremse. `WAIT_FOR_TRIGGER` ist
offenbar keine Folge einer einzelnen Regel, sondern eine Grundhaltung — eine
Regel weicher zu formulieren verschiebt sie nicht.

Ungeprüft und als nächstes naheliegend: nicht *erlauben*, sondern die Wahl
einschränken. Etwa — wenn `nearest_resistance` leer ist und die höhere
Zeitebene die Richtung bestätigt, ist `WAIT_FOR_TRIGGER` keine zulässige
Antwort, sondern nur `EXECUTABLE_NOW` oder `NO_TRADE` mit Begründung. Das ist
eine Vermutung, keine Messung.

## Rohdaten

- `2026-09-17_prompt_ab_rohdaten.json` — jeder der 126 Aufrufe mit Zustand
- `2026-09-17_prompt_ab_auswertung.json` — je Fall Einstiegsquote und Ausgang
