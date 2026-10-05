# Halogen 0.16.2: echte 128K- und 260K-Eingaben, 5. Oktober 2026

Beide Serien sind vollständig: ein ausgeschlossener Warmup und drei Messläufe pro Größe. Die nachfolgend angegebenen Tokenraten sind die arithmetischen Mittel der drei Messläufe. Akzeptanz ist die Summe der nativen akzeptierten Entwürfe geteilt durch die Summe der entworfenen Tokens.

| Tatsächliche Eingabetokens | Prefill tok/s | MTP-Decode tok/s | Native Akzeptanz | Akzeptiert / entworfen |
| ---: | ---: | ---: | ---: | ---: |
| 131,072 | 1177.60 | 36.67 | 47.33% | 186 / 393 |
| 260,000 | 1104.87 | 36.81 | 51.20% | 192 / 375 |

## Messbedingungen

- Qwen3.8-Flash-Next, natives v2-HGN-Checkpoint; originale GPU-Kernels von Halogen 0.16.2 über WSL2/DXG.
- Kontextkapazität 262.144, ein Slot, MTP-Tiefe 2, PLD 3,3. Die nativen Draft-Zähler beziehen sich auf diesen konfigurierten MTP/PLD-Pfad.
- `HALOGEN_MAX_TOK=8192` und `HALOGEN_PREFILL_CHUNK=8192`, im tatsächlich gestarteten Manifest belegt.
- Ein einmaliges Romanpräfix aus War and Peace mit eingefrorener Fortsetzungsaufgabe und Thinking-Off-Framing; weder Padding noch wiederholte Textblöcke.
- Exakt 131.072 beziehungsweise 260.000 native Eingabetokens einschließlich Framing; jeweils 128 Ausgabetokens, Temperatur 0, Seed 1.
- Prompt-Cache aus; jede Antwort meldet `cache_n=0` und `disk_restore_n=0`. Die Dateicaches wurden durch den jeweiligen ausgeschlossenen Warmup aufgewärmt.
- Alle vier greedy Ausgaben jeder Größe sind bytegleich. Die erzeugte Prosa wurde auf repetitive Textblöcke geprüft.
- Native Prefill-/Decode-Zeiten mit der gespeicherten Windows-QPC/Guest-Clock-Kalibrierung; keine Ableitung aus Komponentenlatenzen.
- Vor jeder Anfrage mindestens 22 GiB physische und Commit-Reserve; durchgehend mindestens 18 GiB überwacht.

## Ausgeschlossene Warmups und Streuung

| Eingabetokens | Warmup Prefill | Warmup Decode | Gemessene Prefill-Spanne | Gemessene Decode-Spanne | Mindestreserve physisch / Commit |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 131,072 | 782.47 | 30.12 | 1173.06–1182.44 | 36.62–36.74 | 29.19 / 122.06 GiB |
| 260,000 | 936.48 | 26.64 | 1096.10–1109.96 | 36.74–36.92 | 25.63 / 118.48 GiB |

## Aussagegrenzen und Betriebszustand

Die früheren ungefähr 48,42 tok/s gehören zum 8K-Workload bei 262.144 Kontextkapazität. Sie sind kein Wert für 262K tatsächliche Eingabetokens. Diese neuen Roman-Workloads lassen sich nicht als Geschwindigkeitsänderung gegenüber dem historischen 8K-Workload oder einem früheren fehlgeschlagenen Warmup ausweisen.

Die NPU ist in diesen Läufen ausgeschaltet. Die separat gemessene gepaarte Projektion war mit 1,850 ms langsamer als die GPU mit 0,487 ms; ein vollständiger NPU-An/Aus-Vergleich in tok/s liegt weiterhin nicht vor. Die Genauigkeitsqualifikation des vollständigen Hidden-/MTP-Kopfs ist weiterhin offen.

Der reguläre Stop hatte zunächst die ursprüngliche Speicher-Rückgewinnungsschwelle verfehlt. Ein späterer Nachweis mit derselben Schwelle qualifizierte die Freigabe; der ursprüngliche Fehler wurde erhalten. Beim neuen Start wurden die veralteten Paket-Prüfsummen der bereits geänderten Startdateien korrigiert. Beide Messserien liefen anschließend ohne weiteren Neustart auf derselben Instanz. Die Engine-Startlogs melden zuvor 12,3 GiB Arbeitsbereich bei max_tok 32768 und jetzt 5,6 GiB bei max_tok 8192, also rund 6,7 GiB weniger nach den gerundeten Engine-Angaben. Dies belegt die Speicherreduktion; ein kontrolliertes Geschwindigkeitsdelta zur alten Arena wird daraus nicht abgeleitet.

Der Server bleibt danach auf `http://127.0.0.1:8840/v1` bereit und offen. Die aktuelle menschliche Freigabe für automatische Messneustarts und den erforderlichen offenen Endzustand ist im Fortsetzungsstand gespeichert.

[Maschinenlesbare Belege](halogen0162-natural-long-20261005.json) enthalten Run-Identitäten, alle Messläufe, Ausgabetexte und Prüfsummen der gespeicherten Rohdateien.
