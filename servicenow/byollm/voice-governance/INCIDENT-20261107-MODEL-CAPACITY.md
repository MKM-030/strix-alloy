# Modellplatz-Konflikt im Voice-Anruf vom 7. November 2026

Der Anruf `1f89384417af` gehört zur [ServiceNow-Conversation `65d2d46393505b94e7f2b9fa6aba1058`](https://soprasteriaassvsdemo14.service-now.com/sys_cs_conversation.do?sys_id=65d2d46393505b94e7f2b9fa6aba1058). Die Protokolle zeigen konkurrierende Zugriffe auf den einzigen Modellplatz. Dadurch scheiterten sowohl eine lokale Gesprächsantwort als auch nachfolgende ServiceNow-Modellaufrufe mit HTTP429.

## Nachgewiesener Ablauf

Die zentrale Auswahl verwendete Halogen 0.19.1 mit einem Modellplatz und einer gleichzeitigen Anfrage. Native lief noch mit dem ausdrücklich für parallelen Betrieb eingerichteten direkten Gesprächszugang auf Port8840. ServiceNow nutzte die gemeinsame Warteschlange auf Port8841. Die direkte Verbindung umging damit die gemeinsame Reihenfolge.

| Beobachtung | Ergebnis |
|---|---|
| Begrüßung auf dem lokalen Server | Erster PCM-Chunk um19:01:58.139 MEZ, Synthese und Annahme von368640PCM-Bytes bis19:02:04.750. Gerätewiedergabe bleibt separat zu bestätigen. |
| Erste erkannte Eingabe | ASR-Abschluss um19:02:12.471 MEZ. Der erkannte Wortlaut wurde lokal nicht gespeichert. |
| Lokale Gesprächsantwort | Verworfen um19:02:12.513, anschließend `controller_busy` um19:02:12.516. Dieses Merkmal wird ausschließlich nach HTTP429 gesetzt. |
| Gesprochener Fehlersatz | `Ich kann Ihre Frage gerade nicht zuverlässig beantworten.` stammt aus dem lokalen Fehlerzweig für eine angenommene Spracheingabe. Dieser Zweig setzt keine tatsächliche Frage voraus. |
| Erster ServiceNow-Modellaufruf | Erfolgreich, GenAI-Laufzeit21096ms. Die Antwort wählte die SCC-Aktion zum Erfassen der vier erforderlichen Angaben. |
| Weitere ServiceNow-Modellaufrufe | Dreimal HTTP429. Diese Antworten stimmen mit den drei GenAI-Fehlern `200000` überein. |
| ServiceNow-Plan | `a6d21c6393505b94e7f2b9fa6aba1003`, beendet mit `execution_failed`. Der native Start meldete anschließend `servicenow_startup_not_ready`. |

ServiceNow- und Windows-Uhren sind versetzt. Die Reihenfolge wird über IDs und Ereignisse korreliert. Laufzeiten stammen jeweils aus derselben Uhr.

## Installierte Korrektur

Die effektive Native-Konfiguration verwendet jetzt `http://127.0.0.1:8841/v1/chat/completions`. Dadurch teilen sich lokale Gesprächsantworten und ServiceNow-Modellaufrufe dieselbe vorhandene Warteschlange. Die verwendeten Zugangsdaten wurden vor der Umstellung auf Übereinstimmung geprüft.

Die Konfigurationsänderung betraf genau `conversation_http_url`. Die inaktive Native-Bridge wurde einmal neu geladen, PID21460 mit Launcher27580. Der Prüfbeleg bestätigt die erhaltenen zehn Modell-, Sprach- und Gateway-Prozessidentitäten sowie die bestehende zentrale Profilauswahl `69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84`.

Die reguläre Startprüfung kontrolliert jetzt einen ausdrücklich eingerichteten direkten Zugang auf Port8840. Dafür benötigt der Controller mindestens zwei gleichzeitige Anfragen und Halogen mindestens zwei Modellplätze. Bei einer widersprüchlichen Einstellung benennt die Prüfung den gemeinsamen Zugang auf8841 als erforderliche Korrektur. Der gemeinsame Zugang unterstützt die aktuelle Einplatz-Auswahl. Bereits laufende Verbraucher müssen bei einem zentralen Kapazitätswechsel weiterhin abgeglichen werden.

| Lokales Artefakt | Änderung |
|---|---|
| `voice/native-start/start_current_voice.py` | Prüfung der direkten Gesprächsadresse gegen die ausgewählte Controller- und Halogen-Kapazität. |
| `voice/native-start/qwen_asr_start.py` | Prüfsumme des aktualisierten Artefaktmanifests. |
| Private Datei `native-asr-artifacts.local.json` | Ausschließlich die Prüfsumme des geänderten Starters wurde erneuert. Alle übrigen Einträge wurden byteweise erhalten und gegen die Dateien geprüft. |
| `voice/tests/test_conversation_capacity.py` | Ein gezielter Offline-Regressionstest mit fünf Fällen. Die zwei erforderlichen Ablehnungen scheiterten vor der Korrektur und bestehen mit ihr. |

Die Quelländerung ist in Commit `b563ba0` enthalten. Die reguläre lesende Vorprüfung bestand anschließend mit bereiter CrispASR und gültigen HTTPS-Routen.

## Befund zur Spracherkennung und Begrüßung

Die fünf ASR-Aufrufe lieferten jeweils nichtleeren Text. Der geladene Erkennungspfad arbeitet mit Qwen3-ASR0.6B, CrispASR, 16kHz, Mono und dem empfangenen PCM-Signal. Die geprüften Dateien, Bibliotheken und Modellartefakte passen zu den festgelegten Prüfsummen. Die Qualitätsdiagnose des verwendeten Dienstes enthält Text ohne Wortwahrscheinlichkeiten oder Segment-Konfidenzen.

Für die Beurteilung der gemeldeten Wortfehler fehlen der erkannte Wortlaut und das zugehörige Audiosignal dieses beendeten Anrufs. Die ServiceNow-Nachrichten enthalten ebenfalls keine freien Nutzereingaben, weil der Start vor deren fachlicher Übergabe scheiterte. Aus fünf technisch erfolgreichen ASR-Aufrufen wird deshalb keine korrekte Worterkennung abgeleitet.

Eine begrenzte aktuelle Konfigurationsabfrage bestätigt Deutsch (`de`), die aktive eigene Stimme `Marcel Käfke (lokal)` mit Voice-ID `81959ffa-c2ef-4db5-bf95-5df2a24c9404` und leere Fachbegriffe. Der lokale Parametervertrag projiziert daraus `language=de` und eine leere Begriffsliste. Das native Voice-Profil enthält die Begrüßung zur Laptopbestellung mit der Frage nach dem Mitarbeiter. Das zugehörige fachliche Bot-Profil besitzt zusätzlich seinen allgemeinen VA-Begrüßungssatz. Diese aktuellen Datensätze ersetzen keine gespeicherte Einstellungsmomentaufnahme des früheren Anrufs.

Die lokale Begrüßung wurde vor der ersten ASR-Eingabe erzeugt. aiortc beginnt die Ausgabe erst nach aufgebauter ICE-/DTLS-Verbindung. Eine zusätzliche Bestätigung der Audio-Wiedergabebereitschaft des tatsächlichen iPhone-Clients liegt in den vorhandenen Belegen nicht vor. Die lokale TTS-Annahme allein bestätigt die Hörbarkeit auf dem Gerät nicht.

## ServiceNow-Metadaten und Update Sets

Der zusätzliche Konfigurationsschutz protokollierte `getnotfound` für `4780c7e193f747d0e7f2b9fa6aba1030`. Die Konfiguration existiert. Der Eintrag trat auch vor der erfolgreichen ersten Modellantwort auf. Die drei nachfolgenden Gesprächsfehler sind unmittelbar über die HTTP429-Antworten belegt.

Ein ergänzender Abgleich mit dem nativen Provider-Metadatenzugriff wurde vorbereitet. Der einmalige Installationsversuch hielt vor sämtlichen Schreibvorgängen bei der Prüfung eines neuen Update Sets an. Die Nachlesung bestätigte null neue Sets und den vorhandenen Mapping-Quellstand `dd5b33476b8dbfafa37f4c89648f335eee6d401ce0f6e31b3a8ffb4dad736f03`, Revision7. Diese vorbereitete Ergänzung bleibt zur gesonderten Prüfung zurückgestellt. Der Versuch ist als verbraucht gekennzeichnet.

Für diese Reparatur entstanden damit keine funktionalen Customer Updates in ServiceNow. Die dokumentierte ServiceNow-Änderungshistorie aus Task93/94 bleibt im [Änderungskatalog vom 6. November](CHANGELOG-20261106.md) beschrieben. Die zusätzliche SDK-Ausführung erzeugte ihre technische [Ausführungshistorie](https://soprasteriaassvsdemo14.service-now.com/sys_script_execution_history.do?sys_id=c177d46793905b94e7f2b9fa6aba107b).

## Prüfung und Fortsetzung

Die gezielte Offline-Regression und die reguläre Startvorprüfung sind bestanden. Ein anschließender einmaliger Test schickte zwei sehr kurze lokale Textanfragen gleichzeitig über die konfigurierte gemeinsame Adresse. Beide erhielten HTTP200 nach218 beziehungsweise359ms. Die Warteschlange zeigte dabei eine aktive und eine wartende Anfrage. Dieser Test bestätigt die Serialisierung des reparierten Zugangs.

Die geplante Prüfung des normalen Gesprächsstarts erreichte keinen fachlichen Dialog. Der erste Helfer wurde versehentlich mit dem Basis-Python statt der Native-Umgebung gestartet und scheiterte schon beim Import. Ein frischer Helfer mit der korrekten Umgebung erreichte anschließend die reguläre Voice-Zulassung. Diese lehnte den SDK-OAuth-Zugang mit `AdmissionDenied('unauthorized')` ab, bevor ein Dialog oder Modellaufruf entstand. Beide Helfer sind verbraucht. Über die angemeldete Testoberfläche wurde zusätzlich der Chat-Modus geprüft. Auch nach Neuladen kehrte die Oberfläche zu `No active chat` zurück. Die Oberfläche steht wieder im Voice-Modus ohne aktiven Anruf.

Die aktuelle gemeinsame Warteschlange und der Startschutz sind damit technisch geprüft. Die vollständige Voice-Konversation, die hörbare Begrüßung und die Wortgenauigkeit benötigen weiterhin einen neuen Geräteanruf mit zugänglichem Transkript.

Die privaten Rohbelege liegen unter `C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102/task97-latest-call-20261107-v1`. Wesentlich sind `shared-route-activation.SPENT.json`, `startup-guard-promotion.json`, `shared-queue-qualification.ONCE.json`, `stt-local-call-and-provenance.private.json`, `FINAL-STATE.private.json` sowie die korrigierten ServiceNow-Abfragen mit `DIRECT-NODE` im Dateinamen. Erste Windows-Wrapper-Abfragen verloren Filtertrennzeichen und wurden durch diese korrigierten Abfragen ersetzt.
