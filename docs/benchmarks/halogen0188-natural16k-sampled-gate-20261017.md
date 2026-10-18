Halogen 0.18.8 ist installiert. Der feste 16K-Texttest und ein einzelner gesampelter MTP-Kandidat sind vollständig gemessen. Ein gemeinsamer globaler Prefill-/Decode-Höchstwert ist nicht belegt.

Je Zelle: ein ausgeschlossener Warmup und drei Messungen; 16.384 echte Eingabe-/128 Ausgabetokens, 32K Kapazität, Chunk/Arena 8192, Cache Off, Thinking Off, Vision Off, IQ4/v2. Greedy: Temperatur 0, Seed 1, MTP-Tiefe 2. Gesampelt: Temperatur 0,7, top_p 0,95, top_k 20, min_p 0, Seed 1; native maximale Draft-Tiefe 7 ohne Override. Die Anfrage bleibt zwischen allen drei gesampelten Fenstern bytegleich. Gate 0.95 senkt nur die Schwelle für den dritten und weitere Drafts gegenüber dem Standard 0.95,0.98.

| Test | API-Prefill tok/s* | API-Decode tok/s* | Native Akzeptanz | HTTP-Anfrage, Mittel ± SD |
|---|---:|---:|---:|---:|
| Greedy, Standard | 1234.87 | 36.10 | 180/399 (45.11%) | 16.90118 ± 0.24049 s |
| Gesampelt, Gate 0.95,0.98 davor | 1140.76 | 35.65 | 204/333 (61.26%) | 16.81894 ± 0.18995 s |
| Gesampelt, Gate 0.95 | 1226.02 | 38.44 | 219/357 (61.34%) | 16.77317 ± 0.12454 s |
| Gesampelt, Gate 0.95,0.98 danach | 1200.51 | 38.50 | 204/333 (61.26%) | 17.07532 ± 0.03534 s |

*Die nativen API-Phasenwerte sind unabhängig nicht qualifiziert. Die komplette HTTP-Dauer wurde mit Windows QPC gemessen und ist die Vergleichsbasis. Phasen wurden weder skaliert noch durch Abzug von Overhead zurückgerechnet. Nicht als qualifizierte separate Prefill-/Decode-Postwerte verwenden.

Der MTP-Kandidat verändert die vollständige Anfrage um -1.027% gegenüber dem Mittel beider Standardfenster. Die beiden Standardfenster driften um +1.524%. Mehr Akzeptanz allein beweist keine Beschleunigung; Ausgaben, tatsächliche Tokenzahlen, alle Fehlschläge und Originalzähler bleiben erhalten. Die gesampelte 128-Token-Fortsetzung ist keine vollständige Qualitäts- oder Verteilungsprüfung. Der Kandidat wird nicht als Produktionsstandard übernommen.

0.18.8 ändert den untersuchten IQ4-Gather nur durch Adressverschiebungen; die Instruktionen und Ressourcen bleiben gleich. Der neue KV8-Roundtrip-Probe bleibt deaktiviert. Die neuen Cache-Funktionen stellen keinen nachgewiesenen kalten Prefill-Kernelgewinn dar. Flexible Cache wurde nicht stillschweigend eingeschaltet. Die abgeschlossenen Hipfire-Kohorten wurden nicht wiederholt.

Die anfänglichen Lifecycle-/Portfehler liegen vor jeder Benchmarkanfrage und bleiben separat erhalten: originaler Stop mit Cleanup=true/Recovery=false, identitätsgeprüfte Beendigung des eigenen hängenden Observers, belegter Port 8841 unverändert. Die eigentliche vollständige Messreihe verwendet den vor dem Stop geprüften Port 8842. Start- und Laufzeitreserven wurden nicht herabgesetzt.

Der normale Server läuft anschließend auf Port 8840 mit Vision, Exact Cache und den bisherigen Thinking-Defaults. Dieses Serving-Profil unterscheidet sich ausdrücklich vom Textbenchmark. Das vollständige Beschleunigungsziel bleibt unerreicht.

Rohbelege: `server/.local/halogen-update-20261017/goal-next-20261017/primary0188/{finite-trial-port8842,greedy-trial-prep/results,mtp-trial-prep/results}`.
