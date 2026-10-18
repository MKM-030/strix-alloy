Die Kombination aus 8K-Prefill und deaktivierter optionaler MTP-Prompt-Vorbereitung wurde direkt gegen den 8K-Standard gemessen. Ein gemeinsamer Höchstwert für Prefill und Decode ist damit nicht nachgewiesen. Der normale 0.18.7-Server läuft wieder auf Port 8840.

Natural prose, 16384 input / 128 output tokens; temperature 0, seed 1; Cache Off, Thinking Off, vision off; MTP depth 2, gate 0, PLD 3,3; context 32768, one slot; one excluded warmup and three measurements per arm.

| Chunk/Arena | MTP-Prompt-Vorbereitung | Gesamte HTTP-Anfrage, Mittel ± SD (s) | Native Akzeptanz | Prefill / Decode laut API* |
|---:|---|---:|---:|---:|
| 4096 | default2 | 16.40400 ± 0.06649 | 177/408 (43.38%) | 1226.13 / 39.20 |
| 4096 | mode0 | 15.95385 ± 0.09376 | 183/396 (46.21%) | 1181.05 / 38.40 |
| 8192 | default2 | 15.42362 ± 0.04432 | 180/399 (45.11%) | 1263.96 / 38.81 |
| 8192 | mode0 | 15.38280 ± 0.06345 | 180/399 (45.11%) | 1272.47 / 38.98 |

*Die Halogen-Phasenwerte sind unabhängig nicht qualifiziert und passen teilweise nicht zur vollständigen QPC-Anfragedauer. Sie sind Beobachtungen, keine belastbaren separaten Prefill-/Decode-Durchsatznachweise. Es wurde nichts umskaliert oder als echter Decode zurückgerechnet.

4K: mode0 verändert den beobachteten HTTP-Mittelwert um -2.744%. 8K: -0.265%. Innerhalb jeder Chunk-Größe sind alle Warmup- und Messausgaben gleich; zwischen 4K und 8K unterscheiden sie sich. Ein vorheriges oder folgendes Kontrollfenster und drei Messungen belegen keinen globalen oder statistisch signifikanten Höchstwert.

Der getrennte Versionsvergleich 0.18.7 → 0.18.5 → 0.18.7 ergab 16.24479 / 16.11876 / 16.40400 s bei identischer Ausgabe und 177/408 nativer Draft-Akzeptanz je Messkohorte. Die alte Version reproduziert den historischen Zustand mit 11.8 s nicht. GPU-Fatbin, GEMM-Pläne und die sechs tatsächlich gemappten Bibliotheken sind gleich; die Ursache des historischen Laufzeitunterschieds bleibt offen.

Der Hipfire-Abgleich findet die untersuchte Head-Nachführung und den kompakten GDN-Launch bereits in Halogen. Es wurde kein zusätzlicher Hipfire-Kernel eingebaut. Die neue enum-begrenzte MTP-Prefill-Schnittstelle und ihre Messbelege bleiben als Kandidat erhalten; Original-Validator und Source-Pins wurden im laufenden Paket wiederhergestellt. Keine NPU-Beschleunigung wird behauptet.

Die früheren 1925.16 Prefill-tok/s gehören zu 0.16.2 mit 8192 Eingabe-/1 Ausgabe-Token in einem seriellen Pseudoprose-Test. Rund 70 API-Decode-tok/s gehören zur separaten gesampelten Code-Anfrage mit 200 Eingabe-/321 Ausgabe-Tokens. Diese Spitzen lassen sich nicht zu einer gemessenen Konfiguration zusammenziehen.

Der wiederhergestellte Server nutzt 8K Chunk/Arena, 32K Kontext, Vision, Exact-Cache und die bisherigen Thinking-Defaults. Dieses Serving-Profil unterscheidet sich ausdrücklich vom CacheOff/ThinkingOff-Textbenchmark. mode0 bleibt bis zu einer stärkeren Qualifikation deaktiviert. Der Server ist authentifiziert geprüft und bleibt für ServiceNow offen.

Rohbelege:
- C:\Projects\strix-alloy-clean\server\.local\halogen-update-20261017\goal-next-20261017\version-bracket-4k\analysis\results.json
- C:\Projects\strix-alloy-clean\server\.local\halogen-update-20261017\goal-next-20261017\prompt-head-policy\runtime-prep\comparison\results.json
- server\.local\halogen-update-20261017\goal-next-20261017\prompt-head-policy\runtime-prep\combined8k\comparison\results.json
