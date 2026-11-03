# Voice-Reparatur: geprüfter Stand am 3. November 2026

Die vorzeitige Mitarbeiterfrage in der Begrüßung ist korrigiert. Beide tatsächlich verwendeten Begrüßungsquellen enthalten jetzt: **„Hallo und willkommen. Wie kann ich Ihnen helfen?“** Eine frische öffentliche Voice-Konfigurationsabfrage unter dem ursprünglichen Benutzer hat genau diesen Text bestätigt. Die vollständige Gesprächsreparatur ist weiterhin offen.

Die zusätzliche Prüfung der tatsächlichen Zugriffsausgaben hat die Ursache des
Workflow-Abbruchs weiter eingegrenzt: Der äußere Workflow durfte starten, sein
bisheriger Rollenfilter entzog aber die für den Aufruf des vorhandenen
SCC-Agenten erforderliche Admin-Rolle. Die freigegebene Korrektur ergänzt diese
Rolle ausschließlich im äußeren Workflow. Der fachliche Agent behält seine
beiden Datenrollen, seine bisherigen Aufrufregeln und die dynamische
Benutzerzuordnung. Die unabhängige Rücklesung bestätigt genau eine neue
Rollenzuordnung und deren native Änderungsaufzeichnung. Für den unveränderten
Konfigurationskopf entstand kein zusätzlicher persistierter Eintrag; der
ursprüngliche Prüfbericht mit seiner abweichenden Aufzeichnungserwartung bleibt
als Ausführungsnachweis erhalten. Die vollständige Gesprächsprüfung nach dieser
Korrektur steht noch aus.

Zusätzlich ist eine eng begrenzte lokale Browser-Anmeldungskorrektur aktiv
und unabhängig geprüft: Ein gültiger OAuth-Bearer muss kein JWT mit drei
Punktsegmenten sein. Der Sprachadapter akzeptiert künftig dieselbe begrenzte
ASCII-Schreibweise und lässt weiterhin ServiceNow die tatsächliche Berechtigung
prüfen. Elf gezielte Tests bestehen. Nur der Sprachadapter wurde neu geladen;
Modell, Erkennung und eigene Stimme wurden erhalten.

Der native gemeinsame Voice-Startbaustein ist ebenfalls korrigiert und durch
normales Speichern in einem eigenen Update Set aufgezeichnet. Er behandelt
`connected` und `completed` als erfolgreiche Verbindung, fängt asynchrone
Signalisierungs- und Wiedergabefehler ab und ordnet den optionalen Audiokontext
dem jeweiligen Anruf zu. Ein Fehler der optionalen Analyse darf funktionierende
Wiedergabe nicht beenden. Die produktive lokale Fassung besteht 26 portable
Regressionstests; native Rücklesung und genau eine passende XML-Aufzeichnung
sind geprüft. Der native Hilfsbaustein und die Ereigniszuordnung blieben
unverändert. Die Anpassung betrifft den gemeinsamen Test-Startbaustein, nicht
nur das SCC-Profil; physische Geräte sind damit noch nicht abgenommen.

Ein neuer synthetischer Anruf erreichte nach der Rollen-Korrektur die echte
SCC-Mitarbeiterfrage, las den erkannten Namen zurück und nahm genau ein Ja auf
diese Namensfrage an. Die Erkennung änderte dabei den künstlichen Testnamen
„Testperson“ zu „Testpersonen“; die Rücklesung bewahrte genau diese erkannte
Fassung. Der erste folgende ServiceNow-Text war eine Planer-Übergangsmeldung.
Der begrenzte Test endete danach sauber, bevor eine weitere Angabe oder eine
Bestellfreigabe gesendet wurde. Er belegt somit noch keine vollständige
Fortsetzung bis zur nächsten echten Fachfrage. Die tatsächlichen Modellläufe
sind erfolgreich auf Halogen; die Wartezeiten entstehen aus mehreren
nacheinander ausgeführten ServiceNow-Planungs- und Agentenschritten.

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

