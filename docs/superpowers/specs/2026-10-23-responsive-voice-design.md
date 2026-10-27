# Ansprechbarer Voice Assistant bei laufender Agentenarbeit

**Ausgangsentwurf vom 23.10.2026 · Ansatz inzwischen zur Umsetzung beauftragt. Verbindliche Konkretisierung: [responsive-voice-implementation-design](2026-10-23-responsive-voice-implementation-design.md).**

Dieses Dokument hält den ursprünglichen Architekturvorschlag fest. Der Nutzer hat anschließend den Ansatz, die vertiefte Planung und vollständige Umsetzung beauftragt und die Modellwahl delegiert. Die verlinkte Konkretisierung ersetzt abweichende Freigabe- und Umfangsaussagen dieses Ausgangsentwurfs. Aktivierung wird durch separate Laufzeitnachweise belegt.

## Ziel und bestehender Betrieb

Während ein ServiceNow-Agent arbeitet, soll der Anrufer weiter Fragen stellen, Angaben ergänzen und zwischen Anliegen wechseln können. Die Gesprächsschicht soll unmittelbar zuhören und verständlich reagieren. Ein Orchestrator ordnet neue Aussagen dem passenden Anliegen und Agenten zu. Fachliche Ergebnisse und ausgeführte Aktionen bleiben durch ServiceNow belegt.

Die aktuelle Reparatur der Geräuscherkennung ist davon getrennt: Ein lokal qualifizierter Silero-Sprachdetektor soll den bisherigen Pegelentscheid ersetzen. Whisper, TTS und Gemma bleiben dabei erhalten. Ein besserer Sprachdetektor allein führt noch keine asynchrone Gesprächsführung ein.

Als ersten Umfang für Ansatz A schlagen wir den bestehenden Laptop-Workflow mit Statusfragen, Verständnisfragen und Ergänzungen zum laufenden Anliegen vor. Der Routingvertrag bleibt für weitere Agenten erweiterbar. Zusätzliche schreibende Agenten folgen erst nach einer ausdrücklichen Auswahl aus dem zugelassenen Agentenkatalog. Dieser Umfang ist unser Vorschlag und noch keine Nutzerentscheidung.

Heute bestehen bereits parallele Audiopfade, aber ein serieller fachlicher Dialog:

- `voice/native-bridge/native_bridge.py`, `NativeCall.microphone()` und `recognize_turns()`: Mikrofon und Erkennung laufen unabhängig von der fachlichen Antwort. Die Audio- und Textwarteschlangen sind jeweils auf zwei Einträge begrenzt.
- `NativeCall.process_turns()` wartet auf `Dialog.turn()`. `Dialog.turn()` wartet auf ServiceNow-Callbacks und ruft die Sprachausgabe auf. Eine weitere erkannte Aussage erhält währenddessen keine eigene dialogische Antwort.
- `voice/bridge.py`, `Bridge.message()`: `session.busy` verhindert überlappende Nachrichten in derselben ServiceNow-Unterhaltung. `Bridge.callback()` bindet Antworten an Sitzung und letzte Request-ID und verwirft doppelte Callback-Inhalte. Diese Schutzmechanismen dürfen nicht durch parallele `dialog.turn()`-Aufrufe umgangen werden.
- Barge-in verwirft die aktuelle Audiogeneration; es storniert keine bereits eingereichte fachliche Aktion. Der bestehende Pfad beobachtet deren Ergebnis weiter.
- `voice/native-start/gateway_profile.py`, `load_native_profile()`, und das aktive Gemma-Profil erzwingen eine qualifizierte Kapazität von **einer** Modellanfrage, mindestens 18 GiB Speicherreserve und `--parallel 1`. Beobachtete fachliche Turns können 60–150 Sekunden dauern. Eine zusätzliche Warteschlange vor demselben belegten Modell ermöglicht deshalb noch kein flüssiges Rückfragen.

Gleichzeitiger Audiotransport, Unterbrechung der Wiedergabe, schrittweise Ausgabe und weiter ansprechbare fachliche Gesprächsführung sind getrennte Fähigkeiten. Alle vier müssen einzeln geprüft werden.

## Ansätze und Empfehlung

