# Native SCC Demo: Betrieb auf DESKTOP-8M583SI

Stand: 13.10.2026. Diese Anleitung bedient den vorhandenen nativen ServiceNow-Stack.
Während eines Anrufs oder Tests keine Dienste neu starten.

**Wiederanlauf geprüft: 13.10.2026, 15:30:39 Uhr Berlin.** Alle sieben
Dienste antworteten mit HTTP 200; Modell, Gateway und nativer Adapter waren
frei. HaloGen läuft mit 262.144 Kontextpositionen und einem Slot. Freier
RAM: 30,235 GiB; die 18-GiB-Reserve bleibt aktiv. Alle acht Desktop-Verknüpfungen
wurden um 15:29:03 Uhr unabhängig zurückgelesen und stimmten mit den
vorgesehenen Befehlen bzw. der Demo-URL überein. Der erfolgreiche Gesamtstart
über das bereitgestellte Paket wurde durch die Nutzerausgabe um 15:26 Uhr
belegt. Der anschließende echte Mikrofontest ist jedoch fehlgeschlagen;
ein gesunder Dienstestatus ist keine Abnahme des Sprachdialogs.

**Mikrofontest vom 13.10., 15:30–15:35 Uhr Berlin:** Nach dem deutschen
Anliegen kam eine englische Zwischenansage, danach die deutsche Namensfrage.
Der gesprochene Vorname „Philipp“ wurde als „Hallo“ erkannt. Auf die erneute
Namensfrage antwortete der Nutzer „Philipp Borchert“; dafür erschien kein
Transkript. Belegt sind nur zwei ASR-Aufrufe. Der zweite ServiceNow-Turn
lieferte `OutputText`, aber keine neue `InputText`-Freigabe. Die bisherige
Bridge blockierte während dieses Wartens auch weitere ASR-Aufrufe und brach
später mit Timeout ab. Ob die dritte Aufnahme in der Warteschlange lag,
ist aus den damaligen Logs nicht feststellbar. Alle sechs untersuchten
Modellaufrufe liefen ohne Thinking und wurden mit HTTP 200 abgeschlossen.
Der korrigierte Adapter trennt Spracherkennung und Transkriptanzeige vom
serialisierten ServiceNow-Dialog. Beide Eingabewarteschlangen bleiben auf
zwei Einträge begrenzt; eine überfüllte Warteschlange wird angezeigt.
Bei Backendfehler werden ungesendete Antworten verworfen und eine deutsche
Abbruchmeldung ausgegeben, ohne eine Bestellung erneut zu senden. Lokale
Hinweise verwenden kein natives `error`-Ereignis, weil die ServiceNow-Testseite
dadurch sofort die Verbindung schließen würde. Die Korrektur ist seit
**16:05:21 Uhr Berlin aktiv**; nur der native Adapter wurde neu gestartet.
Der unabhängige Statuscheck um 16:06:09 Uhr bestätigte alle sieben Dienste,
keine aktive Native-Sitzung und denselben unveränderten Bot-Prozess.
Fehlende ServiceNow-Freigabe und englische Zwischenansage bleiben offen.

**Prüfung der Korrektur:** Der unabhängige Windows-Lauf bestand 43 Tests
einschließlich weiterlaufender ASR bei blockiertem Backend, Eingabegrenzen,
Unterbrechungen, Aufräumen und WebRTC-Transport. Der synthetische Vergleich um
16:01:25 Uhr Berlin erkannte „Philipp“, „Philipp Borchert“ und „Der Mitarbeiter
heißt Philipp Borchert.“ in beiden ASR-Ausgabeformaten identisch (250–328 ms
je ASR-Aufruf). Die neue Diagnostik erfasst nur begrenzte numerische
Segmentwerte und Transportphasen; sie speichert keine Mikrofonaufnahmen und
verändert keine Namen anhand vorgegebener Werte. Dies ersetzt keinen neuen
echten Mikrofontest und erklärt die frühere Erkennung als „Hallo“ nicht.

