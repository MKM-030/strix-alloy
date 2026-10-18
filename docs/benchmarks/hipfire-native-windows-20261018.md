# Native Windows Hipfire, 18. Oktober 2026

Der Windows-Quellport lädt das vollständige vorhandene Qwen3.8-Flash-Next-MQ2-Modell mit Rank-q4-PLE und führt native GPU-Inferenz aus. Der eingefrorene natürliche 16K-Workload wurde mit einem ausgeschlossenen Warmup und drei Messläufen abgeschlossen.

| Messlauf | Tatsächliche Eingabe / Ausgabe | Prefill tok/s | MTP Decode tok/s | Akzeptiert / entworfen | Anfrage bis Done |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 16.384 / 128 | 1.245,7 | 26,0 | 70 / 110 | 18,094 s |
| 2 | 16.384 / 128 | 1.239,3 | 26,7 | 70 / 110 | 18,062 s |
| 3 | 16.384 / 128 | 1.235,6 | 26,9 | 70 / 110 | 18,047 s |
| Mittel / Summe | 16.384 / 128 | **1.240,2** | **26,53** | **210 / 330 = 63,64 %** | **18,068 s** |

Die Tokenraten sind arithmetische Mittel der nativen, gerundeten Phasenfelder. Die Akzeptanz verwendet die tatsächlichen angebotenen Draft-Tokens. Die gesamte Anfragedauer enthält Prefill und Decode; deren gepoolter Ausgabedurchsatz ist 384 / 54,203 s = 7,0845 tok/s und damit eine andere Messgröße.

## Aufbau und Messbedingungen

- Hipfire `ddee82c7464946c86f946d89af1b5634f212d466`, vorhandene Offered-Draft-Instrumentierung und elf Dateien des Windows-Ports; Quell-Pins vor und nach dem finalen Build identisch.
- Windows x64, Ryzen AI Max+ 395 / Radeon 8060S `gfx1151`, HIP SDK 7.2, Rust 1.99.1 und MSVC. 128 GiB eingebauter Arbeitsspeicher, 63,647 GiB für Windows sichtbar; GPU-reservierter Speicher wird separat behandelt.
- Vorhandenes MQ2-XTS-4500-Basismodell mit 44.537.253.400 Bytes und unveränderte Rank-q4-PLE-Datei mit 29.120.146.432 Bytes. Kein Modelldownload, keine Treiberänderung und keine Änderung der Kernelmathematik.
- 32.768 Kontextkapazität, q8-KV mit Windows-Legacy-Backend, MTP K2, Inline-q8-GDN an, NPU und n-gram takeover aus.
- Eingefrorener, nicht repetitiver Roman-Prompt mit SHA256 `a818a059b4e04fd4f4f949a82b9bf585f396efaddb7d667e0b1f2b9f7b236d5d`; exakt 16.384 gerenderte Eingabetokens, 128 Ausgabetokens, Temperatur 0, top_p 1 und Repeat-Penalty 1. Thinking aus.
- Jede Anfrage meldet null Cache-Tokens. Zwischen Anfragen werden Sequenzposition und Gesprächslänge auf null zurückgesetzt. Der Betriebssystem-Dateicache wird durch den ausgeschlossenen Warmup aufgewärmt.
- Alle drei gemessenen Ausgaben sind bytegleich: 541 UTF-8-Bytes, SHA256 `ae7f60c09c03e0e18d446010460f60b21523c89a195dbb19b0403560698638ec`. Die Prosa ist plausibel; alle Anfragen enden am 128-Token-Limit. Commit-/Done-Payloads, Attempts und Zähler stimmen überein. Der native Daemon beendet sich regulär über stdin-EOF mit Exitcode 0.
- Der ausgeschlossene Warmup erzeugt einen anderen Text und erreicht nur 180,6 Prefill / 3,6 Decode tok/s bei 126,156 s Gesamtdauer. Sein Cache-/Initialisierungszustand ist kein Messlauf.

## Zeitbasis