| Ansatz | Ausgestaltung | Nutzen und Abwägung |
| --- | --- | --- |
| **A: Separate schnelle Gesprächsschicht mit vorhandenem STT/TTS** | Ein Gesprächsmanager verarbeitet Sprache, Kontext und Rückfragen unabhängig von den ServiceNow-Aufgaben. Bestehendes Gemma bleibt die fachliche Engine. Ein zentraler Taskvertrag verbindet beide Seiten. | Kleinerer Eingriff in den funktionierenden Medien- und Fachpfad; gut messbare Erkennungsqualität und kontrollierbare Aktionen. Benötigt eine gesondert qualifizierte schnelle Textinferenz und saubere Zustandsführung. |
| **B: Audio-natives Duplex-Frontend** | Ein geeignetes Echtzeit-Audiomodell übernimmt die Gesprächsschicht. Derselbe Taskvertrag bindet unverändert die ServiceNow-Fachausführung an. Qwen3-Omni ist ein möglicher Kandidat für einen Vergleich. | Kann natürliches Überlappen und Turn-Verhalten verbessern. Größerer Wechsel von Audioverarbeitung, Kontext und Laufzeit; Deutsch, Geräusche, Tool-Rückgaben und Hardware müssen gemeinsam qualifiziert werden. |

**Unsere Empfehlung ist A**, danach ein Vergleichsversuch für B hinter derselben Schnittstelle. Ein doppelter fachlicher Ausführungsweg wird bei keinem Ansatz eingeführt. Es wird kein Erfolg durch eine Modellumbenennung oder durch das Entfernen von `busy` erwartet.

Die Gesprächsinferenz braucht während eines langen Gemma-Turns tatsächlich verfügbare Rechenzeit: beispielsweise ein kleines separat qualifiziertes Modell auf geeigneter CPU/GPU oder ein nachgewiesen reservierter beziehungsweise kontrolliert unterbrechbarer Inferenzslot. Zuerst wird eine lokale Lösung qualifiziert; ein externer Modellanbieter ist damit nicht ausgewählt oder beauftragt. Die vorhandene Gemma-Konfiguration wird dafür nicht blind auf mehr Parallelität oder einen anderen Kontext umgestellt. Vor einer Auswahl werden Speicherreserve, gleichzeitige Last, deutsche Dialogqualität und Antwortzeit gemessen. Ohne verfügbare Inferenz darf eine deterministische Statusantwort ehrlich den bekannten Aufgabenstand nennen; sie darf keine kontextuelle Antwortfähigkeit vortäuschen.

Qwen3-Omni unterstützt laut Hersteller deutsche Spracheingabe und -ausgabe. vLLM-Omni dokumentiert eine Duplex-Konfiguration, verlangt aber eine Prüfung der tatsächlich gemeldeten Laufzeitfähigkeiten. Die Tool-Referenz erklärt ausdrücklich, dass generische Tool-Verwaltung keinen Nachweis funktionierender Qwen-Tool-Rückgaben liefert. vLLM-Omni unterstützt Windows nativ nicht; seine ROCm-Anleitung nennt Linux und eine Validierung auf gfx942/MI300. Upstream-vLLM nennt zwar Ryzen AI MAX/gfx1151, daraus folgt keine Qualifikation des vollständigen Qwen-Duplex-Pfads auf diesem Windows/AMD-Rechner. Ansatz B benötigt deshalb einen getrennten Linux-/WSL- oder geeigneten Remote-Versuch.

## Vorgeschlagene Komponenten und Aufgabenvertrag

Der bestehende native Anruf transportiert weiter Mikrofon und Wiedergabe. Ein Gesprächsmanager besitzt den gehörten Gesprächsverlauf und die aktuelle Aufmerksamkeit des Anrufers. Er führt ausschließlich schnelle Gesprächsentscheidungen aus. Ein Taskkoordinator besitzt den verbindlichen Aufgabenstatus und beauftragt die zugelassenen ServiceNow-Agenten. Ergebnisse fließen als korrelierte Ereignisse zurück. Nur die vorhandene ServiceNow-Ausführung darf fachliche Änderungen durchführen.

Ein Task enthält mindestens:

| Feldgruppe | Bedeutung |
| --- | --- |
| `conversation_id`, Anrufgeneration, authentisierter Kontext | Bindung an die richtige Unterhaltung und ihre zulässige Identität |
| `task_id`, `parent_task_id`, Anliegen, `agent_id` | Dauerhafte Agentenzuordnung; unabhängige Anliegen besitzen getrennte Tasks |
| Ursprungsnachricht, `context_version`, geordnete Ergänzungen | Herkunft und Version der Fakten, mit denen ein Agent arbeitet |
| `operation_id`, stabiler Ausführungsschlüssel, ServiceNow-Request-/Ausführungs-ID | Zuordnung und Schutz vor doppelter fachlicher Ausführung |
| Status, Ergebnisversion, Zeitpunkte, belegte Ergebnisreferenz | Wahrheitsgemäßer Fortschritt und einmalige Ergebnisübernahme |

Mögliche Zustände sind `queued`, `running`, `awaiting_input`, `ready_to_commit`, `committing`, `succeeded`, `failed`, `cancel_requested`, `cancelled` und `outcome_unknown`. Audioende oder Verbindungsabbruch sind keine fachlichen Erfolgs- oder Stornierungsnachweise. Ein Zeitlimit beendet das Warten auf eine Antwort, ohne ein unbekanntes Ausführungsergebnis zu erfinden.