Der echte ServiceNow-Browser hat OAuth, Mikrofon, ASR und hörbare TTS-Antworten
bereits erfolgreich verwendet. Die einmalige lokale Begrüßung wird an den
Backend-Dialog übergeben; die Sitzungssprache ist Deutsch. Ein isolierter
Audio-Test beantwortete „Hallo“ damit auf Deutsch ohne zweite Begrüßung
(hörbar nach 6,239 s ab ASR). **Nach einem allgemeinen „Hallo“ fehlt weiterhin
das bestätigte Signal für die nächste Eingabe.** Für die Demo direkt das
Laptop-Anliegen sprechen, wie unten beschrieben.

Die Anweisungen beider SCC-Agenten (Chat und Voice) wurden in ServiceNow
gespeichert und unabhängig zurückgelesen: Deutsch verwenden und den
Mitarbeiternamen vor dem ersten Tool-Aufruf erfragen. Der anschließende echte
RTP-Audiotest erreichte die Namensfrage nach **33,077 s statt zuvor 52,400 s**
ab ASR; die echte Eingabebereitschaft wurde bestätigt. Eine englische
Zwischenansage nach 14,886 s bleibt offen. Alle drei Modellaufrufe dieses
Tests liefen **ohne Thinking**; allein das Einlesen der Prompts dauerte
insgesamt 19,31 s. Ein weiterer vollständiger Bestelltest nach der Änderung
wurde nicht durchgeführt.

Der frühere vollständige Audiotest bestätigte nach ausdrücklich gesprochener
Freigabe die vorhandenen **REQ0010012 / RITM0010011**; er erzeugte keine neue
Bestellung. Dieser ältere Nachweis ersetzt keine aktuelle Abnahme des gesamten
natürlichen Gesprächsablaufs. Details und Messwerte stehen in
[VALIDATION.json](../native-bridge/VALIDATION.json).

Vor dem Neustart des PCs hatte sich der Modelldienst wegen Unterschreitung
der 18-GiB-Speicherreserve beendet. Die vorgeschlagene Cache-Optimierung wurde
nicht aktiviert. Modell, bestehendes Profil und Speichergrenzen bleiben beim
Wiederanlauf unverändert. Der No-Thinking-Demomodus des Gateways setzt für
alle Aufrufe des öffentlichen Alias `halogen-v2` `enable_thinking=false` und
`reasoning_effort=none`; das betrifft auch andere Nutzer desselben Alias.

**Legacy `voice/Start-Voice.ps1` nicht verwenden:** Es startet die stillgelegten CPU-Modelle
auf 8851/8852 und kann die Speicherreserve von HaloGen aufbrauchen.

## Start auf der Messe

Auf dem Desktop liegt **SCC - Alles starten**. Nach einem Rechner-Neustart
per Doppelklick öffnen und das Fenster bis zur abschließenden Statusmeldung
offen lassen. Zuerst werden STT/TTS geladen, danach HaloGen mit seinem
bestehenden Speicherwächter und anschließend Gateway sowie Voice-Bridge.
Der Modell-Kaltstart braucht mehrere Minuten. Ein roter Fehler ist kein
bereiter Zustand; bei einer verbliebenen Modellsperre nicht wiederholt starten.

Die einzelnen Verknüpfungen sind ebenfalls verfügbar:

| Desktop-Verknüpfung | Zweck |
|---|---|
| SCC - HaloGen Modell | Modell starten; benötigte Sprachdienste vorher bereitstellen |
| SCC - Speech to Text | Whisper-Spracherkennung starten |
| SCC - Text to Speech | Qwen-Sprachausgabe und synthetische SCC-Stimme bereitstellen |
| SCC - Gateway | ServiceNow-Modell-Gateway im No-Thinking-Modus starten |
| SCC - Voice Bridge | Bot/Callback und nativen WebRTC-Adapter starten |
| SCC - Alles starten | Den gesamten Stack in der richtigen Reihenfolge starten |
| SCC - Status | Zustand anzeigen, ohne Gespräch oder Bestellung auszulösen |
| SCC - ServiceNow Voice Demo | Die native ServiceNow-Testseite im Browser öffnen |

