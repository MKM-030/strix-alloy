# ReAct-Latenz: gemessene Entscheidung

Stand 23.10.2026. **Der Kompaktausgabe-Anhang und `--ctx-checkpoints 1` sind verworfen.** Beide Versuche waren isolierte, synthetische Modellmessungen. Es gab keine ServiceNow-Geschäftsaktion, keine Produktaktivierung und keinen Nachweis einer verbesserten Live-Latenz. Der bestehende ReAct-Helper, Request-Transformer und das Gemma-Hauptprofil bleiben unverändert.

## Ausgangslage und Aussagegrenze

Ein live eingesehener ReAct-Task nach einem erfolgreichen Kontextabruf brauchte 30,749 s und lieferte eine einzelne `FALLBACK`-Aktion im Modus `collect_input_from_user`. Das strukturierte Statusfeld `Thought` hatte 1.892 Zeichen. Ein weiterer Task wurde beim Auflegen abgebrochen; ein aktueller Kontext-Tool-Loop ist damit nicht belegt. Die sanitisierten lokalen Kontrollanfragen hatten etwa 12.300–13.100 Prompttokens und dauerten selbst mit 73–187 Completiontokens 19,2–24,1 s. **Der große Prefill und der lange strukturierte Statustext sind getrennte Beobachtungen.** Der Zeitanteil des Statustextes am Live-Turn wurde nicht gemessen. Die Vorlage fordert an einer Stelle Kürze, an anderer Stelle 4–5 Sätze; das ist ein konkreter Textkonflikt, aber kein bewiesener alleiniger Latenzgrund.

Der live gesicherte `global.LocalLLMReActExecutionLedger` umfasst 11.160 UTF-8-Bytes und hat SHA-256 `4dd630448e2f18066b717e7725bab9aa1d9c4e5d6dd1c0bdd531daa07147dc1a`. Der live gelesene Request-Transformer umfasst 1.235 Bytes und hat SHA-256 `a0bc5a4a1ec3ae86231553e57f59e51e5cbd8929424aa492a57f21be13e1046d`. Dessen Transport setzt bereits `reasoning_effort: none` und `chat_template_kwargs.enable_thinking: false`; ein zusätzlicher nativer Thinking-Schalter ist nicht begründet. Es fehlt weiterhin der aktuelle Live-Nachweis, dass `aiConfig`, `definition` und `preprocessor_modified_input` im betroffenen Request tatsächlich am Helper ankommen. Quellgleichheit allein belegt die effektive Anwendung nicht.

## Vier-Request-Spike: eingefrorener Umfang und Ergebnis

Verwendet wurden nur die zwei sanitisierten Fixtures `recorded` und `unconfirmed`, jeweils zuerst Baseline und unmittelbar danach Kompaktausgabe. Der Kandidat hängte 556 Zeichen ausschließlich hinter `</recorded_execution_state>` an die Systemnachricht; dessen UTF-8-SHA-256 ist `9e7282d478f0b0f5b266b38f3974fbbf3e515d1ab48afdb51f1cce843cb13061`. Schema, `max_tokens=4096`, Temperatur und übrige Requestfelder blieben je Paar gleich; beide Varianten erhielten dieselben Streaming-Messfelder. Das isolierte Profil nutzte Kontext 32.768, Parallelität 1, `--ctx-checkpoints 0` und `--cache-ram 0`.

| Fixture | Eingabe-SHA-256 | System-SHA-256 Baseline → Kandidat | Wire-SHA-256 Baseline → Kandidat |
| --- | --- | --- | --- |
| `recorded` | `5cb5c09b395270c976be68e82ef845fa7a702f02272b094c910fd5aa91e2ce55` | `9ec8f796008a0cf00c047bcd21f65a3134dce0643a2bb098de0438eea4043a04` → `c2a2faa7da379057ef8d2ec941ff071f2fdced4d8611f8dca38c8c9763548c16` | `a9fec784c7da9a0e494ff282e78f5e57855a4662d4e8f8be60087ba417fc9ca5` → `2881e9e2256db7afb502bb50eed8145f20d5c3dbc70c3bd8bd38f27295cb0a9f` |
| `unconfirmed` | `75db165e5bb80b001c41de229d105fea373914ef4ed76cf392485534436f35c8` | `76018c5090dc3ba895faa5262fe382c141ca9975d788d538c449d15b31b40ce0` → `7b79554541b39aad26fdbc91ffb2668beade412a03b4d98b09e4ebe1ab2b9098` | `a6e527a463ae63bce442619f7421b89edaf250ab0611be48ba5f96a47eee753c` → `79b7d3d67e9eb0480da721a695c054744d13d0262ea4921b6271fc2a5f318213` |

