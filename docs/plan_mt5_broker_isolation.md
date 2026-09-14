# Plan: MT5-Broker-Anbindung in eigenständige Prozesse auslagern

Status: **geplant, noch nicht umgesetzt** — Umsetzung ab kommender Woche (siehe Abschnitt
"Warum jetzt nicht testbar").

**Scope V1 vs. später:** V1 (diese Umsetzung) bringt jede MT5-Verbindung in einen
eigenen Prozess auf einem eigenen, dedizierten Windows-Server — eine aktive Verbindung
pro Broker, **kein** automatischer Failover. Die Architektur wird aber so gestaltet,
dass ein späteres Active/Passive-Setup ohne Neubau der Grundstruktur ergänzt werden
kann (siehe eigener Abschnitt "Vorbereitung auf Active/Passive" unten) — das ist
Vorbereitung, nicht Umsetzung.

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
  (No-Op — das echte Polling läuft im Worker-Prozess).
- `connect()`:
  1. Prüft, ob der zugehörige Worker-Prozess bereits läuft/erreichbar ist.
  2. Falls nicht: startet ihn (Pfad zur gemeinsamen Config als Argument).
  3. Wartet, bis erreichbar, verbindet sich.
- Nach Verbindungsaufbau: registriert sich für dieselben Bus-Member-IDs, die der reale
  `MT5Broker` sonst hätte (`{SHORT_NAME}-ALL___-AD-ADPT`, `{SHORT_NAME}-{PAIR}-AD-ADPT`),
  und leitet Nachrichten 1:1 in beide Richtungen weiter — kennt selbst keine
  MT5-Semantik (kein Wissen über `place_order`, `get_open_positions`, etc. nötig).
- Ob die tatsächliche Kommunikation "direkt" oder "über localhost" läuft, ist für den
  Rest von OFAI **irrelevant** — reines Implementierungsdetail hinter der
  Adapter-Schnittstelle, austauschbar ohne den Rest des Systems zu berühren.

### 2. Eigenständiger MT5-Worker-Prozess

- Ein Prozess pro MT5-Broker-Verbindung (aktuell also 3), jeder auf einem **eigenen,
  dedizierten Windows-Server** — nicht nur ein eigener Prozess auf derselben Maschine
  wie OFAI, sondern eigene Hardware/VM pro MT5-Instanz. Grund: siehe
  "Deployment"-Abschnitt unten.
- Config-Aufteilung (siehe "Vorbereitung auf Active/Passive" für die genaue
  Begründung): Worker startet mit einer **minimalen, installationsfesten** lokalen
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
- Öffnet einen lokalen Listening-Socket, wartet auf Verbindung vom Hauptprozess.
- **Schreibt eigene Logdateien** (siehe unten).

## Deployment: separate Windows-Server je MT5-Instanz

Jede MT5-Instanz läuft auf einem eigenen, dedizierten Windows-Server, nicht nur als
eigener Prozess auf derselben Maschine. Das ist bewusst mehr als nötig für das reine
"eine Verbindung pro Prozess"-Problem — der Grund ist Vorbereitung auf später (siehe
nächster Abschnitt): getrennte Hardware ist Voraussetzung für ein echtes
Active/Passive-Setup, das bei einem Server-Totalausfall (nicht nur Prozess-Absturz)
noch funktioniert.

Damit ist die IPC-Verbindung zwischen OFAI und einem Worker **nicht mehr localhost**,
sondern echtes Netzwerk (siehe "Sicherheit" unten für die daraus folgende
Anforderung).

### 3. Naming-Konvention

`MT5_<BROKER>` als stabiler Bezeichner je isolierter MT5-Verbindung — verwendet für:
Worker-Prozessname, Config-Dateiname, Log-Datei-Präfix. Unabhängig davon, ob die
Anbindung später direkt oder über localhost läuft (Namensgebung ist von der
Transport-Wahl entkoppelt).

Aktuell 3 Broker → 3 unabhängige Worker-Prozesse, 3 Config-Dateien, 3 Log-Präfixe, z.B.
`MT5_OXS_T`, `MT5_<Broker2>`, `MT5_<Broker3>`.

Für V2 (Active/Passive) offen: vermutlich `MT5_<BROKER>_PRIMARY` /
`MT5_<BROKER>_SECONDARY` als Suffix — noch nicht festgelegt, da V2 noch nicht gebaut
wird.

### 4. IPC / Nachrichtenformat

- `AgentMessage` → JSON, zeilenweise über einen lokalen TCP-Loopback-Socket
  (newline-delimited JSON — einfach, robust genug für localhost).
- Zusätzlicher, kleinerer Kanal für `MonitoringEvent` (die eine verbleibende direkte
  Objekt-Referenz, siehe oben).
- Transport bewusst austauschbar gehalten: TCP heute, später z.B. Named Pipes oder
  Unix-Domain-Sockets möglich, ohne dass sich Framing/Format oder die OFAI-Seite ändern
  müssen.