Die Starter lassen korrekt laufende Dienste bestehen; sie starten nichts
vorsorglich neu und räumen keine Modellsperre automatisch weg. Das Schließen
des fertigen Startfensters ist kein Stop-Befehl für die gestarteten Dienste.
Startprotokolle liegen unter `voice\native-start\runtime`; Sprache und
Gateway führen zusätzlich ihre bestehenden Protokolle.

Die Startdateien liegen in `C:\Projects\strix-alloy-scc-voice\voice`:
`Start-NativeVoice.ps1` und `Install-NativeVoiceShortcuts.ps1`. Die zweite Datei
legt die Desktop-Verknüpfungen erneut an. Konfiguration und Schlüssel bleiben
in den vorhandenen lokalen Dateien; die Verknüpfungen enthalten keine Tokens.

## 1. Status ohne Nebenwirkungen

In PowerShell auf dem Windows-Demohost:

~~~powershell
$repo = 'C:\Projects\strix-alloy-scc-voice'
$clean = 'C:\Projects\strix-alloy-clean'
$corepy = "$clean\server\.local\venv\Scripts\python.exe"
$ops = "$repo\voice\native-speech-validation"
& $corepy -B "$ops\stack_status.py"
~~~

Das Skript fragt ausschließlich bekannte GET-Statusrouten, Listener, direkten
Windows-Speicher und die bestehende Funnel-Konfiguration ab. Keine Inferenz,
kein WebRTC-Connect, keine Bestellung, keine Session-Erzeugung, kein Start/Stop.
Tokens werden nur aus vorhandenen Dateien für lokale Health-Aufrufe gelesen
und niemals ausgegeben; Fehlertexte/Antwortkörper werden nicht durchgereicht.

Erwartet: `stack_healthy=true`, `legacy_cpu_ports=[]`.
Vor neuem Test zusätzlich `engine_idle`, `gateway_idle`, `native_idle` jeweils true.
Exitcode 0 bedeutet technisch gesund, **nicht automatisch anruffrei**.
Der Bot bietet keinen lesenden Session-Zähler; eine fremde oder unklar beendete
Bot-Session deshalb nicht durch Neustart beseitigen. `/api/session` nicht als
Health-Check benutzen: dieser GET kann eine neue Session belegen.

| Dienst | Loopback-Port | Erkennung |
|---|---:|---|
| HaloGen 0.18.1, full262/1 Slot | 8731 | authentifizierte Health, busy/in_flight/queued |
| Modell-Controller | 8840 | Health und aktive Requests |
| ServiceNow-LLM-Gateway | 8841 | Health, aktive und wartende Requests |
| Bot / Callback | 8850 / 8853 | Projektprozess; GET / liefert nur statische Seite |
| Nativer WebRTC-Adapter | 8860 | Health, nativeSessions, authMode=servicenow |
| Whisper Vulkan | 8861 | Health |
| Qwen3-TTS Vulkan | 8862 | Modell scc-native-qwen3 |

Die 18-GiB-Reserve für physischen Speicher **und** Commit bleibt unverändert.
Ein Kaltstart des bestehenden v2-Profils verlangt 35/131 GiB und zehn sichere
Sekunden. `cold_start_floor_met=false` ist bei bereits geladenem Modell normal;
es hebt einen gesunden laufenden Stack nicht auf. Niemals die Grenzwerte senken
oder einen verbliebenen runner.lock automatisch löschen.

## 2. Nur fehlende Dienste starten

Gesunde laufende Dienste bleiben laufen. Vor jedem Befehl im Status prüfen,
dass die zugehörigen Ports frei sind; bei fremdem Besitzer abbrechen.
Jede lange laufende direkte Python-Zeile gehört in ein eigenes PowerShell-Fenster
mit den Variablen aus Abschnitt 1. Keine automatischen Wiederholungen.

**Sprache zuerst**, damit HaloGens Admission den tatsächlichen Speicherbedarf sieht:

~~~powershell
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' "$ops\speech_probe.py" start
~~~

Nach einem TTS-Neustart die vorhandene synthetische SCC-Stimme einmal registrieren.
Das ist lokale Referenzregistrierung, keine Dialog- oder Bestellanfrage:

~~~powershell
$voiceDir = "$repo\voice\assets\scc-demo"
$v = Get-Content "$voiceDir\voice.json" -Raw -Encoding UTF8 | ConvertFrom-Json
$hash = (Get-FileHash "$voiceDir\reference.wav" -Algorithm SHA256).Hash.ToLower()
if ($v.kind -ne 'designed_synthetic_voice' -or $hash -ne $v.reference_sha256) { throw 'Voice reference mismatch' }
$body = @{name='scc-demo';ref_text=$v.reference_text;wav_b64=[Convert]::ToBase64String([IO.File]::ReadAllBytes("$voiceDir\reference.wav"))} | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:8862/v1/audio/voices' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
~~~

**HaloGen**, nur mit dem bestehenden geprüften Profil:

~~~powershell
$profile = "$clean\server\.local\optimization9h-20261004\halogen0172-backend-preparation-20261008\halogen0181-version-bracket-20261012\serving0181-full262-profile.json"
if ((Get-FileHash $profile).Hash.ToLower() -ne 'cf02e2e695160c3e199a2efbf81920192d77f538616b4a3a00153e33927333c4') { throw 'Profile changed' }
& $corepy -u -B "$clean\server\controller.py" run --config $profile
~~~

Auf READY warten; der Controller führt seine vorhandenen zwei harmlosen
Startprüfungen aus. Keine zusätzlichen Prompt-Probes parallel senden.

**Gateway, Bot, nativer Adapter**, jeweils nur wenn der Dienst fehlt:

~~~powershell
& "$repo\voice\Start-QueuedGateway.ps1" -Action Start -DemoNoThinking
# Eigenes Fenster:
& $corepy -u "$repo\voice\bridge.py" --config 'E:\SCC-Voice\bridge.json'
# Eigenes Fenster:
& "$repo\voice\native-bridge\.venv\Scripts\python.exe" -u "$repo\voice\native-bridge\native_bridge.py" --config "$repo\voice\native-bridge\config.example.json"
~~~

`config.example.json` ist hier die tatsächlich verwendete produktive
ServiceNow-Konfiguration, trotz des Dateinamens. Kein development_token,
kein `--probe-backend` für regulären Start. Keine Neuinstallation nötig.

Status erneut ausführen. Bestehende Funnel-Zuordnung:
`/ → 8841`, `/scc-native → 8860`, `/scc-voice → 8853`.
Das Skript verändert keine Route. Fehlende/falsche Route gezielt prüfen, nicht
die gesamte Funnel-Konfiguration ersetzen. HTTPS/WSS beweist keine UDP-Verbindung:
der echte Browser muss einen Host-ICE-Kandidaten über LAN/Tailnet erreichen.

## 3. Geordnet beenden

1. Im nativen ServiceNow-Client den Anruf beenden und die Freigabe abwarten.
   Keine zweite Sitzung starten. Bei unklarem Bestell-/Callback-Status warten
   und den laufenden Vorgang klären; einen Neustart nicht als Abbruch benutzen.
2. Status ausführen: Engine und Gateway leer, nativeSessions=0. Die Bot-Session
   muss dem Betreiber bekannt und sauber beendet sein; das Skript beweist das
   für einen fremden Client nicht.
3. Die **eigenen Vordergrundfenster** in dieser Reihenfolge mit Ctrl+C schließen:
   nativer Adapter, Bot. Keine gespeicherten historischen PID-Nummern
   und kein taskkill nach Prozessname verwenden. Gateway anschließend mit seinem
   Besitzer-prüfenden Launcher stoppen; dessen Stop ist nicht selbst drainend,
   daher nur nach dem eben bestätigten Idle-Zustand:

~~~powershell
& "$repo\voice\Start-QueuedGateway.ps1" -Action Stop
~~~

4. HaloGen über seinen Controller geordnet stoppen und STOPPED/Recovery abwarten:

~~~powershell
& $corepy -B "$clean\server\controller.py" stop
& $corepy -B "$clean\server\controller.py" status
~~~

