# ServiceNow Voice: Konfiguration und nachvollziehbare Änderungen

Stand: 6. November 2026. Instanz: `soprasteriaassvsdemo14`. Dies ist der Konfigurationsvertrag; der Aktivierungsnachweis wird im Abschlussprotokoll separat geführt.

## Dokumentation direkt in ServiceNow

Die 1.015 zuvor vorhandenen Customer Updates aus 50 nachgewiesen zugehörigen Update Sets haben jeweils einen individuellen Kommentar erhalten. Dieser benennt Artefakt, Zweck, Abhängigkeiten, erfasste Werte, Quellrevision, Update Set, Aktion und Payload-Digest. Historische Fassungen werden als solche beschrieben. Auch enthaltene Bereinigungs-/Löschaktionen werden dokumentiert; sie wurden weder neu ausgeführt noch aus den Payloads entfernt.

`sys_update_xml` hat kein Description-Feld. Dafür wird das native Feld **Comments** verwendet. Die ursprünglichen Payloads, Update-Namen, Aktionen, Scopes und Set-Zuordnungen bleiben erhalten. Abgeschlossene Set-Köpfe wurden nicht geändert.

Zusätzlich wurden 63 beschreibbare Dokumentationsfelder an aktuellen Quellartefakten ergänzt und regulär erfasst: 37 Prompt-Konfigurationen, 10 Business Rules, 11 Script Includes, ein Fix Script, eine REST-API und drei REST-Ressourcen. Bei 165 nicht beschreibbaren Feldern bleibt die Erklärung am Customer Update; eine vorhandene gültige REST-Kurzbeschreibung bleibt unverändert. Agenten-, Tool- und Assistant-Beschreibungen können laufende Anweisungen sein und erhalten keine administrativen Zusätze. Die veraltete Gemma-Erklärung des ReAct-Ledger-Helfers wurde modellneutral berichtigt.

Die vier neuen Dokumentationssets sind nach Anwendung getrennt. Der funktionale Referenzstimmen-Vertrag liegt separat in **SCC Voice 3.2 - ServiceNow Voice References - 20261106**. Die neue Quelldokumentation ändert keine Prompttexte, Modelle, Aktivierungen, Zugriffsregeln oder Geschäftslogik.

## Zuständigkeiten

ServiceNow führt den Laptop-Bestellprozess aus, prüft Angaben und Berechtigungen und holt die Bestellfreigabe ein. Das Gesprächsmodell darf während der Verarbeitung natürlich reagieren, aber keine erfolgreiche Speicherung, Prüfung oder Bestellung erfinden. AI Control Tower / Skill Kit bleiben die Quelle der Capability- und Modellzuordnungen. Die lokale Sprachkonfiguration wählt keine Geschäftsmodelle aus.

Der Assistant `8aa131d793f787105c8132d47aba1095` liefert seine autorisierten Einstellungen je Anruf. Sprache, Stimme und Gesprächspolitik werden als Anrufkontext übernommen. Eine spätere Konfigurationsänderung ersetzt keine bereits laufende Stimme.

## Parametervertrag