Der ursprüngliche Voice-OAuth-Token kann die öffentliche Konfiguration mit dem
richtigen Benutzer lesen. Eine zusätzliche native Leseabfrage war ebenfalls
erfolgreich. Der getrennt geprüfte Sitzungstest bestätigt jedoch keine
authentifizierte native Unterhaltung: Die Erstellung antwortete mit HTTP 200,
erfüllte die native Authentifizierungsbedingung aber nicht. Die vollständigen
Metadaten zeigten zwei neue Datensätze außerhalb der Eigentümerbeziehungen des
angemeldeten Benutzers. Seine eigenen aktiven oder unbekannten Gespräche
blieben bei null. Ein nachfolgender begrenzter Leseversuch zur genaueren
Eigentümerzuordnung wurde durch die geltenden Leserechte verweigert. Eine
tatsächliche Gastzuordnung und Aktivität auf diesen fremden Datensätzen sind
damit weiterhin unbekannt; die früher belegte Gast-Ausführung der B2B-Strecke
ist ein gesonderter Befund.

Dieser Test sendete keine Initialisierung, Texteingabe, Mikrofonaufnahme oder
Bestellung. Ohne bestätigte Eigentümerbindung wurde kein Gesprächsabbruch
erfunden. Der kurzzeitig im Speicher gehaltene Token wurde beim Aussteller
widerrufen (HTTP 200) und anschließend mit demselben Token durch HTTP 401 als
ungültig bestätigt. Die 1,63 Sekunden der nativen Erstellung und die zusätzlichen Metadatenlesezeiten
sind keine Messung des vollständigen Voice-Verbindungsaufbaus.

Ein erster Diagnoseversuch scheiterte bereits vor Token-Ausstellung und
Sitzungserstellung an einer zu früh geschlossenen Antwortverbindung im
Testprogramm. Die getrennte Korrektur besteht 86 gezielte Prüfungen mit echten,
an Abbruchsignale gebundenen Antwortströmen; ursprüngliche Dateien und beide
Laufergebnisse wurden erhalten. Das ändert keine laufende Voice-Komponente.
Die nächste Untersuchung betrifft die dokumentierte Provider-Kontoverknüpfung
und die Identitätsübergabe an den asynchronen Agentenlauf. Zusätzliche Rollen,
ACL-Regeln oder spekulative API-Freigaben wurden nicht angelegt.

- Die lokale B2B-Voice-Strecke muss die ursprüngliche Benutzeridentität bis zum tatsächlichen AIA-Worker erhalten. Der vorherige V5-Lauf blieb dort `guest`.
- Der Verarbeitungsfehler der allgemeinen nativen Suche benötigt einen tatsächlichen Fehler- oder Callback-Nachweis; weitere Modell-, ACL- oder Suchkonfigurationsänderungen sind daraus bislang nicht begründet.
- Root→SCC→Halogen, gebundene Namensfortsetzung, Kontextfortschritt und begrenzter Gesprächsabbruch müssen gemeinsam nachgewiesen werden.
- Verbindungstiming, TURN/Relay und physisches Verhalten auf iPhone, Android und Computer bleiben gesondert zu prüfen.

Die vorbereiteten [Capability-Modellskripte](capability-model-management.md) bleiben unabhängig von diesen Punkten. Modell-, Skill-, Sprach- und Agent-Konfiguration bleiben getrennt und in ServiceNow verwaltet. Das bereits geladene Halogen und die eigene TTS-Stimme wurden erhalten.

Private Ausführungs- und Prüfnachweise liegen unter `server/.local/voice-repair-20261102/entry-workflow/native-profile-test-20261103/`, insbesondere `WELCOME-REPAIR-VERIFIED.json`. Die zwei öffentlichen Begrüßungsvergleiche starteten keine Voice-/CS-Sitzung und keinen Modelllauf. Ihre kurzzeitig nur im Speicher gehaltenen Tokens wurden jeweils beim Aussteller widerrufen und anschließend mit demselben Token durch HTTP 401 als ungültig bestätigt.
