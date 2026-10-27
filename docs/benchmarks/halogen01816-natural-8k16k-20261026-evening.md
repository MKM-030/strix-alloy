# Halogen 0.18.16: neue 8K-/16K-Messung vom 26. Oktober 2026

Qwen3.8 Flash Next, unverändertes v2-Modell, 32.768 Kontextkapazität.
Je ein ausgeschlossener Warmup und drei vollständige Messläufe mit 128
Ausgabetokens. Eingefrorene natürliche Texte, Temperatur 0, Seed 1,
Thinking Off, Cache Off/no_store, MTP mit Gate 0,90, PLD 3,3,
Prefill-Chunk und Arbeitsbereich jeweils 8.192. NPU-Helfer deaktiviert.

| Tatsächliche Eingabetokens | Prefill tok/s | MTP-Decode tok/s | Native Akzeptanz | Akzeptiert / vorgeschlagen |
|---:|---:|---:|---:|---:|
| 8.192 | **2.033,12** | **56,93** | **66,04 %** | 210 / 318 |
| 16.384 | **2.002,08** | **49,63** | **52,68 %** | 177 / 336 |

Tokenraten sind arithmetische Mittel der drei Messläufe auf direkt erfassten
CLOCK_MONOTONIC_RAW-Phasen. Akzeptanz ist der Quotient der summierten nativen
Zähler nach Warmup-Ausschluss. Decode verwendet Halogens Konvention von 128
Tokens; der beobachtete Zählerunterschied an den Endpunkten beträgt 127.

Die Antworten sind normale Textfortsetzungen. Es wurden keine künstlich
repetierten Tokenfolgen erzeugt. Die beiden Zeilen behalten ihre jeweiligen
eingefrorenen Texte und sind keine isolierte Kontextskalierung desselben Prompts.

## Abweichende API-Zeiten

| Eingabe | Native API Prefill tok/s | Native API Decode tok/s |
|---:|---:|---:|
| 8.192 | 1.876,97 | 52,47 |
| 16.384 | 2.002,08 | 49,63 |

Bei 8K weichen die direkt beobachteten nativen und RAW-Intervalle voneinander
ab; bei 16K stimmen sie praktisch überein. Deshalb wurde kein gemeinsamer
Umrechnungsfaktor angewandt. Die RAW-Phasensummen passen in jedem Lauf in die
separat mit Windows QPC gemessene vollständige HTTP-Dauer. Das begründet keine
absolute Uhrensynchronisierung. Beobachter-Overhead ist enthalten und wurde
nicht abgezogen.

Der bisherige feste 8K-Zeitbeobachter blieb unverändert. Die getrennte
16K-Variante ändert ausschließlich die feste Eingabelänge, die dazugehörigen
Validierungen und den Prefill-Zähler. Hookstellen, ABI und GPU-Kernel bleiben
unverändert. Die 16K-Variante bestand ihre Testgegenprobe und alle 17
CPU-Prüfungen vor der tatsächlichen Messung. Alle acht Modellanfragen wurden
genau einmal gesendet; eine vorherige Metadatenprüfung scheiterte vor dem
ersten Benchmark-POST und wurde mit einem separat eingefrorenen Paket behoben.

Der aktuelle OEM-Modus konnte mangels erhöhtem Prozesstoken nicht ausgelesen
werden; es wurde kein Modus geändert. Dies ist keine kontrollierte Zuordnung
eines Geschwindigkeitsgewinns zu einer einzelnen Optimierung und kein
Nachweis eines NPU-Gewinns.

Nach beiden Messserien wurden die Zeitbeobachter entfernt und das normale
sichtbare Serverprofil wieder gestartet. Startgrenze 30 GiB und Laufreserve
18 GiB bleiben erhalten. Der Server bleibt für die weitere Nutzung offen.

Die vollständigen Einzelzeiten, Hashes und Prüfnachweise stehen im
[JSON-Messbericht](halogen01816-natural-8k16k-20261026-evening.json).