Der Orchestrator unterscheidet eine Status-/Verständnisfrage, eine Ergänzung zu einem laufenden Task, ein neues Anliegen und einen Steuerwunsch. Bei „doch erst am ersten November“ wird anhand der offenen Frage und der Taskzuordnung das Eintrittsdatum ergänzt. Bei mehrdeutigem Bezug fragt die Gesprächsschicht nach. Sie sendet dieselbe Aussage nicht vorsorglich an mehrere Agenten. Fachliche Datenzugriffe behalten ihre bestehenden Rechte; ein Voice-Login erzeugt keine zusätzliche Benutzerimpersonation.

## Ergänzungen, Antworten und Unterbrechung

Agenten erhalten Ergänzungen an einem ausdrücklich unterstützten sicheren Verarbeitungspunkt. Ein bereits vorbereiteter Modellaufruf wird nicht nachträglich als geändert dargestellt. Unterstützt der ServiceNow-Pfad keine Live-Nachricht an eine laufende Ausführung, bleibt die Ergänzung geordnet im Task und wird vor dem nächsten fachlichen Schritt zugestellt. Vor der Integration ist eine unterstützte Fortsetzungs-/Eingabeschnittstelle samt sicherem Verarbeitungspunkt zu qualifizieren. Die heutige VA-Bridge bietet diese bei `busy` nicht.

Vor einer schreibenden Aktion prüft der autoritative Ausführer die aktuelle Taskversion. Eine zwischenzeitliche relevante Korrektur verhindert die Freigabe einer veralteten Vorbereitung. Sobald eine Aktion verbindlich eingereicht ist, wird sie nicht heimlich mit neuen Angaben überschrieben. Die Gesprächsschicht erklärt dann den bestätigten Stand und veranlasst gegebenenfalls einen eigenen Änderungs- oder Stornierungsvorgang.

Späte Ergebnisse werden mit Task, Ausführungs-ID und Kontextversion abgeglichen. Sie dürfen nie eine inzwischen andere Frage beantworten oder einem anderen Anruf zugeordnet werden. Ein altes Ergebnis wird als solches eingeordnet; ein tatsächlicher fachlicher Erfolg wird weiterhin dokumentiert. Die Gesprächsschicht darf aus einem geplanten Schritt keinen abgeschlossenen Schritt machen.

„Hör auf zu sprechen“ stoppt ausschließlich die aktuelle Ausgabe. „Brich die Bestellung ab“ erzeugt einen fachlichen Stornierungswunsch. Bei noch nicht eingereichter Aktion kann die Freigabe zurückgenommen werden; nach Einreichung ist Stornierung nur mit belegter Unterstützung des Fachsystems erfolgreich. Unklare Übertragungen werden anhand vorhandener Ausführungsreferenzen geklärt und nicht blind wiederholt. Für Wiederholungen muss der Ausführungsschlüssel am autoritativen schreibenden Endpunkt wirksam sein.

Die Gesprächsschicht führt getrennt, was erzeugt, gesendet und tatsächlich abgespielt wurde. Unterbrochene Aussagen dürfen im Modellkontext nicht vollständig als gehört gelten. Ohne verlässliche Wiedergabebestätigung wird der Verlauf konservativ gekürzt oder bei Bedarf nachgefragt.

## Isolation, Ende und Wiederaufnahme

Jeder Anruf erhält eigene Audio-, Kontext- und Taskzuordnungen. Callbacks prüfen zusätzlich zur Authentisierung die vollständige Zuordnung. Das Beenden des Anrufs stoppt neue Eingaben und Audio. Bereits eingereichte Facharbeit wird wie im bestehenden Pfad bis zum geklärten Ergebnis weiter beobachtet; sie darf nicht in einen späteren Anruf hineinsprechen. Externe Benachrichtigungen sind nicht vorgesehen. Eine Wiederaufnahme nach Transportverlust braucht authentisierte Sitzung, Generation und Ereigniscursor. Fachliche Tasks werden dabei wiedergefunden und nicht erneut gestartet. Ohne belegte Wiederaufnahmeschnittstelle beginnt ein neuer Anruf getrennt.

## Abnahmekriterien und Einführung

Die folgenden Zeiten sind **ungeprüfte Abnahmeziele**, keine Aussage über den heutigen Betrieb: Von verfügbarer finaler ASR-Transkription bis zum ersten hörbaren Antwortaudio im Normalfall unter 1 Sekunde und unter definierter gleichzeitiger Fachlast im 95. Perzentil unter 2 Sekunden. Für Unterbrechungen gilt als Ziel: vom verifizierten Beginn tatsächlicher Sprache bis zum hörbaren Stoppen der Ausgabe unter 300 ms. Lange Fachaufgaben dürfen diese Gesprächsziele nicht blockieren.

