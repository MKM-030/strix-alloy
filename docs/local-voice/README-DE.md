# ServiceNow Local Voice 2.0 – konsolidierter Importstand

Stand: 19.10.2026. Der konsolidierte native Originalexport einschließlich der eigenen Infrastruktur-/Validierungsbasis ist erstellt und geprüft. Eine Preview beziehungsweise ein Import auf einer frischen Zielinstanz sowie die aktuelle physische Android-/iOS-Audioabnahme stehen noch aus.

## Konsolidierter Lieferstand

Für ServiceNow wird **eine konsolidierte XML-Datei** verwendet: `ServiceNow-Voice-2.0-Konsolidiert-20261019.xml`.

| Merkmal | Geprüfter Stand |
| --- | --- |
| Dateigröße | 5.028.890 Bytes |
| SHA-256 | `7cce5efc22353bb64f5f3ef36de54d4092c3d7c59dc961bfe8d412647b6e7003` |
| Native Hierarchie | 31 eindeutige Update Sets; 32 serialisierte Header mit einer identischen Root-Wiederholung |
| Customer Updates | 812; davon 783 unterschiedliche CU-Namen |
| Versionsüberschneidungen | 29 zusätzliche Versionsvorkommen zu 26 geteilten CU-Namen |
| Konsolidierung | Neuer globaler Release-Parent mit den sechs öffentlichen Roots; native Hierarchie und Kaskade verwendet |
| Quellenintegrität | Alle ursprünglichen 30 Set-Inventare und rohen Payload-Hashes nativ und offline unverändert bestätigt |
| Abschluss | Alle 31 Sets Complete; native Base-Kaskade und Originalexport abgeschlossen; Kontext wiederhergestellt; keine Produkt- oder CU-Payload-Änderung durch die Konsolidierung |

Infrastructure 1.0, Validation 1.0.1, Core 1.1, Gemma 1.2, Foundation 1.0 und Voice 1.3 sind als sechs Teilstände enthalten. Foundation mit 254 und Voice 1.3 mit 36 Customer Updates sind ebenfalls Complete und exportiert. Für eine neue Zielinstanz wird die gemeinsame **2.0-Datei mit Preview des gesamten Verbunds** verwendet; die früheren Teil-Exporte sind keine feste lineare Importfolge.

**Infrastructure 1.0** und **Validation 1.0.1** sind im finalen Gesamtverbund enthalten. Die eigene Mirror-State-Tabelle besitzt Admin-ACLs. Native Voice-/Skill-ACLs werden dafür nicht geändert; zusätzliche mobile Benutzerrollen werden nicht eingeführt. Mirror-Automation, `apply_enabled` und `serialized_execution_verified` bleiben bis zu einer gesonderten Qualifikation aus. Aktivierende Properties werden nicht transportiert.

Das XML ist ein unveränderter nativer Originalexport. 17 geschützte native Kompatibilitätseinträge sind ausgeschlossen und wurden nicht geöffnet. Credentials, private Update-Set-Zuordnungswerte und Quellhost-Adressen sind im geprüften XML nicht enthalten. Native Creator-/Updater-Metadaten bleiben erhalten. Passende native Produkt- und Versionsvoraussetzungen werden weiterhin benötigt.

## Zuständigkeiten und Parameter

Modell, Custom-LLM-Provider und Skill-/Prompt-Konfiguration bleiben im AI Control Tower beziehungsweise im Skill Kit. Die native Voice-Konfiguration bestimmt Systemanweisungen, erste und weitere Sprachen sowie Voice-Ablauftexte. Der Modelladapter enthält keine feste deutsche Sprachvorgabe. TTS, STT, VoiceStudio und vorhandene Custom-Stimmen werden durch dieses Paket nicht ersetzt.

| Einstellung | Umsetzung und Grenze |
| --- | --- |
| Voice-Beschreibung / Systemanweisung | Frische native Auflösung je Skill-Aufruf; vollständiger Text im tatsächlichen ReAct-Prompt geprüft; Originalpersona erhalten |
| Erste und weitere Sprache | Nur native konfigurierte Sprachen wählbar; bei deaktivierter Auswahl gilt die erste Sprache; gewählte Sprache im STT-, Konversations- und Skill-Kontext |
| Begrüßung / Sprachwahl / Abschluss | Lokaler Session-Ablauf; zusätzliche Begrüßung nach Auswahl nur bei mindestens zwei konfigurierten Sprachen |
| Nummern / Kennungen | Native Sprechvorgaben im tatsächlichen Skill-Prompt; Befolgung und andere mögliche Modi sind keine pauschal bestätigte TTS-Funktion |
| VAD / Inaktivität / maximale Dauer | Vorhandene lokale Verbraucher mit dokumentierten Grenzen und Operator-Hostcap; native VAD-Schnittstelle maßgeblich |
| Prompt-Rolle / final gerenderter Text | Inhalt und Reihenfolge im Modellrequest erhalten |
| Temperatur / Ausgabetokens / Sampling / Stop / Penalties | Typisierte, profilabhängig validierte Übergabe; aktuelles Backend verwendet repeat_penalty für repetition_penalty |
| Antwortschema | Native NameValue-JSONdarstellung einmal dekodiert und unverändert übertragen |
| Nicht unterstützte Inferenzoptionen | Klare Fehlermeldung statt stiller Ignorierung |
| 39 Behavior-Felder | Definierte Allowlist, private Projektion bei vorhandenen nativen Werten; mehrere Felder bleiben ausdrücklich Metadaten |
| Cloud-Stimmkennungen / Phoneme | Begrenzt projiziert und privat erhalten; keine bestätigte Zuordnung zur lokalen Custom-Stimme oder Phonemverarbeitung durch TTS |