## Logging (eigenständiges Broker-Modul)

Jeder Worker-Prozess schreibt eigene, durchsuchbare Logdateien (nicht nur stdout —
das ist beim Wrapper-Modell nachträglich kaum analysierbar). Mindestinhalt:

- Verbindungsaufbau/-abbruch zum MT5-Terminal (inkl. `mt5.last_error()` bei Fehlern).
- Jeder `mt5.*`-Aufruf mit Latenz — analog zum bestehenden "Slow MT5 call detected"-Log
  in `mt5.py`.
- Jede ein-/ausgehende Bus-Nachricht (Typ + Korrelation, nicht zwingend volle Payload).
- IPC-Verbindungsstatus zum Hauptprozess (verbunden/getrennt/Wiederverbindung).

Ablage- und Rotationskonvention an bestehende Log-Struktur anlehnen (`logs/`-Verzeichnis,
Präfix `MT5_<BROKER>_*`, Tages-Rotation wie bei den bestehenden LLM-Transcript-Logs).

## Vorbereitung auf Active/Passive (V2 — nicht Teil von V1)

V1 baut bewusst **nur**: ein Worker pro Broker, eine aktive Verbindung, kein
automatischer Wechsel. Trotzdem soll die Architektur jetzt schon so gestaltet werden,
dass ein Active/Passive-Setup später ergänzt werden kann, ohne die Grundstruktur
(virtuelles Modul, Worker, IPC-Format) noch einmal anzufassen. Die folgenden Punkte
sind **Entwurfsentscheidungen für später**, nicht Teil der V1-Umsetzung.

### Sicherheit (mTLS)

Da die Worker auf separaten Windows-Servern laufen (siehe Deployment-Abschnitt), geht
die IPC-Verbindung über echtes Netzwerk, nicht mehr localhost. Sobald das der Fall
ist, muss die Verbindung abgesichert werden — ein selbstsigniertes/lokales
Zertifikat reicht dafür völlig aus, keine echte PKI nötig. Wichtig dabei: **mutual
TLS**, nicht nur einseitiges TLS — sonst ist der Kanal zwar verschlüsselt, aber jeder
im Netz, der den Port erreicht, könnte trotzdem eine Verbindung aufbauen und
Nachrichten einschleusen. Beide Seiten müssen sich gegenseitig über Zertifikate
authentifizieren.

### Warum kein einfaches gegenseitiges Heartbeat zwischen genau zwei Workern

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
Pfad: **der Broker-Account selbst**, den beide Worker ohnehin über's Internet
erreichen müssen, um überhaupt handeln zu können — nicht eine zusätzliche, separat zu
betreibende dritte Maschine.

### Lease-basierter Ansatz (statt reines Zwei-Wege-Heartbeat)

Für später vorgesehen, analog zu echten Cluster-Systemen (Kubernetes, etcd,
Zookeeper): der aktive Worker hält einen "Lease" mit Ablaufzeit, den er alle paar
Sekunden erneuern muss. Der passive Worker prüft, ob der Lease abgelaufen ist, und
übernimmt nur dann — atomar (prüfen-und-setzen in einem Schritt, nicht getrennt lesen
dann schreiben, sonst Race zwischen zwei gleichzeitigen Übernahmeversuchen). Der
Lease-Speicherort muss die "unabhängiger Pfad"-Anforderung von oben erfüllen.

### Sync-Key-Dedup-Check — Voraussetzung, unabhängig vom Failover-Zeitpunkt

Selbst mit Lease und unabhängigem Pfad bleibt ein Restfall: ein Worker ist *langsam,
aber nicht tot* — die Anfrage wird trotzdem noch verarbeitet, während OFAI (oder der
Lease-Mechanismus) längst auf den anderen Worker umgeschaltet hat. Ergebnis:
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
liegt deshalb nicht in einem bulletproof Konsens-Protokoll zwischen den Workern,
sondern in **schneller, zuverlässiger Erkennung + Alarmierung**, falls doch mal etwas
schiefläuft.

Geplant: **Zabbix** als unabhängige Überwachungsinstanz (läuft auf eigener
Infrastruktur, unabhängig von beiden MT5-Servern). Nicht über den normalen
Zabbix-Agent (der ist für generische Host-Metriken wie CPU/RAM), sondern über
**Trapper-Items** — Worker und OFAI pushen anwendungsspezifische Werte aktiv an den
Zabbix-Server (`zabbix_sender` oder direkt über die Trapper-API). Sinnvolle Items:

- Lease-Zeitstempel je Worker.
- Wer aktuell glaubt, aktiv zu sein (je Worker).
- Duplikat-Zähler für `sync_key`-Kollisionen (sollte immer 0 sein — jeder Wert > 0
  ist ein sofortiger kritischer Alarm).
- IPC-Verbindungsstatus je Worker.

