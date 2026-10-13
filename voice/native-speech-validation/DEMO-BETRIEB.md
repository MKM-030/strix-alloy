# Native SCC Demo: Betrieb auf DESKTOP-8M583SI

Stand: 13.10.2026. Diese Anleitung bedient den vorhandenen Stack. Sie ist kein
neuer externer Voice-Client. Während eines Anrufs oder Tests keine Dienste neu starten.
Die technische Statusprobe ist keine native End-to-End-Abnahme: echter
Mikrofonzugriff und realer ServiceNow-OAuth-Aufruf sind noch nicht nachgewiesen;
eine vollständige Sprachbestellung ist noch offen. Der bisherige isolierte
First-Turn-Audiotest erreichte die vollständige Frage nach etwa 113 Sekunden.
Seit 10:32:10 UTC ist der reversible No-Thinking-Demomodus auf Gateway 8841
aktiv. Er setzt für alle Chat-Aufrufe des öffentlichen Alias halogen-v2
`enable_thinking=false` und `reasoning_effort=none`. Modell, Kontext, Memory
Guard, Tools und Bestätigungslogik bleiben unverändert. Das betrifft alle
Caller dieses Alias; neue Latenz- und vollständige Abnahmeergebnisse stehen aus.
**Legacy `voice/Start-Voice.ps1` nicht verwenden:** Es startet die stillgelegten CPU-Modelle
auf 8851/8852 und kann die Speicherreserve von HaloGen aufbrauchen.

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

Geprüfter Status nach dem isolierten Audiotest um 10:25:20 UTC: alle sieben
Health-Abfragen HTTP 200, Modell/Gateway/Native idle, 26.954 GiB freier RAM,
120.072 GiB Commit-Reserve, keine Legacy-CPU-Listener. Das ist eine Statusprobe,
keine Zusage zur gesamten Dialoglatenz oder zur Erreichbarkeit fremder Browser.

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
