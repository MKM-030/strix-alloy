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

Die letzte erfolgreiche Native-Aktivierung dieses Arbeitsschritts lud `a58c906` am 7. November um 19.21.54 UTC als PID14940. Dieser Prozess ist nach der späteren Laufzeitunterbrechung beendet. Die neueren Quellkorrekturen liegen im Repository vor. Ihre Übernahme in eine wieder laufende Sprachschicht wird im abschließenden Aktivierungsstand dokumentiert.

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

Der zuletzt beobachtete Vergleich läuft unter Controller27724 auf Port18840. Der Prozess wurde um 21.34.25,832406 UTC mit dem temporären Profil `mtp_gate_cost-raw-comparison/before.profile.json` und dessen Prüfsumme `2dc701…` erstellt. Der äußere Lauf beginnt mit `017694e…`, der Backend-Lauf mit `6fa7…`; Backend21040 war zuletzt im Start. Gateway17680 blieb erhalten. Der reguläre Voice-Starter verweigerte seine Vorprüfung mit „central selection changed“, bevor er einen Dienst startete.

Die normalen Aufrufdarstellungen von Controller und Gateway sind durch `fd06be1` und `9dfb3d0` im Quellstand berücksichtigt. `9a689e3` ergänzt die passende ASR-Starterbindung. Insgesamt bestanden 32 gezielte Offline-Prüfungen, eine Rückrufprüfung, vier Controller-Prüfungen und drei Gateway-Prüfungen; die direkte Dateiverifikation bestand ebenfalls. Zum Stand dieser Vorprüfung waren die Gesprächskorrekturen vorbereitet und die Sprachdienste beendet. Die spätere tatsächliche Aktivierung ist unten getrennt belegt.

Die Wiederherstellung wartet auf die Rückgabe des normalen Controllers an Port8840 mit dem gespeicherten Profil `serving0191-text32k-one-slot-2048.json`, Prüfsumme `69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84`. Der private Beleg `task98-normal-start-restoration-20261107-v1/RESTORATION-NOT-EXECUTED.json` hält den Stand von 21.37.25 UTC, sieben Quellbindungen und null Lebenszyklusaktionen aus diesem Reparaturablauf fest. Locks wurden nicht verändert. Ein neuer Nutzertest ist derzeit nicht angefordert; zunächst muss der normale Betrieb zurückgegeben und die Sprachschicht regulär wiederhergestellt werden.
## Ausstehende Abnahme

Offen bleiben eine angemessene natürliche Reaktion auf unklare Namen und Verbindungswünsche, ein neuer vollständiger ServiceNow-Dialog und die hörbare Ausgabe auf dem Gerät. Gleiches Verhalten auf iPhone, Android und Computer sowie der vollständige Bestellabschluss sind durch diese begrenzten Text- und Metadatenprüfungen nicht abgenommen. Agententests stoppen an jeder Bestellfreigabe.

Die privaten Nachweise liegen unter `C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102` in den Task98-Transkript-, Vokabular- und drei Textprüfungsordnern. Maßgeblich sind `grounding-activation.SPENT.json`, `GENERIC-KEY-TERMS.FINAL-STATE.private.json`, die drei tatsächlich ausgegebenen `response.txt`, die Ablehnung in `semantic-review.json` und der zurückgezogene Aktivierungsbeleg. Der frühere Reservefehler liegt im Backend-Lauf `70499da200b84b3f9a5483fd247af4cb`, der historische Bereitschaftsbeleg im Lauf `7641d38d806f4771b6db40f3ec3de9a7` und der aktuelle Nichtausführungsbeleg in `RESTORATION-NOT-EXECUTED.json`.
## Ergänzung zur Rückgabe um 21.40 UTC

Der externe Vergleich wurde inzwischen beendet. Der reguläre Controller19368 mit Lauf `654d152776da452782f388a2aed8805d` startet wieder auf8840 mit exakt gespeichertem ProfilSHA69b91…. Um21.40.16UTC war dieser Start noch nicht bereit; Gateway17680 blieb aktiv. Voice-Dienste und Aktivierung werden erst nach bestätigter regulärer Bereitschaft geprüft.

## Tatsächliche Aktivierung um21.44UTC

Nach bestätigter normaler Bereitschaft bestand die vollständige lesende Startvorprüfung. Der reguläre Starter stellte die Voice-Dienste einmal zwischen21.44.36 und21.44.49UTC wieder her. Native23256/Launcher4088 und Bot8052/Launcher5852 wurden gestartet; TTS25816 registrierte die ausgewählte deutsche eigene Stimme, CrispASR meldete bereit. Controller19368, Backend24360 und Gateway17680 behielten exakt ihre vor dem Voice-Start geprüften Prozessgenerationen. Native-Konfiguration und gespeicherte Modellauswahl blieben bytegleich; alle sieben festgehaltenen Quellprüfsummen blieben erhalten. Freier Speicher danach20,743GiB, vorhandene18GiB-Reserve unverändert.

Die neue Bridge meldete `status=ok`, `asrReady=true`, `nativeSdkEnabled=true` und null Sitzungen. Der öffentliche HTTPS-Zugang lieferte um21.45.38UTC HTTP200 in2,672s mit demselben Status. Dies ist eine reine lesende Erreichbarkeitsprüfung. Es gab bei dieser Wiederherstellung keine Modell-Inferenzanfrage, keine Audioaufnahme/-probe und keine fachliche ServiceNow-Anfrage. Ein tatsächlicher neuer iPhone-Dialog bleibt offen.

Nachweise: `task98-normal-start-restoration-20261107-v1/activation.SPENT.json`, `ordinary-start.log`, `public-health.json` und `pin-refresh.json`. Die vorangegangene Datei `RESTORATION-NOT-EXECUTED.json` beschreibt ausschließlich die frühere Vorprüfung um21.37UTC. Der Aktivierungsvorgang ist verbraucht und darf nicht wiederholt werden.
