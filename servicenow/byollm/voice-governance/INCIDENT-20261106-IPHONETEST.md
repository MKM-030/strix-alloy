# iPhone-Versuch vom 6. November 2026: Verbindung ohne Fortsetzung

Instanz: `soprasteriaassvsdemo14`. Lokaler Anruf `8e53c5c6e65b`, [ServiceNow-Gespräch `36ab3e479394db585c8132d47aba1083`](https://soprasteriaassvsdemo14.service-now.com/sys_cs_conversation.do?sys_id=36ab3e479394db585c8132d47aba1083).

**Aktualisierung 19:05 UTC:** Nach neuer ausdrücklicher Freigabe und frei gewordener Speicherreserve wurde Halogen einmal über den normalen zentralen Controller gestartet. Modell, Gateway, Native-Bridge, ASR und TTS sind tatsächlich bereit. Dieser Wiederanlauf ändert keine ServiceNow-Konfiguration. Die anschließende reale Geräteabnahme bleibt offen.

**Separater Startfehler am späten Abend:** Marcels anschließender Start erreichte wegen fehlender öffentlicher TLS-Erreichbarkeit keine Native-Sitzung. Der Zugang ist nach einer regulären Tailscale-Wiederverbindung wieder extern nachgewiesen; ServiceNow erhielt HTTP200 in 684 ms. Modell, eigene Stimme und alle Voice-Einstellungen blieben erhalten. [Befund, Aktionen und Grenzen](INCIDENT-20261106-VOICE-ENTRY.md).

## Tatsächlicher Ablauf

Der lokale Anruf lief von 18:02:29 bis 18:03:41 Uhr MEZ. Die Verbindung blieb bis zum Auflegen bestehen. Die Begrüßung erzeugte 380.160 angenommene PCM-Bytes in 7,187 Sekunden; der erste Chunk lag nach 297 Millisekunden vor. Das belegt die Ausgabe des Servers, nicht die hörbare Wiedergabe auf dem iPhone.

Drei nichtleere Spracheingaben wurden erkannt. Die erste lokale Antwort wurde bei Satzfreigabe und Abschluss wegen `context_changed` verworfen. ServiceNow erhielt in diesem Versuch nur den Startauftrag, keine fachlichen Nutzereingaben und keinen Werkzeug- oder Bestellauftrag.

| ServiceNow-Vorgang | Gemessene Dauer / Ergebnis |
|---|---|
| Orchestrator-Planung | 23,354 Sekunden |
| Weitere Planungsaufrufe | 11,911 / 10,400 / 11,480 Sekunden |
| Gesamter Ausführungsplan | 64,391 Sekunden, `execution_failed` |
| Erste zwei Rückfrage-Aktionen | `FALLBACK` ohne erforderliche `Action Inputs.mode` und `.prompt` |
| Letzte Rückfrage-Aktion | Enthielt `mode` und `prompt`; kurz darauf wurde aufgelegt. Leere `Datatypes` sind für native Texteingaben nicht automatisch falsch. |
| Episodic-Auswertung | Zwei Fehler `200000`; deren aktive Promptbindung verweist noch auf Gemma. |

Die ServiceNow-Zeitstempel und die lokalen Zeitstempel sind versetzt. Reihenfolge und jeweils lokal gemessene Dauern wurden getrennt bewertet; aus verschiedenen Uhren wird keine millisekundengenaue gemeinsame Laufzeit abgeleitet.

## Installierte Korrekturen

1. **Lokale Antwortfreigabe:** Passive Signale wie „Hallo“ und „Ähm“ bleiben im Rohverlauf, machen eine ausstehende Antwort aber nicht mehr allein ungültig. Inhaltliche Korrekturen erhöhen weiterhin die Kontextrevision. Native Kontrollfragen, Bestellfreigaben, Quellenbindung und laufende Audio-Abbruchregeln bleiben wirksam. Die konkrete Zuordnung der zweiten/dritten Erkennung zu diesem Zweig ist mangels geloggter Rohtexte nicht bewiesen; der Fehler wurde unabhängig davon über den echten Eingabepfad reproduziert.
2. **ServiceNow-Rückfragevertrag:** Der bereits ausgewählte SCC-/Halogen-Transformer verlangt im kompakten Produzenten-Schema `Action Inputs` und beschreibt die nativen Felder `mode` und `prompt`. Es werden keine Modellausgaben nachträglich repariert und keine nativen Validatoren ersetzt.
3. **Natürliches Gespräch:** Die alte, vom Transport eingefügte pauschale Namensbestätigung wurde entfernt. Der aktuelle Anwendungs-Prompt behält seine Regeln zur gezielten Klärung unklarer Namen und zur gesonderten ausdrücklichen Bestellfreigabe. Der vollständige aktuelle Eingabe-/Werkzeug-/Anweisungsteil bleibt erhalten.
4. **Gezielte Fehlerdiagnose:** Der bestehende sichere Prompt-Konfigurationsschutz unterscheidet jetzt feste Fehlerkategorien. Er protokolliert nur Argumenttyp und gegebenenfalls eine kanonische Konfigurations-ID. Keine Prompts, Spracheingaben, Audiodaten oder Zugangsdaten. Diese Änderung diagnostiziert den noch nicht eindeutig zugeordneten Lookup-Fehler; sie umgeht ihn nicht.

| ServiceNow-Artefakt | Update Set und Customer Update |
|---|---|
| [Halogen Request Transformer `bc126377936f8750e7f2b9fa6aba1012`](https://soprasteriaassvsdemo14.service-now.com/sys_generative_ai_custom_llm_transformer.do?sys_id=bc126377936f8750e7f2b9fa6aba1012), Feld `request_transformer` | [Global-Set `5782030b9318db585c8132d47aba1059`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=5782030b9318db585c8132d47aba1059), [CU `9b82030b9318db585c8132d47aba1069`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=9b82030b9318db585c8132d47aba1069). Installierter SHA-256: `485a3411edb624e43ff888834837fc4740f3b7d36dfb66fb8d567e8363a09965`. |
| [Custom LLM Provider Mapping `07ca9d94c3550210b0939bc8a840ddeb`](https://soprasteriaassvsdemo14.service-now.com/sys_generative_ai_provider_mapping.do?sys_id=07ca9d94c3550210b0939bc8a840ddeb), Feld `prompt_transformation_script` | [GenAI-Set `76a34f0b93dc9394e7f2b9fa6aba103b`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=76a34f0b93dc9394e7f2b9fa6aba103b), [CU `47a38f0b93dc9394e7f2b9fa6aba1028`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=47a38f0b93dc9394e7f2b9fa6aba1028). Installierter SHA-256: `dd5b33476b8dbfafa37f4c89648f335eee6d401ce0f6e31b3a8ffb4dad736f03`. |
| [Neue Episodic-Promptrevision `40c43848746f4e5e944660784f9846f2`](https://soprasteriaassvsdemo14.service-now.com/sys_generative_ai_config.do?sys_id=40c43848746f4e5e944660784f9846f2) | Version 2, Modell `halogen-v2`, ursprünglicher Custom-Prompt `0f80c7e193f747d0e7f2b9fa6aba10c0` als unveränderter Eltern-Datensatz. Eigenes Documentation-Feld befüllt. [Global-Set `7c04cb8f9318db585c8132d47aba1013`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=7c04cb8f9318db585c8132d47aba1013), [CU `51b943479350d394e7f2b9fa6aba10b1`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=51b943479350d394e7f2b9fa6aba10b1). |
| [Neue Standard-Promptbindung `95b943479350d394e7f2b9fa6aba10a2`](https://soprasteriaassvsdemo14.service-now.com/sys_generative_ai_prompt_config.do?sys_id=95b943479350d394e7f2b9fa6aba10a2) | Nativ erzeugte und als einziger Standard ausgewählte Halogen-Bindung derselben Definition. [CU `99b943479350d394e7f2b9fa6aba10ab`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=99b943479350d394e7f2b9fa6aba10ab) im selben Global-Set. |
| [Bisherige Standardbindung `4780c7e193f747d0e7f2b9fa6aba10c2`](https://soprasteriaassvsdemo14.service-now.com/sys_generative_ai_prompt_config.do?sys_id=4780c7e193f747d0e7f2b9fa6aba10c2) | Nur `is_default=false`; zwei weitere historische Bindungen und der veröffentlichte Gemma-Quellprompt bleiben erhalten. [AIA-Set `c084470f93dc9394e7f2b9fa6aba1066`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=c084470f93dc9394e7f2b9fa6aba1066), [CU `a5b983479350d394e7f2b9fa6aba101b`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=a5b983479350d394e7f2b9fa6aba101b). |
| [Natives Metadatensignal `Is Metadata Updated`](https://soprasteriaassvsdemo14.service-now.com/sys_gen_ai_control_setting_data.do?sys_id=32ee2ed0fff53210c3fcffffffffff09) | Automatisch von der Plattform erfasst, keine zusätzliche fachliche Änderung. Gegenüber dem Vormittags-Capture nur `sys_mod_count` 325→329 und Zeitstempel geändert; `value=true` und alle semantischen Felder erhalten. [CU `89b9438b9398db585c8132d47aba1034`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=89b9438b9398db585c8132d47aba1034) im Episodic-Global-Set; ausschließlich der Zweckkommentar wurde ergänzt. |

Die beiden Skriptartefakte besitzen kein beschreibbares natives Description-Feld. Ihre tatsächlichen Customer Updates wurden deshalb einzeln in **Comments** beschrieben; auch die neuen Set-Köpfe enthalten ihren Zweck. Quellen und Captures wurden nachgelesen. Native XML-Erfassung entfernt CR-Zeichen; eine nicht sichtbare Unicode-Stelle wurde im JavaScript quellgleich als Escape geschrieben, damit der native Capture denselben Laufzeitinhalt transportiert. Der XML-Payload wurde nicht manuell bearbeitet.

Der Abschlussaudit bestätigt **sechs einzeln dokumentierte neue Customer Updates in vier neuen Update Sets**, zusätzlich zum Vormittagskatalog. [Delta-Katalog](customer-update-delta-20261106-evening.csv). Alle vier Set-Beschreibungen sind befüllt; keine der sechs CU-Kommentarspalten ist leer.

Die Episodic-Capability `920e9ca9ffb92210f465ffffffffff68` verwendet nun die neue Halogen-Revision als einzigen Standard. Der Roh-Prompt blieb identisch; die ursprünglichen 37 Quellfelder, die zwei anderen Bindungen, die Definition-Auswahl und die vorhandene Halogen-Registrierung wurden auf Erhaltung geprüft. Es wurde keine Modellregistrierung angelegt und keine Now-LLM-Modellhistorie kopiert; die betreffenden Modellhistorien-Zeilen bleiben bei null.

Bei der Neuanlage prüft das Änderungsskript Datensatz- und Feld-**Anlagerechte**; vorhandene Datensätze behalten ihre Schreibprüfungen. Alle Kontextwechsel und Fremdlesevorgänge liegen vor dem frischen Neuanlage-Datensatz, danach erfolgt unmittelbar das Einfügen. Dies entspricht der Unterscheidung von `canCreate()` und `canWrite()` in der [ServiceNow-API-Dokumentation](https://www.servicenow.com/docs/r/api-reference/server-api-reference/c_GlideElementAPI.html). Frühere sicher abgebrochene Versuche erzeugten keinen Prompt und änderten keine Bindung; der erfolgreiche neue Lauf wurde gesondert geprüft und nicht wiederholt.

Die lokale Korrektur ist seit 17:20 UTC in Native-Prozess **23008**, Launcher **26724**, geladen. TTS **5644**, ASR **16592**, Bot **20180** und Gateway **21028** wurden mit ihren Prozessidentitäten erhalten. Konfigurierte Sprache, Begrüßung und eigene Stimme wurden nicht umgestellt.

Das unabhängige Gesprächsmodell bleibt über die Capability **VA Input Response Generation** (`aca5634f4312121038520464dbb8f236`) im AI Control Tower / Skill Kit zugeordnet. Die hier gesondert behandelte Episodic-Auswertung ist eine interne Agentenauswertung und ersetzt diese Gesprächs-Capability nicht.

## Separater Speicherstopp nach dem Versuch

Erst nach dem Anruf, um 17:13:18 UTC, startete `Grounded2Steam-Win64-Shipping`. Die freie Reserve fiel von 23,543 GiB auf 17,679 GiB. Die bestehende 18-GiB-Überwachung stoppte deshalb Halogen; zu diesem Zeitpunkt lief kein weiterer Voice-Inferenzauftrag. Diese zeitliche und gemessene Übereinstimmung belegt Speicherkonkurrenz, nicht die Herkunft jedes belegten Bytes. Sie erklärt nicht rückwirkend den früheren Gesprächsfehler.

Ein frisch gebundener Wiederherstellungsversuch wurde **vor** Sperrdatei-Archivierung und Modellstart mit `memory_admission_not_met` angehalten: `launch_attempts=0`, `archive=false`. Profil, Modellwahl und Reserve bleiben unverändert. Das Spiel wurde nicht beendet. Der Versuch ist verbraucht und darf nicht wiederholt werden.

Nach Marcels neuer Freigabe war das Spiel nicht mehr aktiv. Eine neue, gesondert gebundene Prüfung bestätigte die beendete alte Laufzeit, ausreichend stabilen Speicher und die unveränderten Sprachdienste. Nur die exakt zugehörige alte Sperrdatei wurde archiviert; der ursprüngliche Speicherfehler samt Belegen blieb erhalten. Der anschließende **einmalige** normale Modellstart war erfolgreich: Controller **20840**, Backend-Steuerung **21368**, Launcher **6572**; neue Läufe `e7ca3a97d1964de780dba4e4c69b4274` und `21c02a5cf0884efd9d1f6879dce85b2f`.

Die unveränderte Auswahl nutzt v2, 32K Kontext, zwei Slots, KV65536 und Prefill2048; die 18-GiB-Reserve bleibt aktiv. Der Start verwendet die regulären Argumente einschließlich `-u -B`, damit auch der bestehende Voice-Starter denselben laufenden Controller erkennt und wiederverwendet. Die authentifizierten Statusprüfungen sowie der tatsächliche reguläre Controller-Verbraucher bestätigen Betriebsbereitschaft und Anfragenzulassung. Um **19:05:43 UTC** waren rund **26,1 GiB** physischer Speicher frei; Native hatte null Sitzungen. Die neun erhaltenen Sprach-/Gateway-Prozessidentitäten blieben unverändert.

## Prüfung und offene Abnahme

Die lokalen Änderungen erhielten gezielte Offline-Regressionen mit reproduziertem Vorher-Fehler und unabhängiger Quellenprüfung. Es wurden keine zusätzlichen geskripteten Sprachgespräche, Mikrofonaufnahmen, Modell-Downloads oder Testbestellungen ausgeführt. Der erste gesonderte Startversuch erreichte keinen Modellstart. Der spätere erfolgreiche normale Start behielt seine eingebauten Prüfungen bei; zusätzliche Inferenzprüfungen wurden nicht hinzugefügt.

Offen bleiben die genaue Ursache des sicher abgebrochenen Konfigurations-Lookups und ein neues tatsächliches Gerätegespräch. Zwei begrenzte ServiceNow-Nachlesungen fanden zwischen 18:05 und 18:57:57 UTC weder ein neues Gespräch noch einen neuen Guard-Diagnoseeintrag. Die vollständigen ursprünglichen Transformationsparameter sind nicht gespeichert; deshalb wurde kein künstlicher Ersatzaufruf erzeugt. Die installierte Diagnose erfasst den tatsächlichen Fehlerkontext beim nächsten realen Aufruf. Weder hörbare Wiedergabe noch vollständiger Geschäftsablauf oder Gleichheit auf iPhone/Android/Desktop werden aus Offline- und Metadatenprüfungen abgeleitet.

Die Episodic-Zuordnung ist installiert. Ein tatsächlich erfolgreicher Auswertungsaufruf mit dem neuen Modell bleibt zusammen mit dem nächsten echten Dialog zu prüfen, sobald das Modell wieder bereit ist. Veröffentlichte Quellen, fremde Modellhistorie und Berechtigungen wurden nicht überschrieben.

Evidenz: `server/.local/voice-repair-20261102/fresh-call-servicenow-observation-20261106-v1`. Die umfassende Dokumentation und der bestehende Katalog vom Vormittag bleiben unter [CHANGELOG-20261106.md](CHANGELOG-20261106.md) erhalten.

Evidenz des tatsächlichen Wiederanlaufs: `server/.local/voice-repair-20261102/task95-voice-resume-20261106-v1/result.json` und `FINAL-READINESS-AND-CONSUMER.json`. Alte und neue Ausführungshelfer sind verbraucht und dürfen nicht wiederholt werden; weitere Modellwechsel oder automatische Wiederanläufe wurden nicht eingerichtet.
