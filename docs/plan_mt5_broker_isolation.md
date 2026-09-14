# Plan: MT5-Broker-Anbindung in eigenständige Prozesse auslagern

Status: **geplant, noch nicht umgesetzt** — Markt ist seit Montag, 2026-09-14 wieder
offen, die Umsetzung kann beginnen (siehe Abschnitt "Testbarkeit").

**Scope V1 vs. später:** V1 (diese Umsetzung) bringt jede MT5-Verbindung in einen
eigenen Prozess auf einem eigenen, dedizierten Windows-Server — eine aktive Verbindung
pro Broker, **kein** automatischer Failover. Die Architektur wird aber so gestaltet,
dass ein späteres Active/Passive-Setup ohne Neubau der Grundstruktur ergänzt werden
kann (siehe eigener Abschnitt "Vorbereitung auf Active/Passive" unten) — das ist
Vorbereitung, nicht Umsetzung.

## Begriffe

Drei Kurznamen, damit in Gespräch und Code klar ist, wovon die Rede ist:

| Name | Was | Wo |
|---|---|---|
| **SAT** | Satellit — der eigenständige Prozess mit der echten MT5-Verbindung | je MT5-Rechner einer |
| **HUB** | die Gegenstelle in OFAI: Gateway plus die Adapterinstanzen | einmal zentral |
| **TEAM** | virtueller Broker, der zwei SATs zu Active/Passive zusammenfasst | optional |

Codebezeichner bleiben davon unberührt: die Adapterklasse heißt weiterhin
`RemoteMT5Broker`, aktiviert über `"adapter": "mt5_remote"`, der Team-Adapter über
`"adapter": "mt5_team"`. Die Instanzbenennung bleibt `MT5_<BROKER>`, bei Teams mit
Suffix `_A` / `_B`.

## Problem

Das MetaTrader5-Python-Paket hält pro Python-Prozess nur **eine** aktive Verbindung
(`mt5.initialize()` ist prozessglobal, nicht pro Objekt) und ist **nicht thread-sicher**
für parallele native Aufrufe. Beides ist durch die offizielle MQL5-Doku und die
Community bestätigt (siehe Quellen unten).

OFAI läuft aktuell als ein einziger Python-Prozess. `bootstrap.py` unterstützt schon
mehrere Broker-Module gleichzeitig (`for broker_name, cfg_path in
broker_module_paths.items(): ...`), aber alle laufen im selben Prozess und importieren
dasselbe globale `MetaTrader5`-Modul. Aktuell sind 3 MT5-Broker im Einsatz. Solange
nur einer davon aktiv verbunden ist, fällt das nicht auf — sobald ein zweiter/dritter
gleichzeitig verbindet, würde der zweite `mt5.initialize()`-Aufruf die Verbindung des
ersten intern übernehmen/umleiten, **ohne Fehler**. Beide `MT5Broker`-Objekte glauben,
unabhängig verbunden zu sein, teilen aber tatsächlich dieselbe, zuletzt initialisierte
Verbindung — eine Order könnte beim falschen Account/Broker landen.

Ein kleinerer, bereits aufgetretener und gefixter Fall vom 2026-09-11: ein dedizierter
Thread-Pool mit `max_workers=4` für einen einzelnen MT5-Broker erlaubte zum ersten Mal
echte parallele native Aufrufe und produzierte zwei fehlgeschlagene Live-Orders mit
`mt5.last_error()=(-2, "Unnamed arguments not allowed")` — reproduziert und als
Zustands-/Concurrency-Problem bestätigt (derselbe Request war über `mt5.order_check()`
isoliert einwandfrei gültig). Der Fix (`max_workers=1`) behebt das *aktuelle* Symptom,
löst aber nicht das grundsätzlichere Problem mehrerer MT5-Verbindungen im selben
Prozess.

## Ziel

- Jede MT5-Broker-Verbindung läuft in ihrem **eigenen, eigenständigen Prozess** mit
  eigenem `mt5.initialize()` — keine geteilte Verbindung, keine Concurrency-Risiken.
- **Keine Änderung an OFAI selbst** — die Umstellung ist rein additiv (neuer Adapter-Typ,
  keine Anpassung an bestehendem Code außer einer Registrierungszeile).
- Design bleibt **jederzeit offen für Erweiterungen** (weitere Broker, andere
  Transport-Mechanismen, andere Broker-Typen mit demselben Muster).
- Das eigenständige Broker-Modul schreibt **eigene Logdateien** für spätere Analyse.
- Die Verbindung ist **von der ersten Zeile an verschlüsselt und beidseitig
  authentifiziert** — sie trägt Orderaufträge für ein Live-Geld-Konto über ein Netz,
  das nicht als vertrauenswürdig angenommen wird. Umgesetzt über einen
  WireGuard-Tunnel, in den sich die SATs einwählen (siehe "Sicherheit").

## Verifizierte Grundlage (Code gelesen, nicht angenommen)

Alle Stellen im System, die nach dem Bootstrap überhaupt eine Broker-Instanz anfassen,
lesen ausschließlich das statische Attribut `.short_name` — nie eine echte
Trading-Methode direkt:

- `openforexai/tools/dispatcher.py:303`
- `openforexai/agents/agent.py:326`
- `openforexai/composers/composer.py:302`
- `openforexai/data/container.py:118` (Kommentar dort sogar explizit: *"No broker
  instance is stored"*)

Echte Broker-Operationen (Order platzieren, Positionen abfragen, Account-Status,
Kerzen-Reparatur) laufen ausschließlich über den EventBus (`order_request`,
`positions_request`, `account_status_request`, `candle_repair_request`, ...), behandelt
in `openforexai/adapters/brokers/base.py` (`_handle_order_request`,
`_handle_positions_request`, etc.). Diese Trennlinie existiert also bereits im System —
sie muss nur an einer Stelle über eine Prozessgrenze hinweg verlängert werden.

Die Repository-Anbindung ist ebenfalls schon vollständig bus-vermittelt
(`repository=None,  # kept for compat — no longer used directly`, `base.py:369`).

Die einzige verbleibende direkte Objekt-Referenz, die der Broker hält, ist der
`MonitoringBus` (`self._monitoring.emit(...)`, `base.py:1279`) — muss mit über die
Prozessgrenze gebrückt werden (siehe unten).

## Architektur-Entscheidung

Kein MCP, kein neues Protokoll. Dieselben `AgentMessage`-Objekte (Pydantic-Modell), die
heute intern über den EventBus laufen, werden 1:1 über eine lokale IPC-Verbindung
weitergereicht — der Bus bekommt effektiv einen Draht statt nur RAM als
Transportmedium für die Mitglieder eines ausgelagerten Brokers.

### 1. "Virtuelles" Broker-Modul in OFAI (`RemoteMT5Broker`)

- Neuer Adapter, registriert wie jeder andere:
  `PluginRegistry.register_broker("mt5_remote", RemoteMT5Broker)` in
  `openforexai/adapters/brokers/__init__.py` — **eine zusätzliche Zeile**, neben der
  bestehenden `PluginRegistry.register_broker("mt5", MT5Broker)`.
- Aktiviert über `"adapter": "mt5_remote"` in der jeweiligen Broker-Modul-Config.
  `bootstrap.py` selbst bleibt unverändert (`PluginRegistry.get_broker(adapter)` ist
  bereits generisch, `bootstrap.py:153`).
- Implementiert nur das minimale Interface, das der Rest von OFAI tatsächlich braucht:
  `connect()`, `disconnect()`, `.short_name`, `start_background_tasks(...)`
  (No-Op — das echte Polling läuft im SAT-Prozess).
- Nach Verbindungsaufbau: registriert sich für dieselben Bus-Member-IDs, die der reale
  `MT5Broker` sonst hätte (`{SHORT_NAME}-ALL___-AD-ADPT`, `{SHORT_NAME}-{PAIR}-AD-ADPT`),
  und leitet Nachrichten 1:1 in beide Richtungen weiter — kennt selbst keine
  MT5-Semantik (kein Wissen über `place_order`, `get_open_positions`, etc. nötig).
- Wie der Transport darunter aussieht, ist für den Rest von OFAI **irrelevant** —
  reines Implementierungsdetail hinter der Adapter-Schnittstelle, austauschbar ohne
  den Rest des Systems zu berühren.
- `connect()` **nimmt entgegen, statt zu verbinden** (siehe "Verbindungsrichtung"):
  1. Meldet sich unter seinem `short_name` beim gemeinsamen HUB-Gateway an (siehe
     nächster Abschnitt) — **öffnet selbst keinen Socket**.
  2. Wartet, bis das Gateway ihm die Verbindung seines SAT zuweist. Bleibt sie aus,
     ist das ein Verbindungsfehler wie jeder andere — OFAI startet den SAT
     **nicht**: er läuft auf einem anderen Rechner, und ein Fernstart wäre ein
     zusätzlicher, deutlich heiklerer Zugriffsweg dorthin. Der Lebenszyklus gehört auf
     den SAT-Server (Dienst/Autostart).
  3. Schickt die Hello/Config-Nachricht an den SAT.

### 1b. HUB-Gateway — ein Listener für alle SATs

Es gibt **eine** Adapter-Klasse und **je Broker-Modul-Config eine Instanz** — bei drei
MT5-Brokern also drei `RemoteMT5Broker`-Objekte, genau wie heute drei `MT5Broker`.
`bootstrap.py` bleibt unverändert: die Schleife über die Broker-Module
(`bootstrap.py:152`) instanziiert weiterhin je Config einmal.

Würde aber jede dieser Instanzen ihren eigenen Listener öffnen, bräuchte man drei
Anwendungsports und drei Weiterleitungen. Das ist unnötig: WireGuard unterscheidet
Gegenstellen am Schlüssel, nicht am Port, und ein TCP-Listener nimmt beliebig viele
Verbindungen an.

Deshalb ein **gemeinsames Gateway unterhalb der Instanzen**:

- Genau ein Listener, gebunden an die Tunnel-Adresse von OFAI, ein fester Port für
  alle SATs.
- Beim Verbindungsaufbau ermittelt das Gateway die Gegenstelle (Tunnel-IP bzw.
  öffentlicher Schlüssel), schlägt in der Registrierung nach, zu welchem Broker sie
  gehört, und reicht die Verbindung an dessen `RemoteMT5Broker`-Instanz weiter.
- Eine noch unbekannte Gegenstelle wird **registriert, aber keiner Instanz
  zugeordnet** — sie ist damit sichtbar und konfigurierbar, ohne handeln zu können
  (siehe "Selbstregistrierung der SATs").
- Eine bekannte Gegenstelle, deren Anmeldung nicht zur gespeicherten Zuordnung passt:
  Verbindung verwerfen und melden.
- Meldet sich ein SAT erneut, während eine alte Verbindung desselben `short_name`
  noch registriert ist, ersetzt die neue die alte. Ein SAT-Neustart darf nicht an
  einer halbtoten Vorgängerverbindung hängenbleiben, die niemand mehr bedient.
- Das Gateway kennt **keine** MT5-Semantik. Es nimmt an, ordnet zu, übergibt — die
  Relay-Logik bleibt in der jeweiligen Instanz.

#### Nachrichtenzuordnung: der HUB entscheidet nach Korrelation

Im Team-Modus gehen eigenständige Nachrichten eines SAT an TEAM. Eine **Antwort** auf
eine Anfrage, die direkt an den SAT gerichtet war, muss dagegen zurück an den
Fragesteller auf dem Bus — an TEAM vorbei. Der HUB muss beides auseinanderhalten.

Dafür ist nichts Neues nötig, der Bus arbeitet bereits mit Korrelations-IDs
(`models/messaging.py:143`, `bus.py:212`), und der Adapter setzt sie beim Antworten
ohnehin (`base.py:224`). Der HUB führt eine Tabelle `correlation_id → Ziel der
Antwort`:

- Reicht er eine Anfrage **vom Bus zum SAT** durch, merkt er sich
  `msg.id → Absender auf dem Bus`.
- Reicht er eine Anfrage **vom SAT zum Bus** durch, merkt er sich `msg.id → dieser SAT`.
- Trifft eine Nachricht mit bekannter `correlation_id` ein, geht sie an das
  eingetragene Ziel; der Eintrag wird gelöscht.
- Alles ohne bekannte Korrelation gilt als **eigenständig** und folgt der Modus-Regel:
  im Team-Modus an TEAM, bei `direct` auf den Bus.

**Nicht nach `target_agent_id` unterscheiden.** Das wäre der naheliegende Weg und
er wäre falsch: `_repo_request` setzt `target_agent_id=REPO_SERVICE_ID`
(`base.py:151`), ist aber eine eigenständige Nachricht aus der Sync-Schleife. Nach
Zieladresse zu trennen ließe genau die Nachrichten durch, die TEAM beim passiven
Mitglied abfangen muss. Die Korrelation trennt richtig, weil sie aussagt "hierauf
wurde gewartet", nicht "das geht irgendwohin".

Zwei Randbedingungen: Die Tabelleneinträge brauchen eine **Verfallszeit**, sonst
wachsen sie, wenn eine Antwort nie eintrifft. Und `msg.id` ist eine UUID, Kollisionen
zwischen mehreren SATs gibt es also nicht.

**Der SAT muss davon nichts wissen.** Er antwortet wie heute, mit denselben Feldern,
die der bestehende Code bereits setzt — keine Änderung am Adapter, keine Kenntnis von
TEAM im SAT.

### 1c. Selbstregistrierung der SATs

Ein SAT, der sich zum ersten Mal meldet, wird von OFAI **aufgeschrieben**, nicht
konfiguriert. Der Unterschied ist der ganze Punkt:

- **Registrierung ist Entdeckung, keine Berechtigung.** Der Eintrag sagt "diese
  Verbindung existiert", nicht "sie darf handeln". Handeln kann ein Broker erst, wenn
  Agents, ECs und Snapshot-Profile gegen ihn konfiguriert sind — und das bleibt
  Handarbeit im System. Ein fremder Peer, der sich einträgt, landet damit in einer
  Liste und läuft ins Leere: keine Agents, keine Routing-Regeln, keine Abnehmer für
  seine Events.
- Umgekehrt löst es das Henne-Ei-Problem: **ohne Registrierung lässt sich ein Broker
  gar nicht konfigurieren**, weil man seinen Namen und seine Eigenschaften noch nicht
  kennt. Erst anschließen, dann in der Oberfläche auswählen.
- Die Registrierung ist zugleich die Grundlage der Überwachung: nur was registriert
  ist, kann als "verbunden" oder "gestört" gemeldet werden.

**Trust on first use — die erste Anmeldung nagelt den Schlüssel fest.** Käme der Name
bei jeder Verbindung frisch aus der Anmeldung, wäre die Registrierung genau das Loch,
das der Abschnitt "Zuordnung Peer zu Broker" schließt. Deshalb:

- Bei der ersten Anmeldung speichert OFAI `öffentlicher Schlüssel → Registrierungsname`
  samt Zeitpunkt und den gemeldeten Eigenschaften.
- Ab dann ist **der Schlüssel die Identität**. Meldet sich derselbe Schlüssel erneut,
  gilt die gespeicherte Zuordnung; die Anmeldung darf sie nicht mehr ändern.
- Ein anderer Schlüssel unter einem schon vergebenen Namen wird **abgewiesen und
  gemeldet** — nicht etwa als Neuregistrierung durchgewinkt.
- Eine Registrierung zu entfernen ist eine bewusste Handlung in OFAI, keine
  Nebenwirkung eines Verbindungsabbruchs.

**Was der SAT meldet**, und was OFAI gegen die Konfiguration prüft, sobald der
Broker konfiguriert ist: Kontonummer, Server, verfügbare Symbole, MT5-Version. Weicht
etwas ab, wird die Verbindung verweigert und gemeldet. Das fängt den Fall ab, der
echtes Geld kostet — der SAT hängt an einem anderen Konto, als OFAI annimmt, und
Orders landen am falschen Ort. Ohne diese Prüfung fällt das erst bei der Order auf.

### 1d. Jede Verbindung ist ein eigener Broker

Jede registrierte Verbindung erzeugt **automatisch einen eigenen Broker** und bleibt
dauerhaft sichtbar — auch wenn sie später einem Team angehört. Damit lässt sich jede
Verbindung jederzeit einzeln ansprechen und auf Funktion prüfen, statt nur als
namenloser Teil einer Gruppe zu existieren. Für die Fehlersuche ist das der
Unterschied zwischen "der Broker antwortet nicht" und "Satellit 2 antwortet nicht".

### 1e. Team-Broker: Active/Passive über zwei Verbindungen

Zusätzlich lässt sich **von Hand** ein virtueller Broker anlegen, der zwei der
vorhandenen Broker zu einem Team zusammenfasst. Dieser Team-Broker ist für das
Active/Passive-Management zuständig; die Einzelverbindungen bleiben daneben bestehen.

```json5
{
  "adapter": "mt5_team",
  "short_name": "OXS_T",
  "members": ["MT5_OXS_T_A", "MT5_OXS_T_B"],
  "command_ttl_seconds": 8,        // Frist, die dem SAT mitgegeben wird
  "failover_after_seconds": 11,    // wann TEAM auf das andere Mitglied geht
  "attempts_before_failover": 3,
  "heartbeat_interval_seconds": 2,
  "heartbeat_misses_before_dead": 3,
  "auto_failback": false
}
```

Für Agents, ECs und Routing ist das ein Broker wie jeder andere.

#### Attribute am Broker-Adapter

| Attribut | Werte | Herkunft |
|---|---|---|
| `modus` | `direct` \| `team` | Konfiguration |
| `team` | `short_name` des TEAM-Adapters | Konfiguration |
| `team_role` | `active` \| `passive` | Config-Datei, **von TEAM geschrieben** |

`modus` hat Vorrang: steht dort `direct`, wird ein vorhandenes `team` ignoriert. Das
ist eindeutig und braucht keine Ablehnung widersprüchlicher Kombinationen — der
ignorierte Eintrag wird aber beim Laden protokolliert, damit eine versehentliche
Fehlkonfiguration sichtbar ist statt stillschweigend zu wirken.

**`team_role` steht in der Config-Datei, aber TEAM ist der einzige Schreiber.**
Dasselbe Muster wie bei den abgeleiteten Routing-Regeln mit `owner`: Die Datei enthält
Zustand, den ein Dienst besitzt — sichtbar, versioniert, aber nicht von Hand zu
pflegen. Damit bleibt die Konfiguration wahr, statt nach dem ersten Failover zu
behaupten, A sei aktiv, während längst B läuft.

Geschrieben wird bei genau zwei Anlässen:

| Auslöser | Wann |
|---|---|
| Automatisch | **nur** bei Verbindungsausfall. Der Wechsel rastet ein, es gibt keine Rückkehr von selbst. |
| Manuell, "in sync" | Rollentausch im gesunden Zustand, für Wartung. Ausgelöst durch ein Event an TEAM — aus der Oberfläche oder aus einem Skript. |

Nach einem Neustart gilt, was in der Datei steht: der zuletzt aktive SAT bleibt aktiv.
Fehlt der Eintrag — beim allerersten Start —, nimmt TEAM das erste Mitglied aus
`members`. In beiden Fällen wird das andere Mitglied nachweislich auf passiv gesetzt,
**bevor** das erste aktiv wird.

Zwei Dinge, die bei der Umsetzung leicht schiefgehen:

- **Das Zurückschreiben darf keinen Hot-Reload auslösen.** Eine geänderte Config-Datei
  löst im System sonst einen Neuaufbau aus; mitten in einem Failover wäre das das
  Letzte, was gebraucht wird. TEAM kennt den neuen Zustand bereits — der Schreibvorgang
  ist reine Persistenz, wie `replace_owner` im Routing-Store, der ebenfalls nur bei
  echter Änderung schreibt.
- **Von Hand in der Datei geändert wird nichts.** Umgeschaltet wird, indem ein Event
  an TEAM geht — aus der Oberfläche, aus einem Skript, von wo auch immer. TEAM führt
  den Wechsel durch und schreibt ihn anschließend fest. Ein direkter Eingriff in die
  Datei würde beim nächsten Wechsel überschrieben, weil es genau einen Schreiber gibt.

#### Was TEAM beim passiven Mitglied abfängt

Die Trennlinie verläuft nicht zwischen Event und Anfrage, sondern zwischen
**ausgehend** und **eingehend**:

| Richtung | Beispiele | Passives Mitglied |
|---|---|---|
| Vom SAT ausgehend | `M5_CANDLE_UPDATE`, `M5_CANDLE_TRIGGER`, `CANDLE_GAP_DETECTED`, `ACCOUNT_STATUS_UPDATED`, `ORDER_BOOK_SYNC_DISCREPANCY`, `REPO_REQUEST` aus dem Orderbuch-Abgleich | TEAM verwirft |
| An den SAT gerichtet, samt Antwort | `ORDER_REQUEST` → `ORDER_RESULT`, `POSITIONS_REQUEST` → Antwort, `CANDLE_REPAIR_REQUESTED` → `CANDLE_DATA_BULK` | geht durch |

Der `REPO_REQUEST` in der ersten Zeile ist der Eintrag, den man leicht übersieht: Die
Sync-Schleife (`_sync_pair`, `base.py:725ff`) trägt brokerseitige Schließungen im
Orderbuch nach — über den Bus an den RepositoryService, also auf dem vorgesehenen Weg,
aber eigenständig. Liefe sie beim passiven Mitglied ungefiltert mit, würden zwei SATs
dasselbe Orderbuch gegen dasselbe Konto abgleichen.

Das passive Mitglied darf den Abgleich weiterhin **rechnen** — das hält es warm und
nachweislich funktionsfähig — nur das Ergebnis wird nicht zugestellt.

#### Rollenabgrenzung: TEAM ändert nie einen Inhalt

TEAM stellt Zustellung und Weiterleitung sicher, mehr nicht.

| | TEAM |
|---|---|
| Marktdaten erzeugen, Entscheidungen treffen, Payloads verändern | nie |
| Den Broker von sich aus abfragen | nie — das tun die SATs |
| Uhren, Wiederholungen, Umschaltung, Abgleichsanfrage vor dem Wiederholen | ja, das ist seine Aufgabe |

TEAM hat genau **zwei eigene Zeitgeber**: die Wartezeit auf eine Bestätigung und die
Heartbeat-Überwachung seiner Mitglieder. Alles andere geschieht nur, wenn eine
Nachricht eintrifft.

Diese Zeitgeber sind nicht wegzudesignen, auch wenn TEAM sonst rein reaktiv ist:
**Abwesenheit erzeugt kein Ereignis.** Eine vollständig reaktive Komponente könnte
nicht bemerken, dass nichts gekommen ist — und genau ein Ausbleiben ist die Störung,
für die TEAM gebaut wird.

#### Ablauf bei ausbleibender Antwort

1. Der Team-Manager schickt den Auftrag an das aktive Mitglied, **mit Verfallszeit**.
2. Kommt nach mehreren Versuchen keine Bestätigung, wartet er ab, bis die Frist des
   Adapters sicher abgelaufen ist (siehe Zeitverhältnis unten).
3. Er fragt über das **passive** Mitglied beim Broker nach, ob der Auftrag bereits
   wirksam wurde.
4. Nur wenn nicht, führt er ihn über das passive Mitglied aus.

#### Verfallszeit auf jedem ordersverändernden Befehl

Kritisch sind alle Befehle, die Orders verändern — platzieren, ändern, schließen.
Lesende Abfragen (Kerzen, Positionen, Kontostand) dürfen jederzeit wiederholt werden
und brauchen das nicht.

- Jeder solche Auftrag trägt eine Frist. Der Adapter **verwirft ihn nach Ablauf**,
  statt ihn verspätet auszuführen.
- Der Adapter misst die Frist **ab Empfang**, nicht ab einem mitgeschickten
  Zeitstempel. Damit ist keine Uhrensynchronisation zwischen den Maschinen nötig —
  und abweichende Uhren können die Frist nicht verfälschen.

#### Das Zeitverhältnis — hier entsteht sonst der Doppelversand

Der Manager startet seine Wartezeit beim **Senden**, der Adapter seine Frist beim
**Empfangen**. Empfang liegt später. Wären beide Zeiten gleich lang, verwürfe der
Adapter erst *nachdem* der Manager bereits umgeschaltet hat — und genau in diesem
Zwischenraum läuft derselbe Auftrag zweimal.

Deshalb gilt zwingend:

```
failover_after_seconds  >  command_ttl_seconds + maximale Übertragungsverzögerung
```

Die Werte in der Config werden beim Laden gegeneinander geprüft; eine Kombination, die
diese Bedingung verletzt, wird abgelehnt statt stillschweigend übernommen.

#### Die gewählten Werte

| Wert | Begründung |
|---|---|
| `command_ttl_seconds: 8` | Eine Order ist in derselben Sekunde beim Broker und in 1–2 s als laufender Trade bestätigt. Acht Sekunden sind reichlich, ohne die Wiederholung unnötig zu verzögern. |
| `failover_after_seconds: 11` | Acht Sekunden Frist plus drei Sekunden Reserve für die Übertragung. Über einen kabelgebundenen Tunnel liegt die Laufzeit im Millisekundenbereich. |
| `heartbeat_interval_seconds: 2`, `heartbeat_misses_before_dead: 3` | Verbindungsverlust in etwa sechs Sekunden erkannt. Es sind keine Funk- oder Mobilstrecken beteiligt, eine Unterbrechung von zehn Sekunden ist hier bereits ein echter Fehler und kein Wackler. |

Verbindungsverlust und unbeantworteter Auftrag sind dabei **zwei verschiedene
Auslöser**. Der Heartbeat darf schnell sein und schaltet die aktive Rolle für alles
Künftige sofort um. Ein bereits laufender Auftrag muss trotzdem seine Frist auslaufen
lassen, bevor er woanders wiederholt wird — schnellere Erkennung hilft dort nicht, die
Wartezeit ist physikalisch nötig.

#### Keine automatische Rückschaltung

`auto_failback: false`, und das ist die Empfehlung, nicht nur die Voreinstellung.

Jede Umschaltung ist ein Risikomoment: laufende Aufträge, Kerzenlücke oder
-überlappung, Übergabe des Orderbuch-Abgleichs. Für einen einzigen Vorfall zweimal
umzuschalten verdoppelt dieses Risiko, ohne etwas zu gewinnen — beide Mitglieder sind
gleichwertig und hängen am selben Konto. Ein zeitweise flackerndes Mitglied brächte
das System bei automatischer Rückschaltung zusätzlich zum Pendeln.

Regelmäßiges Nachfragen, ob das ausgefallene Mitglied wieder da ist, braucht es dafür
nicht: Da beide SATs durchgehend senden und der HUB nur verwirft, ist der Zustand des
Standby ohnehin laufend sichtbar. Statt zurückzuschalten wird gemeldet.

**Gemeldet werden drei Ereignisse**, jeweils über die bestehenden
Benachrichtigungsregeln:

- Umschaltung auf das passive Mitglied, mit Grund
- Rückschaltung von Hand
- Standby wiederhergestellt — die Redundanz steht wieder

#### Manuelles Umschalten für Wartung

Der Zustand gehört TEAM, also bekommt TEAM den Befehl: ein Endpunkt in der
Management-API und eine Schaltfläche in der Oberfläche, mit dem Zielmitglied als
Parameter.

Drei Bedingungen:

- Das Ziel muss verbunden und mit aktuellen Daten versorgt sein. Auf ein Mitglied
  umzuschalten, das selbst gerade hängt, wäre die Störung, die man vermeiden will.
- Laufende Aufträge werden abgewartet oder laufen ab, bevor umgeschaltet wird — es
  gilt dieselbe Frist wie beim automatischen Fall.
- Die Umschaltung wird gemeldet wie jede andere.

#### Die Frist begrenzt den Versuch, nicht die Wirkung

Auch mit korrektem Zeitverhältnis bleibt ein Restfall: Der Adapter schickt die Order
kurz vor Fristende an MT5, der Broker nimmt sie kurz danach an. Der Adapter verwirft
dann sein eigenes Ergebnis — die Order existiert trotzdem.

Deshalb ist Schritt 3 oben **tragend, nicht absichernd**: vor jeder Wiederholung über
das andere Mitglied wird **beim Broker** nachgesehen, nie in OFAIs Orderbuch. Das
Orderbuch ist im Störungsfall genau das, was nicht stimmt.

Dafür ist die Grundlage bereits vorhanden und muss nicht erst geschaffen werden:

- `openforexai/adapters/brokers/mt5.py:319` — der `sync_key` geht als `comment` mit
  der Order an den Broker.
- `mt5.py:373` — offene Positionen werden mit ihrem `sync_key` zurückgelesen.
- `mt5.py:590` — `find_closed_trade_by_sync_key()` findet auch bereits geschlossene.

Ein Auftrag ist damit am Broker eindeutig wiedererkennbar, unabhängig davon, über
welches Mitglied er ursprünglich lief.

#### Beide SATs senden, der HUB verwirft

Am SAT wird **nichts abgeschaltet**. Beide Mitglieder pollen durchgehend Kerzen,
Kontostand und Sync-Prüfung und senden alles an den HUB. Verworfen wird erst dort:
Solange ein Mitglied passiv ist, lässt der TEAM-Adapter dessen Datenstrom fallen.

Das kostet etwas Bandbreite — eine M5-Kerze alle fünf Minuten — und bringt zwei Dinge,
die den Preis wert sind:

- **Das passive Mitglied ist nachweislich gesund.** Ein Standby, der nichts sendet, ist
  bis zum Ernstfall ungetestet. Hier sieht man laufend, dass seine MT5-Verbindung
  steht, seine Kerzen aktuell sind und sein Konto antwortet — obwohl nichts davon
  verwendet wird.
- **Kein Kaltstart beim Umschalten.** Der neue Aktive pollt bereits, seine Verbindung
  ist warm, seine Kerzenhistorie fortlaufend. Es entfällt die Anlaufzeit, die ein erst
  bei Bedarf gestarteter Datenstrom hätte.

**Verworfen wird vor dem Veröffentlichen, nicht danach.** Der TEAM-Adapter filtert,
bevor er etwas auf den EventBus gibt. Landet der Strom des passiven Mitglieds erst auf
dem Bus und wird dort ausgesortiert, ist es zu spät — Agents und DataContainer haben
ihn dann schon gesehen.

#### Umschaltung: alles oder nichts

Der Wechsel erfasst **alle** Funktionen gleichzeitig — Orderweg, Kerzen, Kontostand,
Sync-Prüfung. Eine Mischung, bei der Orders über das eine und Kerzen über das andere
Mitglied laufen, darf es nicht geben: Entscheidungen würden dann auf Daten beruhen, die
aus einer anderen Verbindung stammen als die Ausführung, und im Fehlerfall wäre nicht
mehr zuzuordnen, welcher SAT was verursacht hat.

Ebenso darf **nie** ein Zeitraum entstehen, in dem beide Mitglieder gleichzeitig aktiv
sind. Der TEAM-Adapter schaltet das alte Mitglied nachweislich ab, bevor das neue
übernimmt.

#### Lückenlose Kerzen über die Umschaltung hinweg

Die vorhandene Lückenerkennung greift hier **nicht**. Der DataContainer holt zwar
fehlende Kerzen nach, aber er *sucht* keine Lücken: `_on_m5_candle`
(`data/container.py:173`) prüft die Payload, speichert und meldet `M5_CANDLE_SAVED` —
ohne Vergleich mit dem Vorgänger-Zeitstempel. Er wird informiert, und informiert wird
er von genau einer Stelle im System: `base.py:571`, im `_m5_loop` des SAT, im
Vergleich gegen dessen *eigenes* `last_m5`.

Da beide Mitglieder durchgehend pollen, hat nach einer Umschaltung keiner von beiden
eine Lücke in seiner eigenen Historie — der neue Aktive hat die Kerze bekommen, er
durfte sie nur nicht weiterreichen. Es meldet also niemand etwas. Die Lücke existiert
allein in dem, was der HUB weitergereicht hat, und das weiß nur TEAM.

Der TEAM-Adapter führt deshalb je Paar den Zeitstempel der zuletzt weitergereichten
M5-Kerze und prüft jede eingehende Kerze des aktiven Mitglieds dagegen:

| Fall | Bedingung | Reaktion |
|---|---|---|
| Normal | genau ein M5-Schritt weiter | weiterreichen, Marke setzen |
| **Überlappung** | Zeitstempel ≤ letzte weitergereichte | verwerfen |
| **Lücke** | mehr als ein M5-Schritt weiter | weiterreichen **und** Lücke melden |

Zur Überlappung, eingegrenzt: Für die **Speicherung** ist sie harmlos. Kerzen werden
mit `INSERT OR REPLACE` auf `timestamp TEXT PRIMARY KEY` geschrieben
(`adapters/database/sqlite.py:558`), dieselbe Kerze zweimal ändert also nichts. Was
nicht doppelt kommen darf, ist der **Trigger**: ein zweiter `M5_CANDLE_TRIGGER` für
dieselbe Kerze startet einen zweiten Analysezyklus. Die Entdopplung ist deshalb für
den Trigger-Pfad nötig, nicht zum Schutz der Datenbank.

**Für die Lücke wird die bestehende Maschinerie benutzt, kein zweiter Weg gebaut.** Der
TEAM-Adapter veröffentlicht `CANDLE_GAP_DETECTED` genau so, wie es ein einzelner
Adapter täte; der Rest läuft unverändert weiter:

```
TEAM erkennt Lücke        → CANDLE_GAP_DETECTED
Routing candle_gap_to_data → DataContainer
container.py:206           → CANDLE_REPAIR_REQUESTED an den Broker
base.py:199                → der inzwischen aktive SAT holt die Kerzen nach
```

Da die Umschaltung unter fünf Minuten liegen soll, fehlt im Regelfall höchstens eine
Kerze. Die vorhandene Erkennungslogik rechnet die Anzahl ohnehin aus dem
Zeitstempelabstand aus und kommt mit mehreren genauso zurecht.

#### Abgrenzung zu V1

V1 baut die Einzelverbindungen samt Registrierung, Überwachung und Notfall-Policy. Der
Team-Broker ist ein **eigener Adapter** (`mt5_team`) und kann danach ergänzt werden,
ohne die Einzelverbindungen anzufassen — sie funktionieren mit und ohne Team
unverändert weiter. Die Verfallszeit auf ordersverändernden Befehlen ist dagegen schon
in V1 sinnvoll: sie schützt auch ohne Failover davor, dass ein verspätet zugestellter
Auftrag lange nach seinem Anlass noch ausgeführt wird.

### 2. SAT — der eigenständige Prozess an MT5

- Ein Prozess pro MT5-Broker-Verbindung (aktuell also 3), jeder auf einem **eigenen,
  dedizierten Windows-Server** — nicht nur ein eigener Prozess auf derselben Maschine
  wie OFAI, sondern eigene Hardware/VM pro MT5-Instanz. Grund: siehe
  "Deployment"-Abschnitt unten.
- Config-Aufteilung (siehe "Vorbereitung auf Active/Passive" für die genaue
  Begründung): der SAT startet mit einer **minimalen, installationsfesten** lokalen
  Config (Account-ID, Passwort, Server, Installationspfad — Dinge, die sich ohne
  Neuinstallation nie ändern). Alle Betriebsparameter (Poll-Intervalle, aktive Pairs,
  UTC-Offset) kommen **nicht** aus einer zweiten geteilten Config-Datei, sondern werden
  von OFAI direkt nach Verbindungsaufbau als "Hello/Config"-Nachricht über den
  IPC-Kanal geschickt — und zwar auch in der einfachen Einzel-Instanz-Variante, damit
  es nur einen Code-Pfad gibt, der so oder so immer getestet wird.
- Instanziiert den bestehenden, **unveränderten** `MT5Broker` — echtes
  `mt5.initialize()`, volle Trading-Logik 1:1 wie heute.
- Bekommt statt des echten `EventBus` einen kleinen lokalen Shim mit derselben
  Schnittstelle (`register_member`, `publish`), der stattdessen über den Socket
  sendet/empfängt.
- **Wählt sich beim Hub ein** (WireGuard-Tunnel, danach die Anwendungsverbindung zu
  OFAIs Tunnel-Adresse) und versucht es bei Abbruch beharrlich erneut. Er lauscht
  selbst auf keinem von außen erreichbaren Port.
- **Schreibt eigene Logdateien** (siehe unten).

## Deployment: separate Windows-Server je MT5-Instanz

Jede MT5-Instanz läuft auf einem eigenen, dedizierten Windows-Server, nicht nur als
eigener Prozess auf derselben Maschine. Das ist bewusst mehr als nötig für das reine
"eine Verbindung pro Prozess"-Problem — der Grund ist Vorbereitung auf später (siehe
nächster Abschnitt): getrennte Hardware ist Voraussetzung für ein echtes
Active/Passive-Setup, das bei einem Server-Totalausfall (nicht nur Prozess-Absturz)
noch funktioniert.

Damit ist die IPC-Verbindung zwischen OFAI und einem SAT **nicht mehr localhost**,
sondern echtes Netzwerk (siehe "Sicherheit" unten für die daraus folgende
Anforderung).

### 3. Naming-Konvention

`MT5_<BROKER>` als stabiler Bezeichner je isolierter MT5-Verbindung — verwendet für:
SAT-Prozessname, Config-Dateiname, Log-Datei-Präfix. Unabhängig davon, ob die
Anbindung später direkt oder über localhost läuft (Namensgebung ist von der
Transport-Wahl entkoppelt).

Aktuell 3 Broker → 3 unabhängige SATs, 3 Config-Dateien, 3 Log-Präfixe, z.B.
`MT5_OXS_T`, `MT5_<Broker2>`, `MT5_<Broker3>`.

Für V2 (Active/Passive) offen: vermutlich `MT5_<BROKER>_PRIMARY` /
`MT5_<BROKER>_SECONDARY` als Suffix — noch nicht festgelegt, da V2 noch nicht gebaut
wird.

### 4. IPC / Nachrichtenformat

- `AgentMessage` → JSON, zeilenweise über eine TCP-Verbindung
  (newline-delimited JSON — einfaches, gut testbares Framing).
- **Kein Loopback.** Die SATs laufen auf eigenen Servern (siehe Deployment), die
  Verbindung geht über echtes, potenziell ungesichertes Netz. Was daraus folgt, steht
  verbindlich im Abschnitt "Sicherheit" — TLS und IP-Beschränkung sind Teil von V1,
  nicht nachrüstbare Zugaben.
- Zusätzlicher, kleinerer Kanal für `MonitoringEvent` (die eine verbleibende direkte
  Objekt-Referenz, siehe oben) — über dieselbe gesicherte Verbindung, kein zweiter
  offener Port.
- Transport bewusst austauschbar gehalten: TLS über TCP heute, später anderes möglich,
  ohne dass sich Framing/Format oder die OFAI-Seite ändern müssen. Ein Austausch darf
  die Sicherheitsanforderungen nie unterschreiten.

## Sicherheit (verbindlich für V1)

Die Verbindung zwischen OFAI und einem SAT geht über echtes Netzwerk, das nicht als
vertrauenswürdig angenommen werden darf. Über diese Verbindung laufen Orderaufträge für
ein Live-Geld-Konto — wer sie lesen kann, sieht die komplette Handelsstrategie; wer in
sie hineinschreiben kann, handelt auf fremde Rechnung. Deshalb gelten die folgenden
Punkte ab der ersten Zeile Code, nicht als spätere Härtung: nachträglich
Verschlüsselung in ein laufendes, unverschlüsseltes Protokoll einzuziehen bedeutet
erfahrungsgemäß einen Übergangszeitraum, in dem beides unterstützt werden muss — und
genau dieser Zeitraum wird dann produktiv genutzt.

Verschlüsselung allein genügt dabei nicht. Ein Kanal, der nur vertraulich ist, schützt
vor Mitlesen, aber nicht vor Einschleusen: Wer den Port erreicht, könnte eine formal
korrekte Order schicken, und ein SAT, der Anfragen ausführt, hätte kein Mittel,
echte von untergeschobenen zu unterscheiden. Erforderlich ist beides — Vertraulichkeit
**und** Authentifizierung der Gegenstelle. Der gewählte Transport leistet beides in
einem.

### Verbindungsrichtung: der SAT wählt sich ein

Umgekehrt zur ersten Fassung dieses Plans, und aus einem praktischen Grund: **nur
OFAI braucht dann eine stabile, erreichbare Adresse.** Die SATs können hinter
beliebigem NAT an wechselnden Standorten stehen, ohne Portfreigabe und ohne feste
öffentliche IP. Ein DNS-Eintrag für den Hub genügt für das gesamte Setup.

- **OFAI ist der Hub.** Ein WireGuard-Interface, ein offener UDP-Port, ein
  DNS-Name. Jeder SAT ist dort als Peer mit seinem öffentlichen Schlüssel und einer
  festen Tunnel-IP eingetragen.
- **Der SAT ist Spoke.** Er kennt Endpunkt und öffentlichen Schlüssel des Hubs,
  wählt sich ein und hält die Verbindung mit `PersistentKeepalive` offen, damit die
  NAT-Zuordnung seines Routers nicht wegläuft.
- **Auch die Anwendungsverbindung geht in dieselbe Richtung:** der SAT baut nach
  dem Tunnelaufbau die TCP-Verbindung zu OFAI auf. OFAI lauscht dafür **ausschließlich
  auf seiner WireGuard-Adresse**, nie auf `0.0.0.0` — sonst steht der Anwendungsport
  trotz Tunnel im lokalen Netz des OFAI-Rechners offen, und die ganze Absicherung
  hängt nur noch an der Windows-Firewall.
- Der Port des Anwendungskanals steht fest in der Config, keine dynamische Vergabe.

Das ändert den Lebenszyklus auf OFAI-Seite, und zwar zum Besseren: `connect()` im
`RemoteMT5Broker` verbindet sich nicht mehr irgendwohin, sondern **nimmt entgegen**.
OFAI muss nicht wissen, wo ein SAT gerade steht, und ein Neustart auf beiden Seiten
findet von allein wieder zusammen — der SAT versucht es einfach weiter.

### Zuordnung Peer zu Broker

Wählen sich mehrere SATs beim selben Hub ein, muss feststehen, welcher davon welcher
Broker ist. **Diese Zuordnung darf nicht aus der Hello-Nachricht kommen** — sonst
könnte sich ein SAT als ein anderer ausgeben und Orders für den falschen Account
entgegennehmen.

- Jeder Peer bekommt in der WireGuard-Konfiguration eine **feste Tunnel-IP**.
- OFAI bildet in seiner Config `Tunnel-IP → short_name` ab.
- Meldet sich eine Verbindung mit einem `short_name`, der nicht zu ihrer Quell-IP im
  Tunnel passt, wird sie **verworfen und protokolliert**, nicht etwa der Hello
  geglaubt.

Die Tunnel-IP ist dafür belastbar: WireGuard lässt ein Paket nur durch, wenn es mit
dem privaten Schlüssel des Peers verschlüsselt wurde, dem diese IP zugewiesen ist
(Cryptokey Routing). Eine gefälschte Absender-IP im Tunnel gibt es nicht.

### Transport: WireGuard

- **Verschlüsselung und Authentifizierung in einem.** Ein Schlüsselpaar je Maschine,
  der private Teil verlässt das Gerät nie; jede Seite trägt nur den öffentlichen
  Schlüssel der Gegenstelle ein. Genau das Modell aus einem öffentlichen und einem
  privaten Schlüssel — mit dem Authentifizierungsteil, der bei reiner Verschlüsselung
  fehlen würde.
- **Keine Schlüssel mit Ablaufdatum**, keine CA, keine X.509-Hülle, keine
  Erneuerungsroutine, kein TLS-Code in der Anwendung. Über den Tunnel läuft schlichtes
  TCP.
- **Kein fremder Dienst dazwischen.** Erwogen und verworfen wurde Tailscale (im Haus
  bereits im Einsatz): dessen Hauptvorteil ist NAT-Traversal ohne Portfreigabe — und
  der entfällt, sobald ohnehin nur eine Seite erreichbar sein muss. Übrig blieben eine
  Abhängigkeit von einer fremden Koordinationsebene und ablaufende Node-Keys, die auf
  einer Handelsmaschine zu einem Ausfall zu willkürlicher Zeit führen. Für ein Setup
  mit einem Hub und wenigen festen Spokes ist rohes WireGuard das kleinere System.
- Tailscale bleibt eine sinnvolle Rückfalloption, falls später SAT dazukommen, bei
  denen sich der Hub *nicht* erreichbar machen lässt.

### Der exponierte Port — bewusst in Kauf genommen

Mit dem Hub auf OFAI wandert die von außen erreichbare Fläche vom SAT auf das
zentrale System, also auf das wertvollere Ziel. Das ist der Preis der Topologie und
soll hier nicht beschönigt werden.

Was ihn vertretbar macht: WireGuard antwortet auf Pakete ohne gültige Kryptographie
**überhaupt nicht**. Der UDP-Port ist für einen Scanner nicht von einem geschlossenen
zu unterscheiden, es gibt kein Banner, keine Versionskennung, keine Handshake-Antwort,
an der sich ein Angreifer entlanghangeln könnte. Dazu kommt eine kleine, auditierte
Codebasis. Ein offener WireGuard-Port ist ungefähr das Harmloseste, was ein offener
Port sein kann.

Ergänzend gehört der UDP-Port auf dem OFAI-Rechner per Firewall auf die bekannten
Quell-Adressen beschränkt, soweit diese statisch sind. Wo die SATs dynamische IPs
haben, entfällt das — dann trägt WireGuard die Absicherung allein, was es kann.

### Was bewusst nicht vorgesehen ist

- Kein Fernstart des SAT durch OFAI (siehe `connect()` oben) — das wäre
  Codeausführung über das Netz und damit ein weit größeres Ziel als der Handelskanal
  selbst.
- Keine Authentifizierung über ein geteiltes Passwort oder Token im Klartext der
  Config. Der WireGuard-Schlüsselaustausch leistet dasselbe, und der private
  Schlüssel liegt außerhalb des Projektverzeichnisses — er kann nicht versehentlich
  ins Repo wandern.

## Verbindungsüberwachung und Notfallverhalten

Sobald der Broker in einem eigenen Prozess auf einem eigenen Server läuft, entsteht ein
Zustand, den es heute nicht gibt: **offene Positionen ohne aufsichtführendes System**.
Fällt die Verbindung aus, laufen die Positionen weiter, aber kein Trailing-Stop-EC, kein
Analyse-Agent und keine Exit-Logik greifen mehr. Dieser Abschnitt beschreibt, wie beide
Seiten das erkennen und was dann passiert.

### Was bereits abgesichert ist — und was nicht

Stop-Loss und Take-Profit liegen **brokerseitig** und wirken unabhängig von OFAI, vom
SAT und vom Netz. Ein Totalverlust durch eine Verbindungsstörung ist damit bereits
ausgeschlossen. Was fehlt, ist die *Bewirtschaftung*: Nachziehen des Stops, vorzeitiger
Ausstieg, Reaktion auf neue Marktlage.

Das ist wichtig für die Auslegung des Notfallverhaltens: Die Frage lautet nicht "wie
verhindere ich Totalverlust" — das tut der Broker-Stop —, sondern "wie lange lasse ich
eine unbeaufsichtigte Position laufen, bevor ich sie lieber schließe". Ein zu scharf
eingestellter Automatismus schließt bei jedem Netzwackler Positionen zum
schlechtestmöglichen Zeitpunkt und ist damit selbst eine Verlustquelle.

### Zustände des SAT

Der SAT führt eine explizite Zustandsmaschine. Der Unterschied zwischen "frisch
gestartet" und "Verbindung verloren" ist dabei entscheidend, weil nur der zweite Fall
den Notfall auslöst:

| Zustand | Bedeutung | Notfall-Policy |
|---|---|---|
| `STARTED_WAITING` | Prozess neu gestartet, noch nie eine Verbindung gehabt | **inaktiv** — es gab nie einen überwachten Zustand |
| `CONNECTED` | Verbindung steht, Heartbeat läuft | inaktiv, Timer zurückgesetzt |
| `DISCONNECTED_GRACE` | Verbindung verloren, innerhalb der Karenzzeit | inaktiv, Timer läuft |
| `DISCONNECTED_ACTION` | Karenzzeit überschritten | **aktiv** — Policy wird ausgeführt |

`STARTED_WAITING` deckt den Fall ab, den ein reiner Timeout falsch behandeln würde: der
SAT-Server wurde neu gestartet, OFAI ist noch nicht verbunden — daraus darf nie ein
Schließen von Positionen folgen, die der SAT nie betreut hat. Der Übergang nach
`DISCONNECTED_*` ist nur aus `CONNECTED` heraus möglich.

Bei einer Wiederverbindung geht der SAT zurück nach `CONNECTED` und setzt den Timer
zurück. Wurde in der Zwischenzeit eine Policy-Aktion ausgeführt, meldet er das OFAI im
Hello-Handshake — sonst arbeitet OFAI mit einem veralteten Bild des Orderbuchs weiter.

### Erkennung der Verbindung

- **Heartbeat in beide Richtungen** über denselben gesicherten Kanal, festes Intervall.
  Ein reiner TCP-Abbruch reicht nicht: eine tote Gegenstelle hinter einem stillen
  Netzgerät hält die Verbindung offen, ohne noch zu antworten.
- Ausbleibende Antworten zählen, nicht einzelne Aussetzer. Erst nach mehreren
  ausgefallenen Heartbeats gilt die Verbindung als unterbrochen.
- OFAI-Seite: dasselbe Verfahren spiegelbildlich. Der `RemoteMT5Broker` meldet eine
  gestörte oder verlorene Verbindung als Bus-Event, damit die bestehende
  Benachrichtigungs-Engine daraus eine Telegram-Nachricht machen kann — **keine
  eigene Telegram-Anbindung im Adapter**, das wäre ein zweiter Weg neben dem
  konfigurierbaren.

### Notfall-Policy: deklarativ, kein Skript

Die Instruktion, was bei längerer Unterbrechung geschehen soll, kommt von OFAI, wird vom
SAT lokal in einer Datei persistiert und überlebt dessen Neustart.

**Sie ist eine Datenstruktur, kein Skript.** OFAI schickt dem SAT niemals
ausführbaren Code. Begründung, dieselbe wie bei den Benachrichtigungsregeln
(`notification_rules.py`: *"no executable code in config"*): ein Skript über die
Leitung wäre Codeausführung über Netz — genau der Angriffsweg, den der
Sicherheitsabschnitt ausschließt. Dazu kommt, dass ein Skript auf der Gegenseite nicht
mehr validierbar ist: der SAT könnte nicht prüfen, ob er gleich Positionen schließt
oder das Datenverzeichnis löscht. Eine deklarative Policy kennt nur Aktionen, die der
SAT implementiert hat, und lässt sich vor dem Speichern gegen ein Schema prüfen.

Form (Entwurf, Feinschliff bei der Umsetzung):

```json5
{
  "version": 3,                 // von OFAI hochgezaehlt, SAT nimmt nur Neueres an
  "grace_seconds": 600,         // ab wann als Unterbrechung gewertet
  "on_disconnect": [
    {
      "after_seconds": 900,
      "action": "close_all_positions",
      "only_if": { "unrealized_pips": { "lt": 0 } }
    },
    { "after_seconds": 3600, "action": "close_all_positions" }
  ],
  "on_reconnect": "report_actions_taken"
}
```

- Erlaubte Aktionen sind eine **geschlossene Liste** im SAT-Code:
  `report_only`, `close_all_positions`, `close_losing_positions`,
  `tighten_stops_to_entry`. Eine unbekannte Aktion wird abgelehnt und protokolliert,
  nicht ignoriert und nicht geraten.
- **In V1 ist nur `report_only` umgesetzt.** Die eingreifenden Aktionen werden
  vorbereitet — Format, Zustandsmaschine, Meldewege stehen —, aber nicht gebaut. Eine
  konfigurierte, aber noch nicht implementierte Aktion wird **beim Laden abgelehnt**
  mit klarer Meldung, nicht stillschweigend übergangen. Ein Notfallmechanismus, von
  dem man glaubt, er greife, während er nichts tut, ist schlimmer als keiner.
- Die Filter (`only_if`) folgen derselben Syntax wie die Benachrichtigungsregeln, damit
  es im System nur eine Filtersprache gibt.
- Fehlt die Datei oder ist sie unlesbar, gilt `report_only` — der SAT unternimmt
  nichts Eingreifendes, protokolliert aber laut. **Fail safe, nicht fail silent:** im
  Zweifel nichts tun ist bei offenen Positionen richtiger als eine geratene Aktion.
- Jede ausgeführte Aktion landet im SAT-Log **und** wird beim nächsten Verbinden an
  OFAI gemeldet.

### Mini-Monitoring im SAT

Damit die Policy überhaupt etwas entscheiden kann, führt der SAT eine eigene,
kleine Positionsübersicht — unabhängig von OFAIs Orderbuch, das er im getrennten
Zustand nicht erreichen kann:

- Zyklisches Abfragen der offenen Positionen direkt bei MT5 (der SAT hat die
  Verbindung ohnehin).
- Je Position: Ticket, Symbol, Richtung, Volumen, Einstand, aktueller unrealisierter
  Stand, gesetzter SL/TP.
- Nur Positionen, die dieser SAT verantwortet (Abgrenzung über den Account, nicht
  über OFAIs Orderbuch).
- Diese Übersicht ist die **einzige** Entscheidungsgrundlage der Policy. Sie greift nie
  auf zwischengespeicherte Daten von OFAI zurück, die im Trennungsfall beliebig alt
  sein können.

## Logging (SAT)

Jeder SAT-Prozess schreibt eigene, durchsuchbare Logdateien (nicht nur stdout —
das ist beim Wrapper-Modell nachträglich kaum analysierbar). Mindestinhalt:

- Verbindungsaufbau/-abbruch zum MT5-Terminal (inkl. `mt5.last_error()` bei Fehlern).
- Jeder `mt5.*`-Aufruf mit Latenz — analog zum bestehenden "Slow MT5 call detected"-Log
  in `mt5.py`.
- Jede ein-/ausgehende Bus-Nachricht (Typ + Korrelation, nicht zwingend volle Payload).
- IPC-Verbindungsstatus zum Hauptprozess (verbunden/getrennt/Wiederverbindung).

Ablage- und Rotationskonvention an bestehende Log-Struktur anlehnen (`logs/`-Verzeichnis,
Präfix `MT5_<BROKER>_*`, Tages-Rotation wie bei den bestehenden LLM-Transcript-Logs).

## Vorbereitung auf Active/Passive (V2 — nicht Teil von V1)

V1 baut bewusst **nur**: ein SAT pro Broker, eine aktive Verbindung, kein
automatischer Wechsel. Trotzdem soll die Architektur jetzt schon so gestaltet werden,
dass ein Active/Passive-Setup später ergänzt werden kann, ohne die Grundstruktur
(virtuelles Modul, SAT, IPC-Format) noch einmal anzufassen. Die folgenden Punkte
sind **Entwurfsentscheidungen für später**, nicht Teil der V1-Umsetzung.

### Sicherheit

Steht im eigenen Abschnitt "Sicherheit (verbindlich für V1)" — Verschlüsselung und Zugangsbeschränkung sind keine V2-Themen,
sie gelten ab der ersten Verbindung.

### Warum kein einfaches gegenseitiges Heartbeat zwischen genau zwei SATsn

Die naheliegende Idee — Rechner 1 und Rechner 2 schreiben sich gegenseitig
Heartbeats, wer nicht mehr antwortet ist tot, der andere übernimmt — funktioniert für
den häufigsten Fall (ein Rechner stürzt komplett ab) einwandfrei. Sie versagt aber bei
einer **Netzwerk-Partition**: reißt nur die Verbindung *zwischen* den beiden Rechnern
(z.B. eine Firewall-Regel, ein VLAN-Routing-Fehler, ein dediziertes Heartbeat-Kabel
fällt aus), während beide Rechner einzeln weiterhin problemlos den Broker/das Internet
erreichen, kommen beide unabhängig zum selben falschen Schluss: "ich höre nichts mehr
vom anderen, also übernehme ich." Das ist Split-Brain — und mit nur zwei Parteien,
die sich ausschließlich gegenseitig beobachten, lässt sich "der andere ist tot" nie
sicher von "wir sind nur getrennt" unterscheiden (das sogenannte
Zwei-Generäle-Problem — eine bewiesene Grenze, kein Engineering-Defizit).

Eine dritte, unabhängige Instanz löst das nur, wenn sie über einen **anderen Pfad**
erreicht wird als die direkte Rechner-1↔2-Verbindung — eine dritte Kiste im selben
LAN/VLAN, die genauso von einer breiten Firewall-Regel betroffen wäre, bringt nichts
zusätzliches. Der am Ende einfachste, robusteste Kandidat für diesen unabhängigen
Pfad: **der Broker-Account selbst**, den beide SATs ohnehin über's Internet
erreichen müssen, um überhaupt handeln zu können — nicht eine zusätzliche, separat zu
betreibende dritte Maschine.

### Lease-basierter Ansatz (statt reines Zwei-Wege-Heartbeat)

Für später vorgesehen, analog zu echten Cluster-Systemen (Kubernetes, etcd,
Zookeeper): der aktive SAT hält einen "Lease" mit Ablaufzeit, den er alle paar
Sekunden erneuern muss. Der passive SAT prüft, ob der Lease abgelaufen ist, und
übernimmt nur dann — atomar (prüfen-und-setzen in einem Schritt, nicht getrennt lesen
dann schreiben, sonst Race zwischen zwei gleichzeitigen Übernahmeversuchen). Der
Lease-Speicherort muss die "unabhängiger Pfad"-Anforderung von oben erfüllen.

### Sync-Key-Dedup-Check — Voraussetzung, unabhängig vom Failover-Zeitpunkt

Selbst mit Lease und unabhängigem Pfad bleibt ein Restfall: ein SAT ist *langsam,
aber nicht tot* — die Anfrage wird trotzdem noch verarbeitet, während OFAI (oder der
Lease-Mechanismus) längst auf den anderen SAT umgeschaltet hat. Ergebnis:
dieselbe Order wird doppelt platziert. Bereits heute erzeugt und durchreicht das
System dafür einen `sync_key` je Order (`openforexai/tools/trading/order_execution.py:467/480/561`),
prüft ihn aber **nirgends** vor dem Ausführen gegen bereits offene Positionen/Orders.
Dieser Check ("existiert bereits eine offene Position/Order mit diesem `sync_key`?
Falls ja, überspringen.") ist eine Voraussetzung für einen sicheren Failover — sollte
aber unabhängig vom Active/Passive-Zeitplan ergänzt werden, da er auch ohne Failover
grundsätzlich robuster ist.

### Unabhängige Überwachung statt perfektem Konsens-Protokoll

Bewusste Risikoabwägung: OFAI ist kein sicherheitskritisches System, bei dem ein
Fehler irreversiblen Schaden anrichtet (keine "Herz-Lungen-Maschine") — eine doppelt
platzierte Order kostet Geld, ist aber manuell korrigierbar. Der sinnvolle Aufwand
liegt deshalb nicht in einem bulletproof Konsens-Protokoll zwischen den SATn,
sondern in **schneller, zuverlässiger Erkennung + Alarmierung**, falls doch mal etwas
schiefläuft.

Geplant: **Zabbix** als unabhängige Überwachungsinstanz (läuft auf eigener
Infrastruktur, unabhängig von beiden MT5-Servern). Nicht über den normalen
Zabbix-Agent (der ist für generische Host-Metriken wie CPU/RAM), sondern über
**Trapper-Items** — SAT und OFAI pushen anwendungsspezifische Werte aktiv an den
Zabbix-Server (`zabbix_sender` oder direkt über die Trapper-API). Sinnvolle Items:

- Lease-Zeitstempel je SAT.
- Wer aktuell glaubt, aktiv zu sein (je SAT).
- Duplikat-Zähler für `sync_key`-Kollisionen (sollte immer 0 sein — jeder Wert > 0
  ist ein sofortiger kritischer Alarm).
- IPC-Verbindungsstatus je SAT.

Trigger darauf: "kein Update seit N Sekunden" (SAT hängt/tot), "beide SATs
glauben gleichzeitig aktiv zu sein" (Split-Brain direkt erkannt), "Duplikat-Zähler >
0" (sofort kritisch). Alarmierung muss wirklich auffallen (Zabbix bringt
Telegram-Anbindung mit — passt zum bereits einmal angedachten, pausierten
Telegram-Plan), nicht nur passiv im Log/Monitoring-Tab landen.

### Was V1 davon konkret NICHT enthält

Kein Lease-Mechanismus, kein automatischer Wechsel, keine Zabbix-Integration, kein
zweiter SAT pro Broker. V1 liefert nur: ein SAT pro Broker auf eigenem Server,
saubere Prozess-Trennung, eigenes Logging. Die obigen Punkte bestimmen lediglich,
*wie* V1 gebaut wird (z.B. Config-Push statt geteilte Datei, `sync_key`-Check ergänzen),
damit V2 später ohne Bruch aufsetzen kann.

## Erweiterbarkeit — muss offen bleiben für

- Weitere MT5-Broker: neue Config + neuer SAT-Start, **kein Code-Änderung in OFAI**.
- Andere Broker-Typen, die dasselbe Isolations-Muster brauchen — nicht MT5-spezifisch
  hart verdrahten.
- Austausch des Transport-Mechanismus ohne Auswirkung auf die OFAI-Seite (die Grenze
  ist die Adapter-Schnittstelle, nicht der Socket).
- Spätere Sichtbarkeit im UI, ob ein SAT läuft/gesund ist (nicht Teil des ersten
  Schritts, aber das Design darf das nicht verbauen).
- Active/Passive-Failover (siehe eigener Abschnitt oben) — V1 baut nur den
  Single-SAT-Fall, aber Config-Push-Mechanismus und `sync_key`-Check werden schon
  in V1 so gebaut, dass V2 darauf aufsetzen kann.

## Umsetzungsschritte V1 (grob, nicht endgültig)

1. `RemoteMT5Broker`-Grundgerüst (Interface-Kompatibilität, noch ohne echten Transport)
   plus das gemeinsame HUB-Gateway: ein Listener, Zuordnung Tunnel-IP →
   `short_name`, Übergabe an die passende Instanz.
2. IPC-Bridge: Relay-Loop im virtuellen Modul (Bus → Socket) + Shim im SAT
   (Socket → bus-artiges Interface). **Von Anfang an nur über den WireGuard-Tunnel**,
   OFAI-Listener an die Tunnel-Adresse gebunden — nicht erst offen bauen und später
   einschränken; siehe "Sicherheit".
3. SAT-Entry-Point-Skript, das den bestehenden `MT5Broker` unverändert mit dem Shim
   verdrahtet — SAT-Config minimal (Account/Passwort/Server/Installationspfad),
   Betriebsparameter per Hello/Config-Nachricht von OFAI.
4. Logging im SAT.
5. `sync_key`-Dedup-Check vor Order-Ausführung ergänzen (unabhängig nützlich, siehe
   "Vorbereitung auf Active/Passive"). Durch den virtuellen Broker mit mehreren
   Verbindungen wird er wichtiger, nicht unwichtiger.
5b. Registrierung: Persistenz, Trust-on-first-use-Bindung an den Schlüssel, Abgleich
   der gemeldeten Eigenschaften gegen die Broker-Config, Sichtbarkeit in der
   Oberfläche.
5c. Verfallszeit auf ordersverändernden Befehlen: als Ganzzahl in Sekunden
   mitschicken, im SAT **ab Eingang** messen, nach Ablauf verwerfen. Schon ohne TEAM
   sinnvoll.
5d. Im TEAM: Filter für den Strom des passiven Mitglieds (vor dem Veröffentlichen),
   Marke der zuletzt weitergereichten M5-Kerze je Paar, Verwerfen von Überlappungen,
   Melden von Lücken über den bestehenden Reparaturweg.
6. Umstellung eines der 3 bestehenden Broker als Pilot, Rest nach erfolgreichem Test —
   je auf eigenem, dediziertem Windows-Server.
7. Lebenszyklus/Supervision: Start, Health-Check, Neustart bei Absturz — analog zum
   bestehenden `tools/openforexai-wrapper.py`-Muster.
8. Heartbeat in beide Richtungen, Zustandsmaschine im SAT, Verbindungsstörung als
   Bus-Event auf OFAI-Seite (Telegram folgt dann aus den bestehenden Regeln).
9. Mini-Monitoring der Positionen im SAT.
10. Notfall-Policy: Übertragung, Persistenz, Schema-Validierung, geschlossene
    Aktionsliste. Testbar ohne Markt: Verbindung hart trennen, Zustandsübergänge und
    Policy-Auslösung gegen ein Demokonto prüfen.
11. Inbetriebnahme je SAT-Server: WireGuard-Schlüsselpaar erzeugen, öffentlichen
    Schlüssel mit fester Tunnel-IP beim Hub eintragen, `PersistentKeepalive` setzen,
    Zuordnung Tunnel-IP → `short_name` in OFAIs Config ergänzen. Anschließend
    verifizieren, dass OFAIs Anwendungsport von außerhalb des Tunnels nicht erreichbar
    ist.

Lease-Mechanismus, zweiter SAT pro Broker und Zabbix-Integration sind **nicht**
Teil dieser Liste — das ist V2, siehe "Vorbereitung auf Active/Passive".

## Entschieden (vormals offen)

- **Wer öffnet den Port:** der SAT lauscht, OFAI verbindet sich. Der SAT baut nie
  selbst eine Verbindung nach außen auf. Siehe "Sicherheit".
- **Portvergabe:** fest je SAT in dessen Config (`listen_port`), nicht dynamisch.
  Nur ein fester Port lässt sich auf der Firewall sauber freigeben.

## Offene Entscheidungen (bewusst noch nicht festgelegt)

- DNS-Name und UDP-Port des HUB — wird bei der Einrichtung der Testumgebung geklärt.
- Ab wann die eingreifenden Notfall-Aktionen scharf geschaltet werden und mit welchen
  Schwellen. In V1 bleibt es bei `report_only`, die Entscheidung fällt erst, wenn der
  Mechanismus im Betrieb beobachtet wurde.

## Entschieden im Verlauf

- Fristen sind Ganzzahlen in Sekunden, im SAT ab Eingang gemessen.
- `command_ttl_seconds: 8`, `failover_after_seconds: 11`, Heartbeat alle 2 s mit
  3 tolerierten Ausfällen.
- Keine automatische Rückschaltung. Der automatische Wechsel erfolgt ausschließlich
  bei Verbindungsausfall und rastet ein; daneben gibt es das manuelle Umschalten
  "in sync" über TEAM. Beide werden in die Config-Datei zurückgeschrieben, damit der
  aktive SAT einen Neustart übersteht.
- Die Registrierung liegt als JSON5-Datei unter `config/RunTime/`, wie die
  Routing-Regeln und die Bridge-Tools — das Format des Systems bleibt einheitlich.
- Die SAT-Server laufen mit automatischer Anmeldung in einer aktiven Sitzung. MT5
  braucht eine solche Sitzung; ein Dienst in Session 0 scheidet damit aus, ein
  zweites MT5 im Portable-Modus ist aber **nicht** nötig. Wichtig im Betrieb: eine
  RDP-Sitzung *trennen*, nicht *abmelden* — Abmelden beendet die Sitzung und damit
  MT5.

## Testbarkeit

Ursprünglich am Wochenende geschrieben, als ohne laufende Kerzensignale (M5-Trigger)
die Order-/Positions-Pipeline nicht durchtestbar war. Seit Montag, 2026-09-14 ist der
Markt wieder offen — die Umsetzung kann beginnen.

Für die Sicherheitsanforderungen gilt zusätzlich: sie lassen sich unabhängig vom
Marktgeschehen prüfen — Anwendungsport von außerhalb des Tunnels nicht erreichbar,
Verbindung eines Peers mit unbekanntem Schlüssel kommt nicht zustande, und eine
Hello-Nachricht mit einem `short_name`, der nicht zur Tunnel-IP passt, wird verworfen.
Der letzte Punkt gehört als Test in die Suite, nicht in ein einmaliges manuelles
Ausprobieren.

## Quellen (Recherche zur MT5-Python-Grundlage)

- [MT5/Metatrader 5 connect to different MT5 terminals using python — MQL5 Forum](https://www.mql5.com/en/forum/351590)
- [Python working with multiple MT5 terminals — MQL5 Forum](https://www.mql5.com/en/forum/478406)
- [Documentation on MQL5: initialize / Python Integration](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py)
- [Developing a Terminal Manager (Part 2): Running Multiple Terminal Instances — MQL5 Articles](https://www.mql5.com/en/articles/19852)

Konzeptionelle Grundlage für den Active/Passive-Abschnitt (V2): Zwei-Generäle-Problem /
Split-Brain-Vermeidung bei verteilten Systemen (allgemeines, etabliertes Wissen —
Lease-basierte Führerwahl analog zu Kubernetes/etcd/Zookeeper), sowie Zabbix
Trapper-Items/`zabbix_sender` für Push-basiertes Custom-Monitoring.