Profil-SHA-256 `ea335895f0cb8f6ded0698ec940cab808a11162187129822ecd9c010efbdb330`, Engine-SHA-256 `4eee91db360703b003ea06b92612366d19ca84938960dae4de68e8bc7ff9bfea`, Modell-SHA-256 `3eca3b8f6d7baf218a7dd6bba5fb59a56ee25fe2d567b6f5f589b4f697eca51d`. Der Lauf dauerte 63,328 s.

| Request in festgelegter Reihenfolge | `Thought`-Zeichen | Completiontokens | Prompttokens / gecacht / verarbeitet | Prefill | TTFT | Terminalzeit |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `recorded` Baseline | 223 | 133 | 13.142 / 0 / 13.142 | 19,304 s | 19,407 s | 22,016 s |
| `recorded` kompakt | 127 | 113 | 13.265 / 13.133 / 132 | 0,484 s | 0,578 s | 2,796 s |
| `unconfirmed` Baseline | 190 | 187 | 13.115 / 0 / 13.115 | 19,806 s | 19,922 s | 23,766 s |
| `unconfirmed` kompakt | 128 | 100 | 13.238 / 13.106 / 132 | 0,479 s | 0,578 s | 2,593 s |

Alle vier Antworten waren schema-gültiges JSON mit `finish_reason=stop`. Beide Paare behielten `FALLBACK`, `collect_input_from_user`, fehlende `Observation` und `last_objective=false`. **Die SHA-256 des vollständigen Action-Objekts unterschied sich jedoch in beiden Paaren.** Bei `recorded` unterschied sich auch `Action Inputs`; bei `unconfirmed` blieb dessen Hash gleich. Die genauen Unterschiede sind aus den ausschließlich gespeicherten Hashes nicht rekonstruierbar. Beide Kandidaten blieben zwar unter 160 `Thought`-Zeichen; `recorded` verfehlte zusätzlich die vorab festgelegte Ein-Satz-Heuristik. Die festgelegten Paritätsgates scheiterten, daher ist der Anhang abgelehnt.

Die kürzeren Zeiten belegen keinen kausalen Backend-Gewinn durch kürzere Ausgabe. Beide Kandidaten folgten direkt einer kalten Baseline und trafen auf mehr als 13.100 gecachte Präfixtokens; die Baselines hatten null. Der Anhang erhöhte den Prompt zudem um 123 Tokens. Eine Beobachtung je Paar in fester Reihenfolge trennt Cache und Reihenfolge nicht vom Kandidateneffekt und erlaubt keine breite Korrektheitsaussage. Ein späterer tatsächlicher Helper-Wire-Prompt wäre nur bei Byteidentität mit den eingefrorenen Kandidatenhashes überhaupt mit diesem Spike vergleichbar. Es wird weder der identische Versuch wiederholt noch der verworfene Anhang über einen Installer-Schalter aktiviert.

Die Startprüfung sah 47,642 GiB freien physischen Speicher sowie idle Haupt-Gemma und Native. Das längste Wächterintervall war 0,234 s; der kleinste freie Speicher 46,695 GiB und damit über der 18-GiB-Reserve. Peak Private Bytes des eigenen Prozesses betrugen 15,815 GiB, keine GPU-Messung. Die eigene PID 20672 ist beendet, Port 52744 freigegeben und das temporäre Tokenverzeichnis entfernt. Der Postcheck sah 47,729 GiB frei sowie weiterhin idle Haupt-/Native-Dienste.

## Separater Checkpoint-Vergleich

