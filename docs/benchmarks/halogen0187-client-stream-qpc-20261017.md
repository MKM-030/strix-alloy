Auf der laufenden Halogen-0.18.7-Instanz wurden am Windows-Client 40.41 Token-Ereignisse/s gemessen. Die native MTP-Akzeptanz beträgt 45.11% (180/399).

Nicht repetierter Romanpräfix mit exakt 16.384 Eingabe- und 128 Ausgabe-Tokens, Temperatur 0, Seed 1, MTP2 / Gate0 / PLD3,3, 32K Kontext und 8K Chunk/Arena. Ein Warmup ist ausgeschlossen; alle drei Messläufe bleiben enthalten. Die Instanz behielt Vision, Exact-Cache und das sichtbare Logfenster. Für diese Raw-Anfragen wurde prompt_cache_policy=no_store gesetzt; die tatsächlichen Cache-Zähler sind null.

| Lauf | Client-Token-Ereignisse/s | Erstes Token nach (s) | Ganze Anfrage (s) |
|---|---:|---:|---:|
| 1 | 40.613 | 12.42404 | 15.55377 |
| 2 | 40.342 | 12.43015 | 15.58093 |
| 3 | 40.266 | 12.72130 | 15.88058 |

Mittlere Zeit bis zum ersten Token: 12.52516 s; mittlere gesamte Anfragedauer: 15.67176 s.

Die Rate ist (128−1)/(Ankunft letztes−erstes Token-Ereignis), gepoolt über drei Läufe. Leere Text-Ereignisse zählen mit; Terminal-, Usage- und DONE-Ereignisse zählen nicht als Token. Alle vier Streams einschließlich Warmup haben exakt 128 Token-Ereignisse, konsistent mit usage.completion_tokens und timings.predicted_n. Jeder Byte-Abschnitt mit seinem ursprünglichen QPC-Eingangsstempel wurde offline erneut abgespielt. Zusammen empfangene Ereignisse behalten gleiche Zeitstempel; keine Interpolation oder Token-Retokenisierung.

Diese API-Lieferrate umfasst native Batches, API, Detokenisierung, Gateway, Konsolenbeobachtung und Transport. Sie ist keine reine GPU-Decode-Zeit. Die Zeit bis zum ersten Token umfasst den Anfragepfad und das erste generierte Token; daraus wird keine reine Prefill-Rate abgeleitet. Der Lauf weist keinen Geschwindigkeitsgewinn gegenüber den älteren Nicht-Streaming-Messungen nach. Die ursprünglichen Halogen-Phasenzeiten bleiben getrennte, unabhängig unqualifizierte Beobachtungen.

Ausgabehash in allen vier Läufen: 940e8b3abd3e9ecb0f0d3b14ec3e1df6140eb83c99d219b6b6e2ac27112f7dec. Er entspricht der vorigen 8K-Chunk-Messung. Es gab weder Serverneustart noch Live-Änderung.

Rohbelege: C:\Projects\strix-alloy-clean\server\.local\halogen-update-20261017\goal-next-20261017\stream-qpc\cohort-current
