# Halogen 0.18.10: Update und Prüfung der 26,5 tok/s vom 18. Oktober 2026

Die 26,53 Decode-tok/s gehören zum nativen Windows-Hipfire-Port mit MQ2 und Rank-q4-PLE. Sie sind kein Halogen-Ergebnis. Der Halogen-Pfad verwendet das vorhandene native HGN-v2-Modell; das ist kein IQ4_XS-GGUF. Der Wechsel zwischen diesen Engines und Modellartefakten ist kein kontrollierter Versionsvergleich.

Das offizielle Update 0.18.10 wurde über den unveränderlichen Image-Digest installiert, der WSL-Adapter frisch gebunden und mit echten Modellanfragen vollständig geprüft. Das Update verbessert laut Upstream die Prompt-Verarbeitung und behebt einen Fehler bei gesampelten rekursiven JSON-Schemas. KV8 bleibt aus.

| Version | Anfrage | API-Prefill tok/s* | API-MTP-Decode tok/s* | Native Head-Akzeptanz | Ganze HTTP-Anfrage, Mittel ± SD |
|---|---|---:|---:|---:|---:|
| 0.18.8 | 8.192 / 128 | 1243.19 | 38.50 | 201/360 (55.83%) | 9.96349 ± 0.25054 s |
| 0.18.8 | 16.384 / 128 | 1170.96 | 36.79 | 180/399 (45.11%) | 17.57065 ± 0.31607 s |
| 0.18.10 | 8.192 / 128 | 1211.77 | 40.87 | 201/360 (55.83%) | 9.94138 ± 0.36360 s |
| 0.18.10 | 16.384 / 128 | 1186.42 | 36.31 | 180/399 (45.11%) | 17.43070 ± 0.31233 s |

*API-Phasen sind Beobachtungen des Engines, unabhängig nicht qualifiziert. Die Raten sind gepoolt: tatsächliche Tokens geteilt durch die Summe der jeweiligen API-Phasenzeiten. Die vollständige HTTP-Zeit stammt separat aus Windows QPC. Es wird nichts umskaliert, durch Overhead-Abzug zurückgerechnet oder als reiner GPU-Kernel-Durchsatz ausgegeben.

Die gesamte Anfrage wird im direkten Versionsvergleich bei 8K um 0,222% und bei 16K um 0,796% kürzer. Bei nur drei Messungen, sichtbarer Streuung und ohne abschließenden Versions-Kontrolllauf ist damit kein belastbarer Geschwindigkeitsgewinn belegt. Akzeptanz und alle 128-Token-Ausgabehashes stimmen zwischen beiden Versionen überein. Die größere API-Decode-Zahl bei 8K wird nicht als entsprechend großer Gewinn der gesamten Anfrage dargestellt.

## Vergleichsbedingungen

Ein ausgeschlossener Warmup und drei gemessene Anfragen je Größe und Version. Tatsächlich 8.192 beziehungsweise 16.384 Eingabetokens, jeweils 128 Ausgabetokens. Der 8K-Fall rekonstruiert den exakten historischen kanonischen Request-Hash mit synthetischer Pseudoprosa; der ursprüngliche HTTP-Wire-Bytestrom wurde nicht erfasst. Der 16K-Fall ist das eingefrorene natürliche Romanpräfix.

Beide Versionen: HGN-v2, 32.768 Kontextkapazität, ein Slot, Chunk und Arena 8.192, MTP2/Gate0/PLD3,3, Vision an und global Exact Cache. Die abgeleiteten Requests ergänzen ausschließlich das unterstützte `prompt_cache_policy="no_store"`; jede Antwort meldet tatsächlich null wiederverwendete Cache-Tokens. `cache_prompt:false` allein wird von der aktuellen API ignoriert. Temperatur 0, Seed 1, explizites Thinking Off pro Request; die normalen Serving-Defaults mit Thinking bleiben im Profil erhalten.

Der Collector meldet für beide vollständigen Serien bestandene 18-GiB-Laufzeitreserven und unveränderte 22-GiB-Request-Zulassung. Vor den Messfenstern wurden keine League-/Riot-Prozesse oder aktiven Windows-GPU-Engine-Zähler gefunden. Es läuft jeweils nur eine große Engine.

## Warum frühere Spitzen keine gemeinsame aktuelle Referenz sind

48,424 Decode mit 1.866,537 MTP-Prefill gehörten zu Halogen 0.16.2, dem historischen 8K-Request, 262.144 Kontextkapazität, 32K Chunk/Arena, Cache Off und dem damaligen Hostzustand. 1.925,160 Prefill gehört zu einer separaten seriellen PP8192/TG1-Zelle mit PLD Off. Rund 70 Decode-tok/s stammen aus einem anderen gesampelten Code-Workload. Diese Werte sind hier nicht reproduziert und werden nicht zu einem neuen Ergebnis kombiniert. Die heutige Versionspaarung belegt keine einzelne Ursache sämtlicher historischer Unterschiede.

Die bisherigen adaptiven Greedy-MTP-Versuche rechtfertigen keinen neuen Standard: Im passenden 0.18.5-Natural16K-Vergleich war der Kandidat rund 3,29% langsamer. Seine höhere Akzeptanz entstand bei gleicher Zahl akzeptierter Tokens durch weniger entworfene Tokens. MTP2/Gate0 bleibt erhalten. Für größere Arena-Werte liegt ebenfalls kein qualifizierter aktueller Gewinn vor.

## Fehler, Wiederherstellung und aktueller Betrieb

Der erste Messversuch scheiterte an der 22-GiB-Request-Zulassung und einer nachträglich geänderten Collector-Informationszeile. Er bleibt fehlgeschlagen und zählt nicht zu den Ergebnissen. Für den abgeschlossenen Vergleich wurden Quellen und Collector eingefroren.

Der alte Server stoppte sauber, behielt aber eine Sperre zurück, weil die relative Speichererholung noch 38,032 GiB aus dem früheren Startzustand verlangte. Die genaue verwaiste Sperre wurde nach Nachweis beendeter Prozesse, terminalem Container, freien Ports und frischer normaler Startzulassung quarantänisiert. Der historische Recovery-Fehler bleibt unverändert; Start- und Laufzeitgrenzen wurden nicht gesenkt. Die nachfolgenden beiden Messinstanzen stoppten regulär.

Nach beiden erfolgreichen Serien scheiterte nur das Schreiben der Vergleichsdatei an einem doppelten `utc`-Schlüssel im Koordinator. Die unveränderten Rohbelege und Zusammenfassungen wurden offline vollständig erneut ausgewertet; keine Anfrage wurde dafür wiederholt.

Die Startskripte und ihre Integritätsbindungen sind auf das geprüfte 0.18.10-Profil aktualisiert. Während des abschließenden normalen Starts wurde Halogen jedoch extern per regulärem Stop beendet und auf Port 8840 ein Gemma-4-Controller gestartet. Dieser fremde Lauf wird nicht übernommen oder beendet. Daher wird ausdrücklich nicht behauptet, dass Halogen am Abschluss online ist. STT/TTS und fremde Programme bleiben unangetastet.

[Maschinenlesbare Ergebnisse](halogen01810-regression-check-20261018.json) · [Hipfire-Messung](hipfire-native-windows-20261018.md) · [Historische 8K-Messung](halogen0162-pld-stock8k-20261004.md) · [Offizielles Changelog](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/v0.18.10/CHANGELOG.md)

Private Rohbelege: `server/.local/halogen-update-20261018/primary01810/bench-results/cohort-{0188,01810}-fresh`. Der vollständige Beschleunigungsauftrag ist weiterhin nicht erreicht.