Trigger darauf: "kein Update seit N Sekunden" (Worker hängt/tot), "beide Worker
glauben gleichzeitig aktiv zu sein" (Split-Brain direkt erkannt), "Duplikat-Zähler >
0" (sofort kritisch). Alarmierung muss wirklich auffallen (Zabbix bringt
Telegram-Anbindung mit — passt zum bereits einmal angedachten, pausierten
Telegram-Plan), nicht nur passiv im Log/Monitoring-Tab landen.

### Was V1 davon konkret NICHT enthält

Kein Lease-Mechanismus, kein automatischer Wechsel, keine Zabbix-Integration, kein
zweiter Worker pro Broker. V1 liefert nur: ein Worker pro Broker auf eigenem Server,
saubere Prozess-Trennung, eigenes Logging. Die obigen Punkte bestimmen lediglich,
*wie* V1 gebaut wird (z.B. Config-Push statt geteilte Datei, `sync_key`-Check ergänzen),
damit V2 später ohne Bruch aufsetzen kann.

## Erweiterbarkeit — muss offen bleiben für

- Weitere MT5-Broker: neue Config + neuer Worker-Start, **kein Code-Änderung in OFAI**.
- Andere Broker-Typen, die dasselbe Isolations-Muster brauchen — nicht MT5-spezifisch
  hart verdrahten.
- Austausch des Transport-Mechanismus ohne Auswirkung auf die OFAI-Seite (die Grenze
  ist die Adapter-Schnittstelle, nicht der Socket).
- Spätere Sichtbarkeit im UI, ob ein Worker läuft/gesund ist (nicht Teil des ersten
  Schritts, aber das Design darf das nicht verbauen).
- Active/Passive-Failover (siehe eigener Abschnitt oben) — V1 baut nur den
  Single-Worker-Fall, aber Config-Push-Mechanismus und `sync_key`-Check werden schon
  in V1 so gebaut, dass V2 darauf aufsetzen kann.

## Umsetzungsschritte V1 (grob, nicht endgültig)

1. `RemoteMT5Broker`-Grundgerüst (Interface-Kompatibilität, noch ohne echten Transport).
2. IPC-Bridge: Relay-Loop im virtuellen Modul (Bus → Socket) + Shim im Worker
   (Socket → bus-artiges Interface).
3. Worker-Entry-Point-Skript, das den bestehenden `MT5Broker` unverändert mit dem Shim
   verdrahtet — Worker-Config minimal (Account/Passwort/Server/Installationspfad),
   Betriebsparameter per Hello/Config-Nachricht von OFAI.
4. Logging im Worker.
5. `sync_key`-Dedup-Check vor Order-Ausführung ergänzen (unabhängig nützlich, siehe
   "Vorbereitung auf Active/Passive").
6. Umstellung eines der 3 bestehenden Broker als Pilot, Rest nach erfolgreichem Test —
   je auf eigenem, dediziertem Windows-Server.
7. Lebenszyklus/Supervision: Start, Health-Check, Neustart bei Absturz — analog zum
   bestehenden `tools/openforexai-wrapper.py`-Muster.

Lease-Mechanismus, zweiter Worker pro Broker und Zabbix-Integration sind **nicht**
Teil dieser Liste — das ist V2, siehe "Vorbereitung auf Active/Passive".

## Offene Entscheidungen (bewusst noch nicht festgelegt)

- Wer öffnet den Port — Worker lauscht, Hauptprozess verbindet sich, oder umgekehrt?
  Für die Architektur nicht entscheidend, wird bei der Umsetzung fixiert.
- Feste Portvergabe je Broker in der Config, oder dynamisch zugewiesen und im Handshake
  kommuniziert?

## Warum jetzt nicht testbar

Wochenende — ohne laufende Kerzensignale (M5-Trigger) lässt sich die komplette
Order-/Positions-Pipeline nicht sinnvoll durchtesten. Umsetzung und Test ab kommender
Woche.

## Quellen (Recherche zur MT5-Python-Grundlage)

- [MT5/Metatrader 5 connect to different MT5 terminals using python — MQL5 Forum](https://www.mql5.com/en/forum/351590)
- [Python working with multiple MT5 terminals — MQL5 Forum](https://www.mql5.com/en/forum/478406)
- [Documentation on MQL5: initialize / Python Integration](https://www.mql5.com/en/docs/python_metatrader5/mt5initialize_py)
- [Developing a Terminal Manager (Part 2): Running Multiple Terminal Instances — MQL5 Articles](https://www.mql5.com/en/articles/19852)

Konzeptionelle Grundlage für den Active/Passive-Abschnitt (V2): Zwei-Generäle-Problem /
Split-Brain-Vermeidung bei verteilten Systemen (allgemeines, etabliertes Wissen —
Lease-basierte Führerwahl analog zu Kubernetes/etcd/Zookeeper), sowie Zabbix
Trapper-Items/`zabbix_sender` für Push-basiertes Custom-Monitoring.