| Parameter / Quelle | Verarbeitung und Grenze |
|---|---|
| `language`; aktive `sn_voice_language_config` | Die konfigurierte Sprache wird an ASR, nativen Gesprächskontext und TTS gebunden. Der lokale Vertrag unterstützt Deutsch und Englisch. Andere Sprachen benötigen eine ausdrücklich unterstützte lokale Engine. |
| `tts_config_sys_id`, `voice_profile`, sprachbezogene TTS-Konfiguration, `voice_id` | Auswahl des exakten TTS-Datensatzes und der exakten Stimme; keine stillschweigende Ersatzstimme. Die Profilbezeichnung ist Anzeigeinformation, keine zusätzliche Modellwahl. |
| `voice_gender` | Beschreibt die gewählte Stimme. Keine nachträgliche Tonhöhen- oder Geschlechtsumwandlung. |
| `parameters.scc.reference` | Autorisierte WAV-Auflösung, Hash-/Größen-/PCM-Prüfung und unveränderliche lokale Registrierung; siehe unten. |
| Assistant-Prompt / native `systemMessage` | ServiceNow bleibt Quelle der Gesprächsleitplanken. Der Text wird unverändert konsumiert. |
| Native `introduction` | Konfigurierter Begrüßungstext; keine lokal festgeschriebene Ersatzbegrüßung. |
| `secondary_language_prompt` | Begrüßung nach ausdrücklicher Sprachwahl; keine Systemanweisung. |
| `enable_language_selection`, `language_input_selection`, `trigger_phrases`, Sprachwahlprompt | Sprachbasierte Auswahl anhand expliziter konfigurierter Triggerphrasen. Der aktuelle Assistant hat nur Deutsch. |
| `enable_dtmf`, `dtmf_language_selection_prompt` | Native Metadaten bleiben erhalten. Mehrsprachige DTMF-Auswahl wird vom Browsertransport abgelehnt, solange kein belastbarer Ziffer-zu-Sprache-Vertrag vorliegt. Keine Ableitung aus der Reihenfolge oder aus Prompttext. |
| Sprachbezogene `key_terms` | Werden dem vorhandenen ASR-Hotword-API übergeben und unter derselben Transkriptionssperre anschließend gelöscht. Kein Wechsel in einen Audio-Frage-Antwort-Modus. |
| Sprachbezogene Aussprache / `phonemes` | Werden autorisiert projiziert. Das lokale TTS hat keinen belegten Adapter für die native Phonemsyntax; diese Wirkung wird nicht behauptet. |
| `start_time_in_ms`, `stop_time_in_ms` / native VAD-Projektion | Die native API liefert hier Sekundenwerte, trotz Feldnamen. Unterstützte lokale Bereiche werden genau einmal in Millisekunden umgerechnet. Aktuell 0,1 / 1,2 Sekunden. |
| Native VAD `confidence`, `min_volume` | Werte werden erhalten und als Grenze ausgewiesen. Eine Gleichwertigkeit zur lokalen neuronalen VAD-/PCM-Skala ist nicht belegt; keine willkürliche Einheitenumrechnung. |
| `noise_suppression_level` | Native Konfiguration bleibt sichtbar. Die lokale RNNoise-Verarbeitung hat keinen gleichwertigen stufenlosen nativen Stärkeparameter; 50 wird nicht als nachgewiesene lokale Stärke ausgegeben. |
| `max_call_duration_in_minutes` | Anrufgrenze, innerhalb der bestehenden lokalen Obergrenze von einer Stunde. Aktuell 10 Minuten. |
| `user_inactivity_threshold_in_seconds` | Inaktivitätsgrenze, aktuell 30 Sekunden. |
| `filler_message_delay_in_seconds` | Wartezeit für den bestehenden asynchronen Gesprächspfad, aktuell 15 Sekunden. Kein Beleg für fachlichen Erfolg und keine Pflicht zu einem statischen Bestätigungssatz. |
| `number_delivery`, `identifier_delivery` | Aktuell `normal`: unveränderte natürliche Textausgabe. Abweichende native Sprechweisen benötigen einen eigenen nachgewiesenen Renderer; reine Metadatenübernahme stellt diese Wirkung nicht her. |
| `retry_prefix`, `goodbye_message`, lokale UI-Meldungen | Explizite Texte werden für ihre konfigurierte Primärsprache erhalten. Native englische Defaults werden nicht als deutsche Übersetzung ausgegeben. Retry-Budget der nativen Authentifizierung löst keine Wiederholung einer Geschäftsaktion aus. |
| `voice_max_retries`, `voice_minutes_account_is_locked`, `push_notification_max_polling_retries` | Native Authentifizierungs-/Sperrparameter; keine lokalen ASR- oder Bestell-Retries. |
| `caller_identification_fields`, `enable_phone_number_based_identification` | Native Identifizierung; keine lokale Identitätserfindung. |
| `enable_multifactor_authentication`, `auto_authenticate`, `disable_auth_v2`, primäre/sekundäre/Step-up-Authentifizierungs- und Identifizierungstypen | ServiceNow bleibt alleinige Authentifizierungsinstanz. Die Bridge umgeht diese Einstellungen nicht. |
| `fallback_option`, `require_auth_for_fallback_record_creation`, Fallback-Record-Producer, `mobile_fallback_record_producer` | Native Fallback- und Datenzugriffslogik; keine lokale Ersatz-Ticketerstellung. |
| `transfer_target`, `capture_pre_transfer_details`, `sip_context_header`, `communication_channel` | Native Telefonie-/Transferparameter. Ein WebRTC-Browser wird dadurch nicht zu einem PSTN-/SIP-Endpunkt. |
| `persist_context_data` | Native Persistenzpolitik; keine zusätzliche Berechtigung zur lokalen dauerhaften Speicherung von Anruferdaten. |
| `orchestration_mode`, `gateway_mode` | Native Betriebsmetadaten. `gateway_mode=cartesia` schaltet die lokale Engine nicht auf Cloud-Inferenz um. |
| Providerattribute wie Now LLM / Azure OpenAI | Modellkonfiguration in ServiceNow. Keine Auswahl eines lokalen Sprachdienstes und kein Cloud-Aufruf durch die Referenzstimmen-Anbindung. |

