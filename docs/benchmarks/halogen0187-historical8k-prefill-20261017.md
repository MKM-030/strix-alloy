Der aktuelle Server ist auf dem historischen 8K-Test langsamer. Das ist ein gemessener Anstieg der vollständigen Anfragelatenz; die Ursache und reine GPU-Prefill-Zeit sind damit nicht isoliert.

Exakt derselbe gespeicherte Chattext, 8.192 tatsächliche Eingabetokens einschließlich Template, ein Ausgabetoken, Temperatur0/Seed1, serieller Drafter, Thinking Off. Auf dem unveränderten0.18.7-Serving-Server wurde ausschließlich `prompt_cache_policy=no_store` ergänzt. Je ein ausgeschlossener Warmup und drei Messungen. Alle Ausgaben stimmen mit dem historischen SHA256 überein; Cache-, Disk-Restore- und Draft-Zähler sind null.

| Kohorte | Vollständige Anfrage einschließlich JSON-/Watcher-Abschluss, Mittel ± SD |
|---|---:|
| Historisch0.16.2, Stock A | 4,40341 ± 0,15960s |
| Historisch0.16.2, PLD Off | 4,28128 ± 0,16076s |
| Historisch0.16.2, Stock B | 4,28533 ± 0,14338s |
| Aktuell0.18.7, PLD3,3 | 6.18129 ± 0.03476s |

Die aktuellen drei vollständigen Body-Latenzen sind6,2170081 /6,1686354 /6,1514578s; Mittel6,1790338s. Der historische Messcode beendet seine Uhr nach JSON-Verarbeitung und Memory-Watcher-Abschluss. Deshalb wird zusätzlich derselbe Abschlussumfang erfasst:6,2201672 /6,1704937 /6,1532215s. Gegen Stock B beträgt der Anstieg 44.24%; gegen Stock A 40.38%. Das ist ein Vergleich über unterschiedliche Zeitpunkte/Konfigurationen und kein isolierter Versions- oder Kerneleffekt.

Der ursprüngliche1.925,16-Prefill-Wert ist eine historische API-Phasenbeobachtung mit damaliger Clock-Korrektur. Aktuell meldet die API im Mittel 1234.63tok/s; diese Phasenuhr ist nicht unabhängig qualifiziert. In allen drei Messungen übersteigt bereits `prompt_ms` die vollständige Body-Anfragedauer. Es wurde keine Phase umskaliert oder aus Gesamtzeit/TTFT rekonstruiert. Der Ein-Token-Test liefert keine Decode- oder MTP-Akzeptanzrate.

Unterschiede bleiben sichtbar: damals0.16.2/262K-Kapazität/MAX_TOK32768/CacheOff/ohneVision; aktuell0.18.7/32K-Kapazität/8K-ChunkundArena/Exactmitrequest-no_store/Visiongeladen. Die Anfrage deaktiviert Thinking und spekulative Arbeit. Der Server wurde für diesen Test nicht neu gestartet oder geändert und bleibt online. Es ist weder ein wiederhergestellter Prefill-Höchstwert noch ein gemeinsamer Geschwindigkeitsgewinn nachgewiesen.