Telephony-, Transfer-, MFA-, Noise- und DTMF-Funktionen benötigen einen passenden Transport beziehungsweise eine eigene Implementierung. Metadaten allein sind kein Funktionsnachweis. `voice_max_retries` bleibt native Authentifizierungsmetadaten und erzeugt keine ASR-, Modell- oder Business-Action-Retries.

Die Einzelzuordnung steht in [parameter-matrix-current.json](parameter-matrix-current.json). [final-source-hashes.json](final-source-hashes.json) enthält die aktuellen eigenen Codefeld-Hashes einschließlich des globalen `CustomLLMPromptMirror` sowie die 14 DE/EN-Hinweise für den fachlichen Abgleich von Preview-Konflikten. Der aktuelle Gemma-Transport ist geprüft; der separate historische Halogen-Transformer ist nicht automatisch migriert. Weitere Modelle benötigen ein qualifiziertes Fähigkeits- und Transportprofil.

Die vollständige Schrittfolge mit lokalen Diensten, Bezug der erforderlichen Host-Basis, Ports, Startreihenfolge und Abnahme steht in [NEUINSTANZ-INSTALLATION-DE.md](NEUINSTANZ-INSTALLATION-DE.md).

## Import auf einer weiteren Instanz

1. Zielrelease, installierte Store-Apps, Tabellen und Lizenzen für Voice, AI Agents, Skill Kit, Custom LLM und verwendete Skills prüfen. Native Provider-, Capability-, Flow-, Validator- und Parent-Konfigurationen bleiben Voraussetzungen. Zwei native Parent-Konfigurationen der Foundation benötigen eine passende Zielinstallation.
2. Die **eine konsolidierte 2.0-XML** in ServiceNow laden. Die native Preview auf dem **gesamten Base-/Batch-Verbund** ausführen.
3. Alle Überschneidungen und Abhängigkeiten gemeinsam prüfen. Die 29 zusätzlichen Versionsvorkommen betreffen 26 geteilte CU-Namen. Eigene bestehende Zieländerungen fachlich abgleichen; für die eigenen aktuellen Code-Datensätze einschließlich des globalen `CustomLLMPromptMirror` die Hashes aus `final-source-hashes.json` heranziehen. Keine pauschale Konfliktentscheidung treffen.
4. Nach geklärten Preview-Ergebnissen den gesamten nativen Batch committen. Die bisherige Exportprüfung ersetzt keine erfolgreiche Ziel-Preview und keinen Zielimport.
5. Verbindungen, Credentials, lokale Endpunkte sowie operative Voice-/NAVA-/Profilzuordnungen auf der Zielinstanz separat privat konfigurieren. Dafür einen eigenen privaten Capture-Kontext verwenden; öffentliche Standardwerte enthalten keine operative Quellinstanz-Zuordnung.
6. Modell und Skills über AI Control Tower / Skill Kit konfigurieren. Eine dedizierte Voice-zu-NAVA-Zuordnung im privaten Capture-Kontext einrichten. Die Synchronisierung erhält die Originalpersona und prüft die genaue Quelle. Für die Voice-/Modellkorrektur wurden keine Laufzeitrollen erweitert, um Zugriffsprüfungen zu umgehen; vorhandene eigene Zugriffsmetadaten des Gesamtpakets sind in der Preview mitzuprüfen.
7. Den getrennten Host-Quelloverlay anhand des geprüften Basisstands kontrolliert abgleichen und übernehmen. Das Update Set installiert keine Host-Laufzeit, Python, Modellgewichte, TTS/STT oder TURN.
8. Android und iOS jeweils mit Begrüßung, erster Antwort, Folgeturn und sauberem Abschluss am Gerät prüfen. Weitere Sprachen nur bei tatsächlich konfigurierter Zweitsprache prüfen. Netzwerkwechsel getrennt testen.