Der frühere A/B-Vergleich verwendete acht synthetische Anfragen, vier je Arm, und dauerte 199,25 s. Die Wire-Requests waren je Zeile zwischen `--ctx-checkpoints 0` und `1` identisch; alle Antworten waren parsebares JSON mit `finish_reason=stop` und gleicher Aktion, gleichem Modus und `last_objective` je Eingabe. Beim identischen warmen `recorded`-Request traf **bereits Checkpoint 0** 13.141 gecachte Tokens, verarbeitete nur ein Token und brauchte 0,054 s Prefill. Checkpoint 1 traf denselben Cache, brauchte aber 4,591 s. Bei `unconfirmed` und dem Rückwechsel zu `recorded` hatten beide Arme null gecachte Tokens; Checkpoint 1 verarbeitete den vollen Prompt und brauchte 28,845 bzw. 28,903 s Prefill gegenüber 19,689 bzw. 19,811 s bei Checkpoint 0. Die vorab verlangten zusätzlichen positiven Cache-Hits oder verarbeiteten-Token-Einsparungen traten nicht ein (`eligible=false`, `no_positive_hit_or_processed_token_reduction`). Die A→B-Reihenfolge und einzelne Messung pro Fall begrenzen die Verallgemeinerung; für die vorab definierten Annahmegrenzen reicht das Scheitern. Der offene Sliding-Window-Checkpoint-TODO bleibt ein zusätzliches Korrektheitsrisiko. Das Hauptprofil bleibt bei Checkpoints 0, Kontext 32.768 und Parallelität 1.

Beide eigenen Checkpoint-Prozesse (PIDs 5692 und 13124) sind beendet, der Port ist frei und das temporäre Tokenfile-Verzeichnis entfernt. Die maximalen Wächterintervalle waren 0,219/0,235 s, der kleinste freie Speicher 46,529/46,449 GiB und Peak Private Bytes 15,884/16,064 GiB. Der Nachcheck sah 47,640 GiB frei, Haupt-Gemma `ready` mit null aktiven Requests und Native mit null Sitzungen.

## Gates für eine materiell andere künftige Optimierung

Ein neuer Vorschlag braucht zuerst einen legitimen Nachweis am aktuellen Live-Request, dass die drei Scope-Metadaten und eine echte abgeschlossene Observation den Helper erreichen; nur Präsenz, Zähler und Hashes dürfen dafür protokolliert werden. Vor einem Helper-Eingriff sind der aktuelle Live-Quelltext und Hash zu sichern. Fehlende oder missgebildete Scope-Daten sowie ein Request ohne abgeschlossene Observation müssen weiterhin exakte No-ops sein. Native Reasoning und die bestehende Tool-, Autorisierungs- und Transaktionsbindung bleiben unangetastet.

Ein materiell anderer Kandidat braucht einen isolierten Adapter-/Wire-Vertrag mit unveränderten nicht betroffenen Feldern, vollständigem Schema und Observationen; separat sind idempotentes Anhängen, Escaping und Scope-Grenzen zu prüfen. Gepaarte, möglichst reihenfolgekontrollierte synthetische Fälle müssen fehlende Eingaben, echten Kontextabruf, unbestätigte und bestätigte Zusammenfassungen, Fehler, Korrekturen und lange Observationen umfassen. Annahme erfordert exakte Action-, Input-, Observation- und `last_objective`-Parität, gültiges vollständiges JSON ohne Längenabbruch, Einhaltung der Schutzregeln und einen wiederholbaren gemessenen Zeitgewinn unter vergleichbaren Cachebedingungen. Andere Schema- oder Completion-Budget-Grenzen wären eigenständige Änderungen und brauchen ihre eigenen Messungen.

Erst danach kämen begrenzte autorisierte Live-Scope-Prüfung und ein physischer Turn mit aggregierten Zeiten in Betracht. Synthetische Tests ersetzen weder einen Nachweis der effektiven Live-Scope-Bindung noch echte Transaktions- oder Audiobelege. Es gibt aus den vorliegenden Messungen keinen Anlass zu einem Produktpatch.

## Belege

Die Entscheidung ist gegen die redigierten Taskworkspace-Belege `duplex-implementation-20261023/react-latency-plan.md`, `live-authority-preflight.md`, `gemma-checkpoint-ab-result.md`/`.json`, `react-compact-spike-preflight.md` und `react-compact-spike-result.md`/`.json` geprüft (Taskworkspace: `C:/Users/Marcel/Documents/Codex/2026-10-19/fahre-den-chat-servicenow-bergabe-bzw`). Dieses Dokument übernimmt weder Roh-`Thought`-Texte noch Transkripte, Zugangsdaten oder Kundendaten.
