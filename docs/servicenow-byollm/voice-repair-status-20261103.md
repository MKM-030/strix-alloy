# Voice-Reparatur: geprüfter Stand am 3. November 2026

Die vorzeitige Mitarbeiterfrage in der Begrüßung ist korrigiert. Beide tatsächlich verwendeten Begrüßungsquellen enthalten jetzt: **„Hallo und willkommen. Wie kann ich Ihnen helfen?“** Eine frische öffentliche Voice-Konfigurationsabfrage unter dem ursprünglichen Benutzer hat genau diesen Text bestätigt. Die vollständige Gesprächsreparatur ist weiterhin offen.

## Zwei Profile mit unterschiedlichen Aufgaben

| Quelle | Profil | Begrüßungsdatensatz |
| --- | --- | --- |
| Native Voice-Konfiguration und deren `prompt.introduction` | `4ea175d793f787105c8132d47aba1032` | `0ea175d793f787105c8132d47aba1041` |
| Zugeordnetes lokales Ausführungsprofil und dessen nativer Profil-Test | `c623e20f93374354e7f2b9fa6aba1081` | `5a23e20f93374354e7f2b9fa6aba10fb` |

Die öffentliche Projektion zeigt das zugeordnete Ausführungsprofil als `context_profile`. Die native Prompt-Erzeugung verwendet für die Begrüßung jedoch weiterhin das ursprüngliche Voice-Profil. Aus dem projizierten Profil allein darf deshalb keine Herkunft des Begrüßungstextes abgeleitet werden. Ein erster öffentlicher Vergleich erkannte diese Abweichung; erst die Korrektur beider Quellen ergab den bestätigten neuen Text.

Die beiden normalen, ausschließlich den Nachrichtentext betreffenden Änderungen liegen im eigenständigen Update Set **SCC Voice Welcome Repair 2026-11-03**, `f06f27f1939cd3185c8132d47aba1087`, Anwendung Generative AI Controller. Die vollständige Rücklesung bestätigte 34 Nachrichten-Datensätze, die unveränderten übrigen 32 Nachrichten, unveränderte Profilzuordnung und unveränderte frühere Voice-Aufzeichnungen. Das Set enthält genau zwei neue Customer Updates. Die normalen Geschäftsregeln und die native Aktualisierung der Voice-Konfiguration blieben aktiv; kein lokaler Dienst oder Modell wurde neu gestartet.

Die native Serialisierung übersetzbarer Texte enthält in diesen Aufzeichnungen eine auf den jeweiligen Datensatz begrenzte Bereinigung von `sys_translated_text`. Für beide geänderten Nachrichten existierten keine Übersetzungszeilen. Diese erzeugten XML-Einträge wurden weder verändert noch auf eine andere Instanz angewendet; die Aufzeichnungen sind daher nicht als frei von eingebetteten Bereinigungsaktionen zu bezeichnen.

## Reproduzierter Gesprächsfehler

Der normale ServiceNow-Profil-Test reproduzierte die gemeldete Folge: statische Mitarbeiterfrage, einmalige synthetische Antwort „Testperson Sprachprüfung“, Verarbeitungsfehler, nicht verfügbarer Live-Agent und Abschluss. Die statische Begrüßung startet keinen Onboarding-Workflow. Eine bloße Namensantwort war deshalb an keinen Mitarbeiter-Eingabeschritt gebunden und gelangte in die allgemeine Suche.

Die native VA-Verarbeitung lief dabei unter dem ursprünglichen Benutzer. Für dieses Gespräch wurde jedoch kein AIA-Plan, Root→SCC-Aufruf oder zugeordnetes GenAI-/Werkzeugprotokoll gefunden. Die 37 Sekunden zwischen gespeicherter Eingabe und Fehler belegen keine Modell- oder Verbindungsaufbaulatenz. Leere Historie auf dem ersten Suchturn ist laut nativer Quelle beabsichtigt; gültige Suche ohne Treffer ist ebenfalls kein belegter Grund für den Verarbeitungsfehler. Tatsächlicher asynchroner Antwortstatus und Callback-Fehler bleiben unbekannt. Beide Testgespräche sind terminal; die vollständige Rücklesung ergab keine aktiven eigenen Gespräche.

## Verbleibende Abnahme

- Die lokale B2B-Voice-Strecke muss die ursprüngliche Benutzeridentität bis zum tatsächlichen AIA-Worker erhalten. Der vorherige V5-Lauf blieb dort `guest`.
- Der Verarbeitungsfehler der allgemeinen nativen Suche benötigt einen tatsächlichen Fehler- oder Callback-Nachweis; weitere Modell-, ACL- oder Suchkonfigurationsänderungen sind daraus bislang nicht begründet.
- Root→SCC→Halogen, gebundene Namensfortsetzung, Kontextfortschritt und begrenzter Gesprächsabbruch müssen gemeinsam nachgewiesen werden.
- Verbindungstiming, TURN/Relay und physisches Verhalten auf iPhone, Android und Computer bleiben gesondert zu prüfen.

Die vorbereiteten [Capability-Modellskripte](capability-model-management.md) bleiben unabhängig von diesen Punkten. Modell-, Skill-, Sprach- und Agent-Konfiguration bleiben getrennt und in ServiceNow verwaltet. Das bereits geladene Halogen und die eigene TTS-Stimme wurden erhalten.

Private Ausführungs- und Prüfnachweise liegen unter `server/.local/voice-repair-20261102/entry-workflow/native-profile-test-20261103/`, insbesondere `WELCOME-REPAIR-VERIFIED.json`. Die zwei öffentlichen Begrüßungsvergleiche starteten keine Voice-/CS-Sitzung und keinen Modelllauf. Ihre kurzzeitig nur im Speicher gehaltenen Tokens wurden jeweils beim Aussteller widerrufen und anschließend mit demselben Token durch HTTP 401 als ungültig bestätigt.