5. Anschließend die vom Sprach-Launcher besessenen Prozesse stoppen:

~~~powershell
& 'E:\SCC-Voice\asr-env\Scripts\python.exe' "$ops\speech_probe.py" stop
& $corepy -B "$ops\stack_status.py"
~~~

Der Sprach-Stop prüft PID, Startzeit, Executable und Argumente. Für die aktuell
im Hintergrund gestarteten Bot-/Native-/Gateway-Prozesse gilt: erst aktuelle
Listener-PID, vollständigen Projektpfad, Konfiguration und Startzeit prüfen;
keinen alten einmaligen `runtime/restart_owned.ps1` erneut ausführen.
Bei unklarer Prozess- oder Session-Zuordnung den betreffenden Dienst laufen
lassen. Funnel darf unverändert bleiben; es wird hier nicht global abgeschaltet.

## No-Thinking-Modus zurücknehmen

Nur nach beendetem Anruf und erneut bestätigtem Engine-/Gateway-/Native-Idle:

~~~powershell
& "$repo\voice\Start-QueuedGateway.ps1" -Action Stop
& "$repo\voice\Start-QueuedGateway.ps1" -Action Start
~~~

Ohne Schalter ist der Override aus. Mit `-DemoNoThinking` ist er an. Der Launcher
verweigert einen abweichenden Modus bei bereits laufendem Gateway; die laufende
Konfigurationsdatei nicht von Hand umschreiben. Dieser Wechsel startet nur 8841
neu, weder HaloGen noch Audio/Bot/Native/Funnel. Details und lokale Vertragstests:
[HALOGEN-DEMO-MODE.md](../HALOGEN-DEMO-MODE.md).

## Nativen Browser-Test durchführen

Auf dem Demorechner oder einem Browser mit Verbindung in dasselbe erreichbare
LAN/Tailnet anmelden und den echten ServiceNow-Test öffnen:

[Native Test Assistant öffnen](https://soprasteriaassvsdemo14.service-now.com/now/now-assist-with-va/voice-test/8aa131d793f787105c8132d47aba1095)

Mikrofonzugriff für diese ServiceNow-Seite **zulassen**, passendes Eingabegerät
wählen und **Start call** drücken. Der Browser muss einen Host-ICE-Kandidaten
des PCs erreichen (LAN `192.168.50.19` oder Tailnet `100.103.94.78`).
Das öffentliche HTTPS-Funnel allein stellt keinen UDP-Medienpfad bereit;
STUN/TURN ist nicht konfiguriert. Bei blockiertem Mikrofon keine erfolgreiche
native Verbindung behaupten und nicht blind weitere Anrufe starten.

Für das bereits geprüfte Laptop-Szenario direkt das Anliegen sprechen und
jeweils die vollständige Rückfrage abwarten. Eine allgemeine Begrüßung kann
aktuell zwar beantwortet werden, lässt den Bot aber ohne bestätigte Bereitschaft
für das Folgeanliegen zurück. In diesem Zustand nicht weiterreden oder parallel
einen neuen Anruf starten; den eigenen Anruf geordnet beenden. Dieser gezielte
Testablauf bedeutet keine Freigabe des noch fehlerhaften natürlichen Dialogs:

1. **Anliegen:** „Mein neuer Mitarbeiter startet am 1. November, sein Laptop
   soll zum Onboarding nach Hamburg in unsere Niederlassung geliefert werden.“
2. **Auf die Namensfrage:** „Der Mitarbeiter heißt Alex Sommer.“
3. **Erst nach Prüfung der gesprochenen Zusammenfassung:** „Ja, bitte bestelle
   den Laptop.“

Im geprüften Lauf betraf die Zusammenfassung Alex Sommer, den 1. November 2026,
Hamburg und den vorhandenen Vorgesetzten. Bei abweichenden Angaben korrigieren;
die Bestätigung nicht überspringen. Der vorige Lauf fand die existierende
REQ/RITM wieder; das ist keine pauschale Garantie für weitere Bestellversuche.
Anruf beenden, Freigabe abwarten und eine neue Unterhaltung getrennt prüfen.