Die offiziellen ServiceNow-Anleitungen beschreiben [Update-Set-Hierarchien](https://www.servicenow.com/docs/r/xanadu/application-development/system-update-sets/us-hier-overview.html) und die [Preview eines abgerufenen Update Sets](https://www.servicenow.com/docs/r/zurich/application-development/system-update-sets/t_PreviewARemoteUpdateSet.html). Zielrelease und installierte Anwendungen bleiben maßgeblich. Eine frische Ziel-Preview und ein frischer Zielimport sind noch nicht nachgewiesen.

## Separater Host-Overlay

Der geprüfte öffentliche Host-Quelloverlay mit optionaler RTC-Diagnose umfasst 39 Dateien, darunter acht Runtime-Dateien. 191 portable Prüfungen und zwölf Installer-Prüfungen bestanden; der Privacy-Audit meldet null Befunde und die unabhängige Review ist bestanden.

Der Basisstand ist `af7845c53d1185d364a3d2a17ff28f9266d82215`. Bestehende lokale Abweichungen müssen vor Übernahme kontrolliert abgeglichen werden. **Installer-Apply bleibt gesperrt; standardmäßig ist nur der Prüfmodus vorgesehen.** Ein automatisch freigegebener Host-Installer wird nicht zugesagt. Der Quelloverlay und die bestehenden privaten Verbindungs- und Dienstkonfigurationen sind separat zu behandeln.

Der bisherige Overlay bleibt als geprüfte Basis unverändert. Die separate Erweiterung unter `relay-overlay/` ergänzt private hostseitige TURN-Konfiguration. Ein öffentlicher Relay-Endpunkt und dessen Credentials sind Betreiberressourcen; aktuelle Geräteabnahme und Aktivierung sind offen. Die XML-Datei bleibt unverändert. Der Overlay ist keine vollständige Hostinstallation; Beschaffung der vollständigen Basis ist in der Installationsanleitung erklärt.

## Mobile Audiofunktion und Latenz

Der OAuth-Zugangsfehler ist behoben: native Plattformvalidierung, aktiver Service und Agent-Ausführungsrecht bleiben maßgeblich; opaque OAuth-Token werden nicht durch eine zusätzliche unpassende JWT-Annahme abgewiesen. Die frühere temporäre Authentisierungsdiagnose wurde entfernt.

Ein nachfolgend beobachteter SDK-Aufruf erhielt erfolgreiche HTTP-Antworten für Session und Signalisierung. Danach scheiterte ICE; am Server kamen keine Audioframes an. Die Client-Plattform ist aus diesen Logs nicht sicher bestimmbar. Der Audiotransport ist deshalb weiterhin **nicht als behoben nachgewiesen**.

Die neue RTC-Diagnose ist davon getrennt. Im öffentlichen Paket ist sie standardmäßig aus. Auf dem Referenzhost wurde sie mit Budget für genau ein autorisiertes Gespräch und höchstens drei Zustandsaufnahmen aktiviert. Sie protokolliert keine SDP-, IP-, Port-, Token-, Ufrag-, Passwort- oder Gesprächsinhalte. Die frischen externen Android-/iPhone-Fehlversuche sind inzwischen ausgewertet; das Ein-Gespräch-Budget wurde verbraucht. SDP und Kandidaten sind konsistent, TTS beginnt nach 46–47 ms, ICE/DTLS liefern jedoch keinen nutzbaren Medienpfad. Das genaue verwerfende NAT-/Firewall-Gerät ist nicht identifiziert.

Der Modelladapter ist nativ für Quick, Unified und ReAct geprüft. Der tatsächliche gemappte ReAct-Prompt enthielt die vollständige aktuelle Voice-Anweisung, die gewählte Sprache und Sprechpräferenzen ohne ungelöste Referenz. Die aktuelle Gemma-Probe dauerte 45,172 Sekunden bis zur nächsten Eingabebereitschaft. Die zugeordneten Modellzeiten der beiden vorhandenen Messfenster betragen 29,057 beziehungsweise 28,372 Sekunden; der jüngste Anstieg entsteht überwiegend außerhalb des Modells bei CREATE-/START-Callbacks. Eine durchgängige Request-ID und ein kontrollierter aktueller Halogen-Vergleich fehlen. Eine Beschleunigung der mobilen Gesamtlatenz wird nicht behauptet. Der finale Voice-Policy-Teststand umfasst 119 bestandene Prüfungen in neun Dateien.

Der aktuelle Netzwerkbefund und seine Grenzen stehen in [NETZWERK-UND-LATENZ-20261019.md](NETZWERK-UND-LATENZ-20261019.md).

Die bisherigen Verläufe bleiben in [MOBILE-HISTORY-DE.md](MOBILE-HISTORY-DE.md) und [GEMMA-MIGRATION-DE.md](GEMMA-MIGRATION-DE.md) dokumentiert.

## Dokumentationsübergabe und öffentliche Freigabe

Ein lokaler Übergabetext für den Dokumentations-Chat liegt bereit. Lesen, Auflisten und Senden über dessen Verbindung scheiterten mit `MCP-32000`; eine Empfangsbestätigung liegt nicht vor. Eine erfolgreiche Synchronisierung mit diesem Chat wird nicht behauptet.

Instanzspezifische Konfigurationen, Credentials, operative Profilbindungen, Referenzstimmen, Modellgewichte, Rohlogs und instanzgebundene Installations-/Bootstrap-Skripte gehören nicht in das öffentliche Quellpaket. Vor einer bestätigten Community-Freigabe bleiben Zielimport und physische mobile Audiofunktion zu prüfen.
