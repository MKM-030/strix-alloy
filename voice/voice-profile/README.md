# Eigene deutsche synthetische Stimme

Die Laptopdemo verwendet die bereits installierte native Qwen3-TTS-Base-Engine auf `127.0.0.1:8862`. `--lang German` legt Deutsch serverseitig fest. Die API akzeptiert keinen Sprachparameter pro Syntheseanfrage. Die unveränderte Voice-ID `scc-demo` bezeichnet die aktivierte Stimme; Bot- und native Bridge verwenden dadurch dieselbe Referenz.

`manage_voice.py` lädt keine Modelle und startet oder stoppt keine Dienste. `stage` prüft Zustimmung, WAV, Signal und Transkript und legt eine neue unveränderliche Revision an. `activate` registriert sie über die native `/v1/audio/voices`-API und schreibt anschließend `runtime/profiles/active.json` atomar. Das native Backend ersetzt die alte Referenz erst nach vollständiger Extraktion unter seinem Voice-Lock. Bei einer abgelehnten Registrierung bleibt die alte Referenz erhalten. Bei einem mehrdeutigen Netzwerkfehler oder Fehler beim Speichern registriert der Helfer die vorherige validierte Referenz erneut; scheitert auch die Wiederherstellung, meldet er ausdrücklich einen unklaren Zustand. Alte Aufnahmen und Revisionen bleiben erhalten.

Der normale TTS-Start stellt die aktive Referenz wieder her. Stimmenwechsel und Startregistrierung verwenden denselben Dateilock. WAV-Dateien, Zustimmungsmanifest, Profile und generierte Hörproben liegen ausschließlich im ignorierten `runtime/`-Verzeichnis. Die bestehende synthetische SCC-Referenz bleibt als Rückweg verfügbar.

## Recorder-Schnittstelle

```powershell
E:\SCC-Voice\asr-env\Scripts\python.exe voice\voice-profile\manage_voice.py activate --request <request.json> --json
```

Die vorhandene ASR-Pythonumgebung enthält `psutil` für die Prozessidentitätsprüfung. Die native Bridge-Pythonumgebung enthält diese Abhängigkeit nicht. Aktivierung nutzt die vorhandene TTS/GPU-Engine und soll zwischen Gesprächen und Benchmarks erfolgen. Ein aufrufender Recorder wartet bis zum Prozessende, maximal 300 Sekunden, und prüft Exitcode 0 sowie `ok: true` und `active_voice: "scc-demo"`.

```json
{
  "wav_path": "C:\\Pfad\\reference.wav",
  "reference_text": "Die tatsächlich gesprochenen deutschen Wörter.",
  "name": "Meine Stimme",
  "language": "German",
  "source": "desktop_microphone",
  "consent": {
    "own_voice": true,
    "confirmed_at_utc": "2026-10-13T16:00:00Z",
    "scope": "local_synthetic_voice_and_servicenow_demo"
  }
}
```

Alternativer freigegebener Ursprung: `authorized_existing_own_recording`. Unterstützt werden 3–30 Sekunden PCM16-WAV mit einem oder zwei Kanälen und 8–48 kHz. Stille, sehr leise oder übersteuerte Referenzen werden zurückgewiesen. Bestehende Stereoaufnahmen werden als Mono mit 24 kHz normalisiert, ihre Originalbytes und SHA256 bleiben in der Revision erhalten. Neue Recorderaufnahmen sind bereits Mono/24 kHz. Ein exaktes Transkript verbessert die ICL-Stimmnachbildung.

Weitere Befehle: `stage --request … --json`, `activate --profile-dir … --json`, `status --json`, `restore-synthetic --json`. Der letzte Befehl verwendet die erhaltene synthetische SCC-Referenz und muss ebenfalls zwischen Gesprächen/Benchmarks ausgeführt werden.

## Verifizierter Erststand, 13. Oktober 2026

Freigegebene Eigenaufnahme: `founder-test/a2-time-location.wav`, 7,576 Sekunden, ohne Clipping. Die Referenz wurde durch die bestehende deutsche ASR transkribiert. Der Nutzer hat die Verwendung seiner Eigenaufnahmen für diese Demo ausdrücklich autorisiert.

Aktive Revision: `20261013T163838Z-b30827f022f1`. Original-SHA256: `6ca08a904964eb6f85160d7decff4c9597a57247cc95c16de4f6d109762df43b`. Normalisierte Referenz: `14519df9b5ae7173f1a11d5dc08c350192ca1a515c2845a67eb7cb5816f00be2`.

Die neue Stimme erzeugte „Guten Tag. Ich helfe Ihnen bei der Bestellung Ihres neuen Laptops.“ als 4,64 Sekunden PCM16/24-kHz-Audio. Erster PCM-Byte: 154 ms; vollständige Synthese: 1,034 s; ASR-Rückprüfung: 365 ms, identische Wörter. Frei verfügbarer Arbeitsspeicher danach: 27,54 GiB. TTS-Prozess 5572 wurde weiterverwendet. Die Klangähnlichkeit beurteilt der Sprecher anhand der Hörprobe; ASR belegt die Verständlichkeit der Wörter.

Hörprobe: `runtime/marcel-german-demo.wav`; Messdaten: `runtime/founder-validation.json`. `native-speech-validation/speech_probe.py validate` verwendet ebenfalls die aktive validierte Eigenstimme und hält während seiner Messung den Aktivierungslock. Jede Registrierung invalidiert zuvor den Startup-Cachebeleg, damit ein verlorenes HTTP-Ergebnis oder eine fehlgeschlagene Wiederherstellung keine alte Stimmidentität als bestätigt erscheinen lässt.