## Vorhandene eigene Stimme und weitere Stimmen

Die Stimme **Marcel Käfke (lokal)** ist bereits als nativer `sn_voice_tts_config`-Datensatz `c46f9ae4287e48d5a713fddf262afdfd` angelegt. Die gewählte Voice-ID ist `81959ffa-c2ef-4db5-bf95-5df2a24c9404`. Am Datensatz liegt `marcel-kaefke-reference.wav`, Attachment `7fa67ad293d01754e7f2b9fa6aba1052`, 657.452 Bytes. Der tatsächliche ServiceNow-Download stimmt mit der freigegebenen Aufnahme überein:

`f35a22ff7e12480c2be2a04180d4bee997aa6e82d809398eb619b58368463f46`

Der native Stimmenkatalog besitzt eine Schreib-ACL ohne Admin-Override. Ausschliesslich die Parameter dieses nachweislich eigenen, ungeschuetzten Datensatzes werden durch die freigegebene administrative Metadatenpflege aktualisiert; die ACL, ihre Rollen und alle Laufzeit-Lesepruefungen bleiben erhalten.

Es wurde keine zweite Aufnahme erzeugt und kein zweiter Stimmdatensatz angelegt. Die Referenz ist PCM16, mono, 24 kHz, 13,696 Sekunden. Aufnahme und dokumentierte Einwilligung stammen vom bereits freigegebenen eigenen Sprachprofil.

Eine weitere eigene Stimme wird in ServiceNow als TTS-Konfiguration angelegt, mit einer freigegebenen WAV-Datei am selben Datensatz verknüpft und für die gewünschte Assistant-Sprache ausgewählt. `parameters.scc.reference` enthält Version, Service-/TTS-/Voice-/Attachment-Identität, SHA-256, Größe, exakten Referenztext, Referenzsprache und Herkunft/Einwilligung. Eine andere Aufnahme erfordert einen neuen passenden Descriptor. Referenzsprache und Ausgabesprache sind getrennt; eine deutsche Referenz aktiviert keine englische Assistant-Sprache von selbst.

Die Bridge nutzt den **bestehenden** autorisierten Endpunkt `POST /api/sn_voice_aia/ai_voice_agent/agents_authorized` mit explizitem `voiceReferenceVersion:1`. Die ursprünglichen Service-, Agenten- und Bearer-Prüfungen bleiben vorgeschaltet. Der ausgewählte TTS-Datensatz, die Attachment-Zuordnung und die Leserechte auf beide Datensätze werden frisch geprüft; anschließend wird der Byte-Digest geprüft und `audio/wav` geliefert. Kein beliebiger Download-URL-Parameter, Redirect oder weitergereichter Administratortoken.