Zusätzlich werden die Abschnitte letztes gesprochenes Wort → erkanntes Turnende, Turnende → finales ASR-Ergebnis und ASR-Ergebnis → hörbares Audio sowie die gesamte Antwortzeit getrennt ausgewiesen. Das aktuelle Endpointing wartet auf etwa 1,2 Sekunden Stille; mit dieser Einstellung wird keine Antwort unter 1 Sekunde ab dem letzten gesprochenen Wort behauptet. Erkennungsfehler bei Namen, Daten und kurzen Antworten sowie fälschliche Unterbrechungen werden separat gegenüber dem reparierten Ausgangspfad gemessen.

Verbindliche Tests umfassen: Rückfrage während eines langen Gemma-Turns; mehrdeutige Ergänzung; Themenwechsel und Rückkehr; Korrektur unmittelbar vor und nach der Einreichung; doppelte und vertauschte Callbacks; unbekannte Übertragung; Geräusch ohne Sprache; leise/kurze deutsche Antworten; beabsichtigte Unterbrechung; Gesprächsabbruch und zweiter Anruf; Verbindungsverlust und Wiederaufnahme; gleichzeitige Modelllast ohne Verlust der Speicherreserve. Fachliche Schreibtests erfolgen zunächst mit simulierten Ausführern, danach in einem ausdrücklich geeigneten Testkontext.

Nach einer Architekturentscheidung und Freigabe dieses Entwurfs folgt erst ein Umsetzungsplan. Die Einführung erfolgt zunächst mit aufgezeichneten beziehungsweise synthetischen Ereignissen und simulierten Fachaktionen, dann mit lesenden Aufgaben, anschließend begrenzt im nativen Testanruf. Schreibende Aktionen werden erst nach belegter Deduplizierung, Versionsprüfung und Stornierungssemantik zugelassen. Rollback schaltet die neue Gesprächsschicht ab und stellt den qualifizierten bestehenden Dialogpfad wieder her; laufende Tasks bleiben im Ledger bis zur Ergebnisaufklärung erhalten und werden nicht neu eingereicht.

## Offene Entscheidungen

Noch zu entscheiden beziehungsweise zu belegen sind: Ansatz A oder B; die verfügbare schnelle Gesprächsinferenz und ihr Rechenort; die unterstützte ServiceNow-Schnittstelle für Taskstart, sichere Ergänzung und Rückfrage; das Verhalten fortlaufender Facharbeit nach Anrufende; eine unterstützte Wiedergabebestätigung des mobilen Clients; die verbindliche deutsche Testmenge und Last für die Zeitziele. Diese Punkte sind keine bereits getroffenen Nutzerentscheidungen.

## Primärquellen

- [ServiceNow: Voice Assistant konfigurieren](https://www.servicenow.com/docs/r/intelligent-experiences/create-an-ai-voice-service.html) – unter anderem Geräuschunterdrückung und Anrufgrenzen; keine Zusicherung einer audio-nativen Duplex-Architektur.
- [ServiceNow: Voice-FAQ eines ServiceNow-Mitarbeiters](https://www.servicenow.com/community/servicenow-otto-articles/ai-voice-agents-are-here-autonomous-service-that-delights/ta-p/3448126) – Voice Orchestrator und getrennte Voice-/Chat-Laufzeiten.
- [ServiceNow: Voice-Modellkarten](https://downloads.docs.servicenow.com/resource/enus/infocard/sn-voice.pdf) – getrennte STT-/TTS-Komponenten. Die Karten sind kein Beleg für den konkreten lokalen Adapter.
- [Qwen: Qwen3-Omni](https://github.com/QwenLM/Qwen3-Omni) – Sprachunterstützung und Echtzeitausgabe.
- [vLLM-Omni: Duplex-Übersicht](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/full_duplex_api/) und [Protokollreferenz](https://docs.vllm.ai/projects/vllm-omni/en/latest/serving/realtime_duplex_api/) – Fähigkeiten, Wiedergabe und modellabhängige Tool-Grenzen.
- [vLLM-Omni: GPU-/Betriebssystemanforderungen](https://docs.vllm.ai/projects/vllm-omni/en/latest/getting_started/installation/gpu/) und [vLLM: GPU-Anforderungen](https://docs.vllm.ai/en/latest/getting_started/installation/gpu/) – Windows-/AMD-Abgrenzung.

Quellenstand: 23.10.2026. Veröffentlichte Fähigkeiten ersetzen die Qualifikation der gewählten Modell-, Laufzeit- und Hardwarekombination nicht.
