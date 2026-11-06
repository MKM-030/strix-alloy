# Änderungsprotokoll · 6. November 2026

Nachtrag zum späteren echten iPhone-Versuch: [Fehlerbefund, installierte Korrekturen und aktuelle Abnahmegrenzen](INCIDENT-20261106-IPHONETEST.md). Die nachfolgende Inventarzahl beschreibt den abgeschlossenen Dokumentationsstand vom Vormittag.

Instanz: `soprasteriaassvsdemo14`. ServiceNow-Installation, native Stream-Prüfung, unabhängiger WAV-Hash und tatsächliche Python-DTO-Prüfung sind erfolgreich. Der finale und der unabhängige Audit bestätigen **1.081 kommentierte Customer Updates in 56 Sets**: 1.015 ursprüngliche und 66 neue Captures. Der [zeilenweise Katalog](customer-update-catalog-20261106.csv) enthält die einzelnen Artefakte, historischen Fassungen, Aktionen und Set-Zuordnungen.

## Geänderte ServiceNow-Datensätze

| Datensatz / Umfang | Änderung und Capture |
|---|---|
| [Global-Property `631c110393d85b585c8132d47aba1023`](https://soprasteriaassvsdemo14.service-now.com/sys_properties.do?sys_id=631c110393d85b585c8132d47aba1023) | Neu: `local_llm.voice.reference.8aa131d793f787105c8132d47aba1095.c46f9ae4287e48d5a713fddf262afdfd`. Referenz-Descriptor, Typ String, `is_private=false`, `ignore_cache=true`; keine Zugangsdaten oder Audiodaten. [CU `231c110393d85b585c8132d47aba102d`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=231c110393d85b585c8132d47aba102d). |
| [Script Include `LocalLLMVoiceAssistantSettings`](https://soprasteriaassvsdemo14.service-now.com/sys_script_include.do?sys_id=6bf331459344d7905c8132d47aba1008) | Prüft den ausgewählten nativen TTS-Datensatz und einen vorhandenen Inline-Descriptor. Nur bei fehlendem Inline-Wert liest es die eigene Property unter dem ursprünglichen Anrufer mit sicheren Datensatz-/Feldprüfungen. Native Engine, Profil und WAV-Hash bleiben bindend. [CU `882c110393d85b585c8132d47aba10a4`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=882c110393d85b585c8132d47aba10a4). |
| [REST-Ressource `Authorized agents`](https://soprasteriaassvsdemo14.service-now.com/sys_ws_operation.do?sys_id=66b97ca0ff6a6210129628ecf43bf1cf) | Bestehender autorisierter Endpunkt mit expliziter Referenzversion; frische Auswahl-/ACL-/Parent-/Hash-Prüfung und erneute Prüfung vor WAV-Ausgabe. Keine beliebige Download-Adresse oder Ersatzstimme. [CU `802c110393d85b585c8132d47aba10b2`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=802c110393d85b585c8132d47aba10b2). |
| 63 administrative Quelldokumentationen | 37 Prompt-Konfigurationen, zehn Business Rules, elf Script Includes, ein Fix Script, eine REST-API und drei REST-Ressourcen. Die Beschreibungen erklären jeweils das konkrete Artefakt; funktionale Prompt-/Assistant-/Tool-Anweisungen erhielten keine Verwaltungszusätze. Dies ergibt die übrigen 63 neuen Captures. |
| 1.081 Customer-Update-Kommentare | Alle inventarisierten Captures sind einzeln kommentiert, einschließlich historischer Fassungen und vorhandener Lösch-/Bereinigungscaptures. Diese Aktionen wurden nicht erneut ausgeführt. 165 nicht beschreibbare Quelldokumentationsfelder und eine gültige REST-Kurzbeschreibung blieben erhalten; deren CU-Kommentare decken den Zweck ab. |
| [Nativer `IsMetadataUpdated`-Capture `08c46f9693d45f185c8132d47aba106f`](https://soprasteriaassvsdemo14.service-now.com/sys_update_xml.do?sys_id=08c46f9693d45f185c8132d47aba106f) | Der Zweckkommentar wurde berichtigt. Die Plattform erneuerte ausschließlich die Payload-Auditfelder `sys_mod_count` 321→325 und `sys_updated_on`; die semantischen Felder blieben identisch. Diese ausdrückliche Ausnahme schließt eine Behauptung pauschaler Byte-Identität aller alten Payloads aus. |

Der [native eigene TTS-Datensatz](https://soprasteriaassvsdemo14.service-now.com/sn_voice_tts_config.do?sys_id=c46f9ae4287e48d5a713fddf262afdfd) wurde **nicht geändert**. Vollständiger Snapshot, ACL und vorhandener WAV-Anhang sind unverändert. Es gab keinen weiteren WAV-/Sidecar-Upload, keinen neuen Stimmdatensatz und keine Rollen-, ACL- oder Cross-Scope-Freigabe. Die 50 ursprünglichen Set-Köpfe und die bestehende fachliche Zuständigkeit von ServiceNow blieben erhalten.

## Sechs neue Update Sets

| Set | Zweck |
|---|---|
| [Dokumentation · Voice `022bd6e9`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=6d67458f93541394e7f2b9fa6aba106d) | Administrative Quelldokumentation im Voice-Scope. |
| [Dokumentation · Anwendung `32808450`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=a967c98f93541394e7f2b9fa6aba108f) | Administrative Quelldokumentation im zugehörigen Anwendungsscope. |
| [Dokumentation · Anwendung `7cc4ec81`](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=6567c98f93541394e7f2b9fa6aba1090) | Administrative Quelldokumentation im zugehörigen Anwendungsscope. |
| [Dokumentation · Global](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=2167c98f93541394e7f2b9fa6aba1091) | Administrative Quelldokumentation im Global-Scope. |
| [SCC Voice 3.2 · ServiceNow Voice References](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=e967c98f93541394e7f2b9fa6aba1091) | Zwei funktionale Voice-Code-Captures für Einstellungen und autorisierte Referenzausgabe. |
| [SCC Voice 3.2 · Local Voice Reference Registry](https://soprasteriaassvsdemo14.service-now.com/sys_update_set.do?sys_id=b9995583931c1394e7f2b9fa6aba10c0) | Ein funktionaler Global-Capture für die eigene Referenz-Property. |

## Lokale Dateien und Verhalten

| Dateien / Bereich | Änderung |
|---|---|
| Qwen C++ `src/tts-server.h`, `tools/tts-server.cpp` und betroffene Generierungs-/HTTP-Abschlusslogik | Nicht-EOS-Abbrüche schließen einen PCM-Stream nicht mehr wie vollständige Sprache ab. Request-lokale Sprache `german`/`english`, Ablehnung ungültiger Sprachen vor Chunk-Headern und lesender Capability-Endpunkt. Alte Anfragen ohne Sprache behalten die Startsprache. |
| `voice/native-bridge/native_bridge.py`, `native_duplex.py` | Exakte Anrufstimme/-sprache; Capability-Prüfung vor Englisch; unveränderte 375-Token-Grenze. PCM-Ausgabe bleibt auf 30 Sekunden und den bestehenden 45-Sekunden-Ausgabezeitraum begrenzt. Fehler/Teil-Audio werden nicht als vollständig gehörte Antwort oder Freigabe behandelt. |
| `voice/audio_service.py`, `voice/native_qwen_asr.py` | Sprachbezogene Begriffe über die vorhandene geprüfte CrispASR-Hotword-Schnittstelle. Begrenzte JSON-Eingabe, Setzen/Löschen unter derselben Sperre, keine Begriffsübernahme zum nächsten Anrufer; bei fehlgeschlagener Bereinigung wird die Sitzung geschlossen. |
| `voice/native-bridge/assistant_settings.py` | Strenge Service-/TTS-/Voice-/Referenzprüfung und unveränderlicher vorbereiteter Handle; vollständiger Descriptor-Fingerprint samt exakter Registry-ID verhindert die Wiederverwendung eines alten Referenztexts bei gleichem WAV-Hash. |
| `voice/native-bridge/voice_reference_cache.py`, `voice_reference_runtime.py` | Frische Anrufer-Autorisierung auch bei Cachetreffern; feste Instanzadresse, keine Redirects, begrenzte WAV-/Hash-/PCM-Prüfung. Registrierung unter `snref-<Descriptor-SHA256>` für die geprüfte TTS-Prozessgeneration; höchstens 32 lokale Referenzeinträge. Zugangsdaten werden nicht gespeichert. |
| SDK-/Browser-Zulassung in `native_bridge.py`, `sdk_sessions.py` | Gemeinsame Kapazitätsreservierung während der asynchronen Referenzvorbereitung, begrenzte Vorbereitung und Freigabe bei Fehler/Abbruch. Native Autorisierung bleibt vorgeschaltet; kein zusätzliches Geschäfts- oder Authentifizierungsrecht. |
| `voice/native-start/qwen_asr_start.py`, private Artefaktpins und Aktivierungshelfer | Neue Settings-/Referenzmodule werden mitgeprüft. Frische Prozessidentitäten statt alter PID-Annahmen; nur drei verifizierte Worker gestoppt, Redirectoren natürlich beendet, fünf geprüfte TTS-Binärdateien mit Rollback-Kopien ersetzt, normaler Start einmal. |
| Bestehender Halogen-Wiederherstellungspfad / ausgewähltes Profil | Den belegten Speicherreserve-Ausfall abgegrenzt und das unveränderte ausgewählte Modell einmal wiederhergestellt. Keine Absenkung der 18-GiB-Grenze, kein Modellwechsel und kein zusätzlicher Inferenzbenchmark. |

## Tatsächliche Nachweise und Grenzen

Die lokale Aktivierung bestätigt Native **23168**, TTS **5644** und ASR **16592**. Bot **20180**, Gateway, Halogen-Steuerung, WSL-Relay und ausgewähltes Profil blieben erhalten. Die ursprüngliche Voice-ID `81959ffa-c2ef-4db5-bf95-5df2a24c9404` und Referenz-SHA-256 `f35a22ff7e12480c2be2a04180d4bee997aa6e82d809398eb619b58368463f46` sind unverändert.

Installations-Readback und unabhängige Python-DTO-Prüfung bestätigen `de`, die eigene Stimme/Referenz, `halogen-v2` und die konfigurierte Begrüßung mit **147 Zeichen**, SHA-256 `5ee9e211647b98192ff36385c3532c9829e8f70b75e334b8cd23b5c7cfda4daa`. Die native Stream-Methode und der unabhängig gelesene Attachment-Digest sind validiert. Der Abschlussaudit nutzt gespeicherte Beobachtungen; der vollständige Inventarstand wurde um eine exakte spätere Nachlesung des nativen Auditfeld-Captures ergänzt.

Dies ist **kein** Nachweis eines HTTP-Rundlaufs mit dem ursprünglichen Anrufer-Bearer, einer hörbaren Begrüßung oder eines erfolgreichen iPhone-/Android-/Desktop-Gesprächs. Es wurde keine neue Bestellung ausgeführt oder deren Abschluss bestätigt. Native Telefonie-/Authentifizierungseinstellungen und unbelegte lokale Phonem-, VAD-Skalen- oder Rauschstärkenwirkungen bleiben in der [Parametermatrix](README.md#parametervertrag) ausdrücklich eingegrenzt.