Die nativen Felder messen den Host-Pipeline-Verlauf. In `hipfire-generate/src/qwen.rs` umfasst Prefill auch die Vorbereitung des MTP-Kopfs, das erste Ausgabetoken und Context-Mapping. Decode zählt alle 128 Ausgabetokens, einschließlich dieses bereits im Prefill erzeugten ersten Tokens, über das anschließende Decode-Zeitfenster. Hostarbeit, Emission und Abschlussarbeit sind enthalten. Dies sind keine reinen GPU-Event-Zeiten und keine klassische 127-Token-Intervallmessung. `ttft_ms` ist in diesem Pfad ein Alias der Prefill-Dauer.

Der unveränderte Collector verwendet `time.monotonic_ns`. In der verwendeten Python-3.12.10-Umgebung ist das Windows `GetTickCount64` mit nominell 15,625 ms Auflösung, **kein QPC**. Die nativen Phasengrenzen und die externen Empfangszeiten dieser neuen Kohorte stimmen innerhalb dieser Auflösung überein. Frühere widersprüchliche WSL-Phasen werden dadurch nicht nachträglich qualifiziert.

## Speicher und Funktionsumfang

Der Port ergänzt Windows-Positionslesezugriffe für die 26,82-GiB-Rank-Tabelle, den Loader ohne Unix-Cacheworker, die exakte HIP-R0600-ABI und eine Windows-Speicherberechnung. Der erste echte Modellversuch mit dem alten Host-Clamp wurde vom unveränderten OOM-Guard abgelehnt; dieser Fehler bleibt erhalten.

Der erfolgreiche Kandidat ordnet das HIP-LUID exakt einem AMD-DXGI-Adapter zu und begrenzt den GPU-Freiraum durch dessen dedizierte Kapazität minus globale PDH-Dedicated-Nutzung sowie durch die lokale DXGI-Budgetreserve und HIP-Freiraum. Shared/Nonlocal-Speicher erhöht die zugelassene Kapazität nicht. Die enge Ausnahme für einen vom SDK gelieferten Node-Mask-Wert 0 ist auf den zuvor nachgewiesenen integrierten Ein-Gerät-gfx1151-Fall begrenzt. Zusätzlich bleiben 18 GiB Host-Reserve für physische und Commit-Verfügbarkeit sowie die laufende Überwachung erhalten.

Der finale Build meldet rund 35,01 GiB Mindestreserve; die vollständige Modellkohorte rund 40,68 GiB. Ein früherer, separater Build bei gleichzeitig aktivem Halogen hatte die Reserve mit 17,717 GiB unterschritten und dessen Guard ausgelöst. Deshalb wurden die finalen Builds bei beendetem großen Modell ausgeführt. Eine durchgehend eingehaltene Reserve über alle Entwicklungsversuche wird nicht behauptet.

## Vergleich und Auswahl

Dies ist kein identischer A/B-Vergleich mit Halogen oder dem früheren WSL-Hipfire-Versuch. Insbesondere sind MQ2/q4 und Halogens nativer HGN-v2-Pfad unterschiedliche Modellartefakte; das historische v2 ist kein IQ4_XS-GGUF. Die frühere gemeinsame Halogen-Messung mit 8.192 Eingabetokens erreichte 1.884,41 Prefill / 48,232 Decode tok/s; 1.925,16 war eine separate PP8192/TG1-Prefill-Messung. Beide stammen aus der [PLD-off-Zelle des eingefrorenen 8K-Bookends](halogen0162-pld-stock8k-20261004.md), nicht aus der normalen PLD-3,3-Konfiguration. Der historische Prompt verwendet synthetische Pseudoprosa mit Kalibrierungspadding, während die neue 16K-Kohorte ein Romanpräfix verwendet. Rund 70 Decode tok/s stammen aus einem anderen gesampelten Code-Workload. Diese Maxima werden nicht zu einem erfundenen gemeinsamen Ergebnis kombiniert.

Der native Port wird als zusätzlicher Funktionspfad aufgenommen. Ein neuer gemeinsamer Geschwindigkeitsbestwert ist nicht nachgewiesen. Die normale Halogen-0.18.8-Instanz wird nach den eigenen Tests wieder sichtbar und authentifiziert auf Port 8840 bereitgestellt.

[Maschinenlesbare Messdaten und Rohdatei-Prüfsummen](hipfire-native-windows-20261018.json) · [Windows-Build und Start](../../backends/hipfire-windows/README.md)
