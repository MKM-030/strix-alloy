# Eigene Stimme fuer die SCC-Demo

Auf dem Windows-Desktop liegt **SCC - Eigene Stimme aufnehmen**. Ein Doppelklick
oeffnet das PowerShell-Werkzeug. Die Aufnahme beginnt erst, wenn die Person ihre
eigene Stimme bestaetigt, ein Mikrofon gewaehlt und den Start ausgelöst hat.

1. Zwischen Demo-Anrufen starten; waehrend der Aktivierung keinen Anruf beginnen.
2. `JA` zur Aufnahme der eigenen Stimme eingeben. Mikrofon-ID waehlen; Enter
   verwendet das Windows-Standardmikrofon.
3. Den angezeigten deutschen Text in etwa 25 Sekunden natuerlich vorlesen.
   Nach Enter folgt ein Countdown. ESC bricht die Aufnahme ab.
4. Aufnahme anhoeren. `P` spielt sie erneut ab, `R` nimmt sie neu auf,
   `A` verwirft sie. Leise, kurze, uebersteuerte oder beschaedigte Aufnahmen
   werden bereits vor diesem Schritt abgewiesen.
5. Abweichungen vom angezeigten Text als genauen gesprochenen Wortlaut eingeben.
6. `AKTIVIEREN` bestaetigt Aufnahme, Text und den Wechsel. Der naechste
   ServiceNow-Demo-Anruf verwendet das Profil unter der bestehenden `scc-demo`-Stimme.

Das Werkzeug verwendet Windows `winmm.dll`, Mono mit 24 kHz und PCM16. Es
installiert keine Aufnahmebibliothek. Der Aktivierungshelfer prueft und registriert
die Referenz beim bereits laufenden TTS-Dienst. Die Aufnahmephase startet oder
stoppt keinen Dienst. Abbruch vor der Aktivierung aendert kein Sprachprofil.
Bei einer fehlgeschlagenen Aktivierung beschreibt der Helfer, ob die vorherige
Stimme wiederhergestellt wurde oder ob der Dienststatus geprueft werden muss.

Die eigene Stimme ist ein synthetisches Modell der Aufnahme; Klang und Aussprache
koennen vom Original abweichen. Die Wiedergabe prueft die Mikrofonaufnahme. Sie
erzeugt keine TTS-Probe. Der Operator hoert das synthetische Ergebnis im naechsten
Demo-Anruf.

Aufnahmen und Einwilligungsdaten werden in `runtime/` abgelegt, das Git ignoriert.
Abbruch oder Neuaufnahme vor der Aktivierung loescht den verworfenen Versuch.
Eine fehlgeschlagene Aktivierung behaelt die Referenz zur Fehleranalyse. Erfolgreiche
Profile liegen zusätzlich in den privaten Revisionen des Aktivierungshelfers.

## Einrichtung und Diagnose

```powershell
& .\voice\voice-profile\Install-VoiceRecorderShortcut.ps1
& .\voice\voice-profile\Record-OwnVoice.ps1 -Check
& .\voice\voice-profile\Record-OwnVoice.ps1 -ListDevices
& .\voice\voice-profile\Test-VoiceRecorder.ps1
```

`-Check`, `-ListDevices` und die Tests nehmen nichts auf und erzeugen keine
synthetische Sprache. Die Tests kompilieren den echten Windows-Audiocode,
analysieren WAV-Pruefdateien und pruefen Prozessfehler und Zeitlimits mit einem
lokalen Testhelfer. Der Aufnahmepfad braucht einen operatorgesteuerten Mikrofontest.

`-DurationSeconds` erlaubt 15 bis 30 Sekunden. `-DeviceId 0` waehlt die angezeigte
Mikrofon-ID, `-DeviceId -1` das Windows-Standardmikrofon. Als Python wird bevorzugt
die vorhandene `E:\SCC-Voice\asr-env\Scripts\python.exe` verwendet. Mit
`-PythonExecutable` kann ein anderes vorhandenes Python mit den Helferabhaengigkeiten
gewaehlt werden. Keine Pakete werden automatisch installiert.

Wenn kein Ton ankommt: Windows-Eingabegeraet und Eingangspegel pruefen und unter
**Datenschutz und Sicherheit > Mikrofon** den Zugriff fuer Desktop-Apps erlauben.