Die lokale Bridge prüft Größe, SHA-256 und WAV-Struktur erneut. Die Registrierung verwendet intern `snref-<Descriptor-SHA256>`: Die ausgewählte ServiceNow-Voice-ID bleibt nachvollziehbar mit dieser unveränderlichen Referenz verbunden. Ein anderer Referenztext oder eine andere Datei erhält eine andere interne Bindung. Ein Cachetreffer ersetzt niemals die Autorisierung des neuen Anrufers. Registrierungen gelten nur für die geprüfte lokale TTS-Prozessgeneration. Es gibt höchstens 32 lokale Referenzeinträge; eine volle Ablage wird ausdrücklich gemeldet und nicht während eines Anrufs automatisch bereinigt.

Die Original-Bearer-Anmeldung wird nur während der Vorbereitung benutzt, nicht auf Platte oder im Anrufkontext gespeichert. Die Vorbereitung reserviert die gemeinsame Browser-/SDK-Kapazität; sie verlängert nicht das bestehende Authentifizierungsbudget. Der lokale TTS-Prozess und die bestehende 18-GiB-Speicherreserve werden vor einer neuen Registrierung geprüft.

**Transport:** Ein TTS-Datensatz im Update Set beweist nicht, dass die WAV-Binärdatei mittransportiert wird. Auf einer Zielinstanz muss die berechtigte Aufnahme separat am korrekten TTS-Datensatz importiert und ihre zurückgegebene Attachment-ID im Descriptor gebunden werden. Keine festen produktionsfremden Attachment-IDs übernehmen. WAV-Dateien und Zugangsdaten gehören nicht in öffentliche Quellarchive.

## Reale iPhone-Beobachtung und verbleibende Abnahme

Der gemeldete Anruf `6cb2dafef338` erreichte keinen fachlichen Dialog. Der lokale Controller beendete Halogen wegen seiner Speicherreserve-/Erholungsbedingung. ServiceNow erhielt Bootstrap-Verarbeitung, aber keine fachlichen Nutzereingaben; es lief keine Bestellung und kein fachliches Tool. Der erste GenAI-Aufruf war erfolgreich (13.977 ms), die drei späteren Aufrufe meldeten Fehler. Die lokale ASR lieferte zwei nichtleere Erkennungen. Diese Beobachtung beweist daher keine fehlerhafte Verarbeitung vollständiger Bestelldaten.

Das unveränderte ausgewählte Halogen-Profil wurde einmal wiederhergestellt und ist per authentifizierter Health-Abfrage bereit. Ein Wiederherstellungsbeobachter meldete vorzeitig einen Fehler, weil die äußere Steuerung 9,45 Sekunden vor dem Backend bereit war; es wurde deshalb kein zweiter Modellstart ausgeführt.

Gezielte Offline-Prüfungen betreffen die neuen Grenzen (Sprache, Hotwords, Referenzbindung, Autorisierung, Reservierung und Audioabschluss). Es wurde keine neue Voice-Smoke-Serie, Mikrofonaufnahme oder Testbestellung durchgeführt. Physische iPhone-/Android-/Desktop-Gleichheit und der gesamte Bestellabschluss sind weiterhin durch einen realen erfolgreichen Durchlauf zu bestätigen.

## Primärquellen

- [ServiceNow Attachment API](https://www.servicenow.com/docs/r/api-reference/rest-apis/c_AttachmentAPI.html)
- [Scoped GlideDigest: Digest eines InputStreams](https://www.servicenow.com/docs/r/api-reference/server-api-reference/c_GlideDigestScopedAPI.html)
- [Customer Updates](https://www.servicenow.com/docs/r/platform-security/r_CustomerUpdatesTable.html)
- [Now Assist for Voice: konfigurierbare Aussprache, Sprachen und Wartezeiten](https://www.servicenow.com/docs/r/store-release-notes/na-suite-rn-2026-06-16.html)

Die konkrete Zuordnung und die Einheiten dieses Vertrags wurden zusätzlich aus dem tatsächlich installierten Schema und nativen Voice-Code abgeleitet. Allgemeine Produktdokumentation ist kein Nachweis dafür, dass eine fremde lokale Engine dieselben Fähigkeiten besitzt.
