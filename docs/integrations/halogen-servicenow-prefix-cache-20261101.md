# ServiceNow-Folgefragen: Prefix-Cache geprüft

Nach Marcels erneuter Freigabe wurde der vorbereitete Vergleich mit
Cache Off → Flexible → Off durchgeführt. Alle 28 Anfragen sowie Antwortgleichheit
und die A/B-Gesprächsprüfung sind belegt. Der normale Server ist wieder mit
Cache Off online; die ServiceNow-Instanz wurde nicht geändert.

Bei der Folgefrage mit 8.121 tatsächlichen Eingabetokens wurden 8.064 Tokens
wiederverwendet und 57 neu verarbeitet. Der erste Text kam im Mittel nach
0,324 statt 4,21–4,34 Sekunden; die vollständige Antwort nach 0,558 statt
4,45–4,57 Sekunden. Die MTP-Head-Akzeptanz blieb bei 42/48 = 87,50 %.
Kalte erste Anfragen waren mit Flexible langsamer. Siehe den
[vollständigen Messbericht](../benchmarks/halogen01822-cache-followups-20261101.md).

Die lokale PowerShell-5.1-Option `-Profile FollowupText32K` stellt genau diese
Flexible-Konfiguration bereit. `CurrentText32K` und der laufende Server bleiben
unverändert bei Off. Für die tatsächliche ServiceNow-Promptform ist weiterhin
eine eigene Integrationsevaluation erforderlich.

## Ziel und Vergleich

Ein stabiler Dokumentkontext mit einer neuen Frage könnte erneut verwendbare
Eingabetokens liefern. Das kann die Wartezeit einer Folgefrage reduzieren.
Es ist ein eigener Vergleich zu vermiedener Arbeit; die bestehenden
[Cache-Off-Prefill-/Decode-Werte](../benchmarks/halogen01822-raw-8k16k-20261101.md)
bleiben unverändert.

Die vorbereitete Variante ändert ausschließlich den vorhandenen Cache-Modus
von Off auf Flexible. Kontext/Pool 32K, ein Slot, Chunk/Arena 8192, MTP-Gate 0,90,
PLD 3,3 und die bestehenden Reserven bleiben gleich. Es gibt keine neuen
Keep-Header und keine aktivierte NPU.

Vier Fragepaare sind vorbereitet, jeweils mit identischem Dokumentpräfix und
unterschiedlicher letzter Frage. Das erste Paar dient später als ausgeschlossener
Warmup; drei Paare wären Messwerte. Vier separate, verschachtelt angeordnete
Gesprächsanfragen prüfen bekannte, voneinander abweichende Kennungen.

Das private Dokument ist ein eingefrorener Romanpräfix mit 32.693 Unicode-Zeichen
und 33.397 UTF-8-Bytes. Vollständige Antworten belegen 8.126 Tokens für die erste
und 8.121 für die Folgefrage. Diese Anfragen sind ein eigener Workload und
ersetzen nicht die früheren genau 8K-/16K-Referenzen.

## Was bereits geprüft ist

Der [portable Offline-Helfer](../../scripts/benchmarks/halogen_cache_followup/README.md)
hat 40 bestandene CPU-Tests mit künstlichen Fixtures. Er prüft gestückelte
UTF-8-/SSE-Daten, vollständige Antwortidentität, Fehler und unvollständige Streams, finale
Nutzungsdaten und die getrennten nativen MTP-Zähler. Die Auswertung verlangt:

- vollständige Eingabe = gecachte + neu verarbeitete Tokens;
- tatsächlich kalten ersten Durchlauf und echte Wiederverwendung der Folgefrage;
- Zeit bis zum ersten nichtleeren Inhaltsereignis und bis zum vollständigen DONE;
- Warmup getrennt von drei vollständigen Paaren;
- bekannte Gesprächskennungen sowie identische Ausgaben/Längen zwischen
  Vergleichsvarianten als zusätzliche Laufzeitprüfung.

Ein vollständiges natives Stop-Ergebnis unterscheidet für sich genommen nicht
zwischen regulärem Ende und einer nativen Stornierung. Die Laufzeitprüfung muss
deshalb zusätzlich eigene Stornierung, Ergebnisvollständigkeit und die bekannten
Sentinel-Antworten belegen.

Die Testzeiten und künstlichen Cache-Treffer belegen nur die Offline-Auswertung.
Der getrennte Root-Vergleich ergänzt die tatsächlichen Treffer,
Reserve-/Laufzeitdaten, Antwortgleichheit und Gesprächsprüfung. Aus vollständigen
oder gecachten Eingabetokens wird keine vermeintliche Prefill-Rate berechnet.

## Grenze der bestehenden ServiceNow-Implementierung

Der SCC-Transformer verarbeitet einen zusammengefassten Prompt. Caller-Kontext
und Ledger hängen von dessen bisheriger Gesamtform ab. Eine mögliche spätere
Aufteilung muss deshalb erst im abschließenden Transport nach diesen Helfern
erfolgen und sämtliche Rollen, dynamischen Inhalte, Schema- und Dispatch-Regeln
erhalten. Auch frühe Werkzeug-/Fallback-Felder können sich ändern und den
wiederverwendbaren Präfix begrenzen. Der frühe Verweis auf aktuelle Zeit ist
teilweise eine statische Anweisung; er belegt keine wechselnden Zeitstempel.

Zusätzliche Chat-Grenzen verändern die native Formatierung. Eine solche
Transportänderung ist daher eine eigenständig zu prüfende Variante. Der aktuelle
Transformer, die Guards und der bereits eingefrorene Agent-Wartungsschritt
wurden nicht angefasst; dessen konkrete SDK-Freigabe bleibt separat offen.

Private Quellbelege und eingefrorene Anfragen liegen unter
`server/.local/halogen-update-20261101/primary01822/cache-followup-prep/`.
Weitere Messungen behalten die normalen Zulassungs- und Ownership-Regeln.
Das vollständige Optimierungsziel bleibt offen.
