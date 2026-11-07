# Transkriptfehler und Gesprächskontext vom 7. November 2026

Marcel bestätigte für den betroffenen Laptopdialog den Namen Lea Oltmer. Das nachgereichte Transkript zeigt eine fehlerhafte Erkennung des Nachnamens und eine spätere Fehlinterpretation einer verärgerten Äußerung als technisches Verbindungsziel. Die Verbindung scheiterte im historischen Anruf an konkurrierenden Modellaufrufen. Zusätzlich ließ die lokale Gesprächsschicht unbelegte Aussagen zum vermeintlich ungültigen Ziel zu.

Der Anruf `1f89384417af` wurde am 7. November gegen 19.02 Uhr Ortszeit geschlossen. Er gehört zur ServiceNow-Conversation `65d2d46393505b94e7f2b9fa6aba1058`, zur Interaction `61d2d46393505b94e7f2b9fa6aba10b7` / IMS0001105 und zum Plan `a6d21c6393505b94e7f2b9fa6aba1003`. Der Anruf lag vor der bereits dokumentierten Umstellung auf die gemeinsame Modellwarteschlange. Das gelieferte Transkript enthält die konfigurierte Begrüßung zur Laptopbestellung. [Conversation](https://soprasteriaassvsdemo14.service-now.com/sys_cs_conversation.do?sys_id=65d2d46393505b94e7f2b9fa6aba1058) · [Warteschlangenkorrektur aus Task97](INCIDENT-20261107-MODEL-CAPACITY.md).

## Befund

| Beobachtung | Belegte Einordnung |
|---|---|
| Erkannt wurde `Für Lea Odlmäde bitte die Nachbene`. | Marcel bestätigte Lea Oltmer als beabsichtigten Namen. Für die übrigen Wortfehler fehlen Originalaudio und ein vollständiger beabsichtigter Wortlaut. |
| Nach der ersten Eingabe kam eine allgemeine Antwort zur unzuverlässigen Beantwortung einer Frage. | Der lokale Fehlerzweig wurde nach HTTP429 erreicht. Er setzt eine angenommene Spracheingabe voraus, prüfte deren Frageform aber nicht. |
| Anschließend meldete der Assistent einen fehlgeschlagenen ServiceNow-Start. | Ein ServiceNow-Modellaufruf war erfolgreich, drei weitere endeten mit HTTP429 und GenAI200000. Der Plan endete mit `execution_failed`. |
| Die spätere verärgerte Äußerung wurde als neue Gegenstelle ausgelegt. | Die lokale Antwort behauptete eine technische Zielprüfung und verlangte weitere Mitarbeiterdaten ohne passende ServiceNow-Rückmeldung. |

Die lokalen Rohwörter und das Originalaudio dieses beendeten Anrufs wurden nicht gespeichert. Die begrenzte Anhangsabfrage für genau Conversation und Interaction lieferte null Datensätze. Andere mögliche Speicherorte wurden damit nicht geprüft. Die Diagnose stützt sich beim Wortlaut auf Marcels Transkript.

## Lokale Änderungen

Die bereits in Task97 aktivierte Verbindung über Port8841 ordnet lokale Gesprächsantworten und ServiceNow-Modellaufrufe in derselben vorhandenen Warteschlange ein. Der ergänzte Startschutz prüft die Kapazität eines ausdrücklich eingerichteten Direktzugangs. Zwei damals gleichzeitig gesendete kurze Textanfragen erhielten über die Warteschlange HTTP200.

| Quellstand | Änderung |
|---|---|
| `a58c906` | Übergibt den fehlgeschlagenen Dialogstart ausdrücklich an den Modellkontext. Bereits genannte Angaben und spätere Korrekturen bleiben im Gesprächsinhalt. Die vorhandene Prüfung unbelegter fachlicher Rückfragen gilt auch nach einem fehlgeschlagenen Start. |
| `c9eb092` | Behandelt erkannte ASR-Wörter als möglicherweise fehlerhafte Gesprächsevidenz. Verbindungsfähigkeiten folgen aus der konfigurierten ServiceNow-Anbindung und dem beobachteten Zustand. Der allgemeine lokale Fehlertext setzt keine gestellte Frage mehr voraus. |
| `29f7760` | Verwirft eine optionale Antwort vollständig, wenn sie unbelegt die Gültigkeit einer technischen Gegenstelle behauptet. Eine exakt passende aktuelle ServiceNow-`OutputText`-Rückmeldung bleibt über den vorhandenen fachlichen Eigentumsnachweis zulässig. Bei einem fehlgeschlagenen Start nutzt der Rückfallzweig den vorhandenen belegten Startstatus. |
| `56801b6` | Ergänzt eine gezielte Regression für die vorhandene Pipecat-Sperre nach dem ersten abgelehnten Antwortkandidaten. Der bestehende Produktionspfad berücksichtigt `callback_failed` bereits. |
| `fd06be1` | Prüft relative Controller- und Profilpfade anhand des tatsächlichen Prozessarbeitsverzeichnisses. Kanonischer Quellpfad, erlaubtes Python, Loopback-Eigentümer, Prozessidentität und Profilprüfsumme bleiben bindend. Der Verbraucher unterscheidet geprüfte laufende Argumente von kanonischen Argumenten für einen späteren Kaltstart. |
| `9dfb3d0` | Erlaubt die nachgewiesene bestehende Gateway-Aufrufweise beim regulären Wiederanlauf. Der begrenzte Eigentumsabgleich erhält das laufende Gateway; drei gezielte Offline-Prüfungen bestanden in 0,015 Sekunden. |
| `9a689e3` | Aktualisiert die bestehende ASR-Manifestkette für den geprüften Starter. Nur dessen private Prüfsummenbindung wurde angepasst; die übrigen Bindungen blieben erhalten. Die direkte Dateiverifikation bestand ohne Dienststart. |

Die frühere Native-Aktivierung lud `a58c906` am 7. November um 19.21.54 UTC als PID14940. Dieser Prozess endete bei der späteren Laufzeitunterbrechung. Die anschließenden Quellkorrekturen wurden mit der unten belegten regulären Wiederherstellung um21.44UTC in die neue Native-Generation23256 übernommen.

## ServiceNow-Änderung und Update Set

Am aktiven deutschen Sprachdatensatz wurden acht allgemeine Kontextbegriffe eingetragen. Die vorhandene Projektion überträgt die Einstellung an den lokalen ASR-Dienst. CrispASR erhält sie als Kontexttext und setzt beziehungsweise entfernt sie innerhalb der bestehenden Sitzungssperre. Daraus folgt keine gemessene numerische Tokengewichtung.

| ServiceNow-Artefakt | Tatsächliche Änderung |
|---|---|
| [Sprachkonfiguration `d2a175d793f787105c8132d47aba1078`](https://soprasteriaassvsdemo14.service-now.com/sn_voice_language_config.do?sys_id=d2a175d793f787105c8132d47aba1078) | `key_terms` enthält jetzt ServiceNow, Laptop, Laptopbestellung, Mitarbeiter, Eintrittsdatum, Führungskraft, Lieferort und Nachname. Nachlesestand Revision5. |
| [Update Set `SCC Voice Task98 - German ASR Vocabulary`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=de1628a3931493985c8132d47aba10bc) | Neues Global-Set mit ausgefüllter Description zum konkreten Wortschatz und dessen vorhandener Projektion. |
| [Customer Update `2a1628a3931493985c8132d47aba10ef`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=2a1628a3931493985c8132d47aba10ef) | Einziger Capture im neuen Set. Der individuelle Kommentar benennt Datensatz, Zweck, acht Begriffe, Projektion und Abnahmegrenze. Aktion `INSERT_OR_UPDATE`, Typ `Voice Language Configuration`. |
| [Ausführungshistorie `921628a3931493985c8132d47aba10ba`](https://soprasteriaassvsdemo14.service-now.com/sys_script_execution_history.do?sys_id=921628a3931493985c8132d47aba10ba) | Einmalige Installation mit Rücksetzkontext `161628a3931493985c8132d47aba10b8`. |

Die komplette Set-Nachlesung bestätigte genau einen Customer Update und dessen native Payload. Das bestehende globale Customer Update `5358be5a93581f185c8132d47aba10cf` und das vorhandene Voice-Set `e967c98f93541394e7f2b9fa6aba1091` wurden erhalten. Die vorherige Global-Set-Auswahl wurde wiederhergestellt.

Ein erster Ausführungsversuch im geschützten Voice-Scope wurde von der Instanz abgewiesen. Eine anschließende lesende Prüfung bestätigte reguläre Admin-Schreibrechte auf Datensatz und Feld mit `GlideRecordSecure`. Die tatsächliche Installation verwendete diesen erlaubten Global-Zugriff. Der Ausführungsbeleg weist null Scope- oder Berechtigungsänderungen aus. Sämtliche Ausführungshelfer sind verbraucht.

Die Prüfsumme des eingetragenen Wortschatzes lautet `518d7d5e299ece7b5d5fa917d3aa0698c3fc4e74f4258d4bad8a1fb8c04f92e8`, die native Customer-Update-Payload hat SHA-256 `dafd49e81e77379aa6f58eb1b629aec6b2e0c594b786b54e518b90dbb9377410`. Personennamen wurden nicht als globale Begriffe eingetragen. Weitere ServiceNow-Schreibvorgänge gehören nicht zu diesem Arbeitsschritt.

## Gezielte Prüfung und Grenzen

Drei einmalige lokale Textprüfungen lieferten HTTP/SSE-Antworten nach rund 2,95, 2,73 und 2,94 Sekunden. Alle drei Antworten deuteten die missverstandene Äußerung weiter als ungültiges Verbindungsziel. Die erste Prüfung ließ Assistentenhistorie aus. Die beiden folgenden verwendeten die tatsächlichen drei vorherigen Assistentenaussagen über die produktiven Ausgabebeobachter. Die dritte prüfte den zusätzlich vorbereiteten ASR-/Verbindungsvertrag. Root lehnte sämtliche semantischen Ergebnisse ab und zog den daran gebundenen Aktivierungshelfer ohne Ausführung zurück.

Historienhaltung, Halogen-Normalisierung und das aktive Jinja-Template erhalten die geprüften Modellnachrichten vollständig. Ein Verwerfen der System- oder Gesprächsnachrichten erklärt diesen Fehler im untersuchten Pfad nicht. Die alte unabhängige Freigabeprüfung ließ dagegen alle sechs Sätze der drei fehlerhaften Antworten passieren. Der neue enge Guard verwirft beim Offline-Wiedergeben jede dieser drei Antworten vollständig.

Root bestätigte 32 gezielte Offline-Tests in 0,716 Sekunden, die einzelne Prüfung der vorhandenen Rückruf-Sperre in 0,272 Sekunden und vier Controller-Verbrauchertests in 0,088 Sekunden. Diese Ergebnisse belegen die geprüften Freigabe- und Eigentumsregeln. Die tatsächlich erzeugten Modellantworten bleiben semantisch fehlerhaft. Der neue enge Guard deckt die ursprüngliche pauschale Behauptung fehlender technischer Fähigkeiten nicht vollständig ab.

Die Textprüfungen enthielten keine tatsächliche anrufbezogene ServiceNow-Präsentation, weil `call_settings=None` gesetzt war. Sie verwendeten höchstens 128 Ausgabetokens gegenüber 192 im Produktionspfad und erzeugten kein Geräteaudio. Der bestätigte richtige Name wurde dem Modell dabei nicht als zusätzliche Kenntnis übergeben. Ein natürliches vollständiges Gespräch ist damit weiter abzunehmen.

Die allgemeinen ASR-Begriffe liefern zusätzlichen Kontext. Eine Verbesserung der Namens- oder Worterkennung wurde noch nicht gemessen. Die vorhandene F16-Datei für Qwen3-ASR0.6B wurde vollständig gehasht. Ihre Integrität ist belegt, Spitzenbelegung, Latenz und Qualitätsgewinn im Laufzeitbetrieb fehlen. Sie wurde nicht geladen oder ausgewählt.

## Laufzeitunterbrechung und Wiederherstellung

Bei der späteren lesenden Prüfung waren sämtliche zwölf zuvor beobachteten Modell- und Sprachprozessgenerationen beendet. Windows meldete weiterhin den Systemstart vom 4. November um 21.14.26 UTC.

Der vorherige Backend-Lauf `70499da200b84b3f9a5483fd247af4cb` speicherte in `guard-failure.json` einen physischen Reserveverstoß bei 17,970 GiB gegen die vorhandene 18-GiB-Grenze. Commit-Spielraum war 108,299 GiB. Der letzte Sample stammt vom 7. November um 20.00.01,969 UTC. Der spätere Abschluss bestätigt `cleanup=true` und `recovery=true`, protokolliert aber auch eine abweichende Guard-Beendigung. Welcher Prozess den Speicher verbrauchte und weshalb alle Sprachdienste endeten, ist weiterhin ungeklärt.

Ein externer normaler Wiederanlauf stellte zwischenzeitlich dasselbe Einplatzprofil bereit. Controller9020 mit Lauf `6f9b6080e1224c68ab51101ecd01eee2` und Backend18980 mit Lauf `7641d38d806f4771b6db40f3ec3de9a7` meldeten am 7. November um 21.28.01 UTC Bereitschaft. Diese Beobachtung ist historisch: Der normale Controller ging gegen 21.34 UTC für einen externen Engineering-Vergleich offline. Daraus wird keine aktuelle Voice-Bereitschaft abgeleitet.

Zum historischen Vorprüfstand um21.37UTC lief der externe Vergleich unter Controller27724 auf Port18840. Der Prozess wurde um 21.34.25,832406 UTC mit dem temporären Profil `mtp_gate_cost-raw-comparison/before.profile.json` und dessen Prüfsumme `2dc701…` erstellt. Der äußere Lauf beginnt mit `017694e…`, der Backend-Lauf mit `6fa7…`; Backend21040 war zu diesem Zeitpunkt im Start. Gateway17680 blieb erhalten. Der reguläre Voice-Starter verweigerte seine Vorprüfung mit „central selection changed“, bevor er einen Dienst startete.

Die normalen Aufrufdarstellungen von Controller und Gateway sind durch `fd06be1` und `9dfb3d0` im Quellstand berücksichtigt. `9a689e3` ergänzt die passende ASR-Starterbindung. Insgesamt bestanden 32 gezielte Offline-Prüfungen, eine Rückrufprüfung, vier Controller-Prüfungen und drei Gateway-Prüfungen; die direkte Dateiverifikation bestand ebenfalls. Zum Stand dieser Vorprüfung waren die Gesprächskorrekturen vorbereitet und die Sprachdienste beendet. Die spätere tatsächliche Aktivierung ist unten getrennt belegt.

Die Wiederherstellung wartete um21.37UTC auf die Rückgabe des normalen Controllers an Port8840 mit dem gespeicherten Profil `serving0191-text32k-one-slot-2048.json`, Prüfsumme `69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84`. Der private Beleg `task98-normal-start-restoration-20261107-v1/RESTORATION-NOT-EXECUTED.json` hält den Stand von 21.37.25 UTC, sieben Quellbindungen und null Lebenszyklusaktionen aus diesem Reparaturablauf fest. Locks wurden nicht verändert. Diese damalige Wartebedingung wurde durch die Rückgabe und die tatsächliche Aktivierung um21.44UTC aufgehoben. Der historische Nichtausführungsbeleg wird dadurch nicht zum Aktivierungsbeleg; maßgeblich für die Wiederherstellung ist `task98-normal-start-restoration-20261107-v1/activation.SPENT.json`.
## Ausstehende Abnahme

Offen bleiben eine angemessene natürliche Reaktion auf unklare Namen und Verbindungswünsche, ein neuer vollständiger ServiceNow-Dialog und die hörbare Ausgabe auf dem Gerät. Gleiches Verhalten auf iPhone, Android und Computer sowie der vollständige Bestellabschluss sind durch diese begrenzten Text- und Metadatenprüfungen nicht abgenommen. Agententests stoppen an jeder Bestellfreigabe.

Die privaten Nachweise liegen unter `C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102` in den Task98-Transkript-, Vokabular- und drei Textprüfungsordnern. Maßgeblich sind `grounding-activation.SPENT.json`, `GENERIC-KEY-TERMS.FINAL-STATE.private.json`, die drei tatsächlich ausgegebenen `response.txt`, die Ablehnung in `semantic-review.json` und der zurückgezogene Aktivierungsbeleg. Der frühere Reservefehler liegt im Backend-Lauf `70499da200b84b3f9a5483fd247af4cb`, der historische Bereitschaftsbeleg im Lauf `7641d38d806f4771b6db40f3ec3de9a7` und der historische Nichtausführungsbeleg von21.37UTC in `RESTORATION-NOT-EXECUTED.json`. Die spätere tatsächliche Wiederherstellung ist in `task98-normal-start-restoration-20261107-v1/activation.SPENT.json` belegt.
## Ergänzung zur Rückgabe um 21.40 UTC

Der externe Vergleich war um21.40UTC beendet. Der reguläre Controller19368 mit Lauf `654d152776da452782f388a2aed8805d` startete wieder auf8840 mit exakt gespeichertem ProfilSHA69b91…. Um21.40.16UTC war dieser Start noch nicht bereit; Gateway17680 blieb aktiv. Die Voice-Dienste und Aktivierung wurden anschließend nach bestätigter regulärer Bereitschaft geprüft und um21.44UTC wiederhergestellt.

## Tatsächliche Aktivierung um21.44UTC

Nach bestätigter normaler Bereitschaft bestand die vollständige lesende Startvorprüfung. Der reguläre Starter stellte die Voice-Dienste einmal zwischen21.44.36 und21.44.49UTC wieder her. Native23256/Launcher4088 und Bot8052/Launcher5852 wurden gestartet; TTS25816 registrierte die ausgewählte deutsche eigene Stimme, CrispASR meldete bereit. Controller19368, Backend24360 und Gateway17680 behielten exakt ihre vor dem Voice-Start geprüften Prozessgenerationen. Native-Konfiguration und gespeicherte Modellauswahl blieben bytegleich; alle sieben festgehaltenen Quellprüfsummen blieben erhalten. Freier Speicher danach20,743GiB, vorhandene18GiB-Reserve unverändert.

Die neue Bridge meldete `status=ok`, `asrReady=true`, `nativeSdkEnabled=true` und null Sitzungen. Der öffentliche HTTPS-Zugang lieferte um21.45.38UTC HTTP200 in2,672s mit demselben Status. Dies ist eine reine lesende Erreichbarkeitsprüfung. Es gab bei dieser Wiederherstellung keine Modell-Inferenzanfrage, keine Audioaufnahme/-probe und keine fachliche ServiceNow-Anfrage. Ein tatsächlicher neuer iPhone-Dialog bleibt offen.

Nachweise: `task98-normal-start-restoration-20261107-v1/activation.SPENT.json`, `ordinary-start.log`, `public-health.json` und `pin-refresh.json`. Die vorangegangene Datei `RESTORATION-NOT-EXECUTED.json` beschreibt ausschließlich die frühere Vorprüfung um21.37UTC. Der Aktivierungsvorgang ist verbraucht und darf nicht wiederholt werden.

## Eingrenzung des eigenständigen Testzugangs um21.57UTC

Eine einzelne neue Zugangsprüfung hat keinen Dialog gestartet, keine Modellanfrage gestellt und keine Nutzerangaben übermittelt. Die offizielle SDK-Anmeldung konnte die Assistentenkonfiguration lesen; erst die vorhandene Vorprüfung des separaten Gesprächserstellungs-Endpunkts wurde mit HTTP401 abgelehnt. Der frühere SDK-Testfehler lag damit aktuell am Zugriff auf diesen Endpunkt. Eine abgelaufene Anmeldung oder ein Fehler des tatsächlichen iPhone-Zugangs ist daraus nicht bewiesen.

Die lesend geprüfte Konfiguration ordnet dem Endpunkt weiterhin genau drei Anmeldeprofile zu, darunter das aktive eigene Browser-Voice-Profil. Für einen aussagekräftigen Dialogtest ist der vorgesehene native Test-Assistant mit seiner eigenen Anmeldung zu verwenden. Dessen Chat-Eingabe braucht zuerst eine erzeugte Chat-Sitzung. Der aktuelle Browserzugriff ist in Work deaktiviert; deshalb konnte diese Sitzung nicht eigenständig untersucht werden. Zugriffsregeln und Anmeldeberechtigungen wurden nicht erweitert. Der sichere Diagnosebeleg liegt in `task98-admission-diagnostic-20261107-v1/result.json`.


## Native Test Assistant Chat compatibility — 2026-11-07, activated

Fresh ServiceNow client-source evidence establishes that native Test Assistant Chat opens `/text/chat/agent_operator`; the local router previously returned404 for that route. This is a distinct test-path compatibility defect, not proof that the historical iPhone failure used that route. The adapter now uses the existing `authorize(..., with_settings=True)`, original caller binding and caller-owned Dialog, model readiness and shared capacity. It emits native connected/static/actual metadata/end_call packets, passes exact raw text once and delivers turn replies only through the existing callback to avoid duplicate output. It allocates no Speech, ASR, TTS, TURN or voice-reference preparation. Unacknowledged owned END retains capacity until cleanup succeeds.

Source commits:8bb41c0 (adapter),61c33a3 (real router integration/plan),a4352ba (failed-upgrade cleanup),8f57f26 (reviewed source manifest chain). Independent review caught an actual new-adapter failure: an unprepared WebSocket close raised and retained shared capacity. A real aiohttp integration regression reproduced500 instead of400; assignment only after successful prepare fixes it and permits a following valid connection. Ten focused offline tests then passed in0.424s. The earlier integration RED was two404s; these are connection-contract tests with fake Dialogs, not natural-language or acoustic acceptance.

The private source manifest now includes native_text_chat at a fixed canonical path and refreshes native_bridge only, preserving all other artifact entries. Standard read-only startup preflight passed using the native bridge venv. The server venv invocation initially failed because it lacks psutil; no package install or service action resulted. The first activation precheck used incorrect health key auth_mode; it aborted before creating a SPENT receipt or stopping anything. Corrected check uses actual authMode.

One idle Native-only reload then succeeded through the ordinary start_services startup lock, exact PID/create-time/executable/argv ownership and existing start_python primitive. Native20840 (launcher22724) became ready; nativeSessions0/authModeservicenow/asrReadytrue. Other observed Bot/controller/backend relay/gateway/speech listener generations and configuration/selection bytes were preserved. The unauthenticated exact text route now returns401 instead of404. No inference, audio, model restart, profile change, order or ServiceNow mutation occurred. Proofs:server/.local/voice-repair-20261102/task98-native-text-chat-20261107-v1/{pin-refresh.json,native-reload.SPENT.json,activation-result.json}. The one-shot activation is SPENT and must not be replayed.

Acceptance remains open: Work browser control is disabled, so the newly active native Chat route has not yet been exercised with its admitted native OAuth identity. Generic SDK administration credentials must not receive broadened Voice access merely to pass that test. The correct name remains Lea Oltmer; the supplied historical call had distorted ASR, one successful ServiceNow operation then three429 responses, followed by unsupported local technical claims. Shared queued transport and claim guards are active, but no later real call or original audio establishes recovery of acoustics or end-to-end natural dialogue. No further blind model prompt probes were run.

## Ergänzende Audio- und Zugangsprüfung

Der ergänzende Quellenaudit des Audiopfads ergab keinen nachgewiesenen neuen Defekt: Die STT-Quelle verwendet 16-kHz-Mono-PCM und eine ausdrücklich gesetzte deutsche Sprache. Die unveränderte Wellenform geht an die Spracherkennung; die entrauschte Fassung dient der Sprachaktivitätserkennung (VAD). Das vorhandene 120-ms-Anlaufverhalten bleibt eine mögliche Abnahmegrenze. Ohne Originalaudio oder einen neuen belegten Gerätevergleich ist weder dessen Einfluss auf den Satzanfang noch eine dadurch verursachte Namensverfälschung nachgewiesen. Diese Quellenprüfung belegt keinen akustischen Qualitätsgewinn.

Auch die öffentliche HTTPS-Weiterleitung für die genaue native Chat-Route `/text/chat/agent_operator` wurde ohne Anmeldung geprüft. Sie antwortete mit HTTP401 nach0,328Sekunden; der private Beleg `task98-native-text-chat-20261107-v1/public-route.json` bezeichnet dies ausdrücklich als reine Prüfung der nicht authentifizierten Reverse-Proxy-Route ohne Dialog oder Audio. Das bestätigt weder eine zugelassene native Chat-Sitzung noch einen erfolgreichen ServiceNow-Dialog. Der in Work deaktivierte Browserzugriff wurde im selben Arbeitsschritt erneut bestätigt. Eine eigenständige Browser-Abnahme mit der vorgesehenen nativen Anmeldung sowie die akustische und geräteübergreifende Abnahme bleiben offen. Für diese Ergänzung wurden keine Instanzänderungen, Laufzeitaktionen oder weiteren Tests ausgeführt.

## Historical capability-denial regression fixed and active —2026-11-07

Current source c8e4b5e (isolated e294e0f) extends the existing hard optional-output release category to the historical direct claim that the assistant has no technical connection functions. It does not infer names, profanity, destinations or business requirements. Ordinary current connection-failure notices, questions, reported/qualified speech and exact current owned native OutputText keep their previous authority. The transcript-based offline regression initially reproduced the leaked denial and invented detail request; after the fix it rejects the first optional sentence, suppresses the remainder, closes only the optional model session, emits observed failed-bootstrap status, preserves original FIFO and invokes Dialog zero times. Root's focused8tests passed in0.077s. Agent's related45tests passed in1.067s. No new inference/prompt probe was used; this is a narrow wording-class repair, not proof of general semantic accuracy.

Activated once through a new independently guarded idle Native-only attempt; previous SPENT activation receipts were preserved. Native19480/launcher10128 is the current observed owner; zero sessions/authModeservicenow/asrReadytrue. Bot/controller/gateway/speech listener generations and source/config/selection snapshot bytes were preserved. Exact private receipts:task98-native-text-chat-20261107-v1/capability-guard-reload.SPENT.json and capability-guard-activation-result.json. No model/profile/ASR/TTS change or ServiceNow write. Both Native activation helpers are now SPENT.

The source audio audit found consistent16kHz monoPCM16 and configured German across microphone/WAV/backend; raw audio goes to ASR while denoised audio determines speech activity. No new format/language bug is proved. A120ms onset minimum could affect extremely short isolated letters, but no retained waveform establishes that cause here; it was not changed speculatively. The public native Chat reverse-proxy route reaches its actual authorization check (unauthenticated401 in0.328s), not404. Browser use was freshly rechecked through CUA and remains disabled by Work settings; no nativeChrome bypass was attempted. There has been no fresh admitted real call since these activations. Full acoustic, natural conversation, repeated-call own-voice and cross-device acceptance remain unproved and require actual admitted dialogue evidence. Original historic audio is unavailable.
