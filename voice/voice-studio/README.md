# Voice Studio

Öffnen: https://strix-alloy.tail7f425a.ts.net/voice-studio/

Der private Zugangscode liegt auf dem Desktop in `Voice-Studio-Zugang.txt`.
Die Desktop-Verknüpfung **SCC - Stimmen verwalten** startet den Webdienst bei
Bedarf und öffnet die Seite. Der Webdienst startet auch bei Windows-Anmeldung.
Er lädt kein zusätzliches Modell.

1. Mit dem Zugangscode anmelden.
2. Einen Namen eingeben und bestätigen, dass die Aufnahme die eigene Stimme ist.
3. Die Aufnahme starten und den angezeigten Text vollständig vorlesen.
4. Die Aufnahme anhören und das Stimmprofil speichern.
5. Im gespeicherten Profil **Für nächste ServiceNow-Anfrage verwenden** wählen.
6. Einen neuen ServiceNow-Sprachanruf starten.

Gespeicherte Aufnahmen und die aktive Auswahl bleiben auf diesem Rechner
erhalten. Ein normaler TTS-Start stellt die aktive Auswahl wieder her. Der
Stimmenwechsel registriert die neue Referenz im vorhandenen TTS-Service;
ein Neustart des Modells ist nicht erforderlich. Vor dem Wechsel ein
laufendes Gespräch beenden. Die Webseite verweigert den Wechsel, wenn sie
eine aktive native Sitzung erkennt.

Originalaufnahmen lassen sich für jedes Profil anhören. **Stimme anhören**
im Bereich der aktiven Auswahl erzeugt einen kurzen deutschen TTS-Test mit
der ausgewählten Stimme. Die Aufnahme stoppt spätestens nach 25 Sekunden.

## Betrieb

```powershell
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-VoiceStudio.ps1' -Action Start
& 'C:\Projects\strix-alloy-scc-voice\voice\Start-VoiceStudio.ps1' -Action Status
```

Der eigene Webdienst lauscht nur auf `127.0.0.1:8863`. Der bestehende
Tailscale Funnel leitet ausschließlich den zusätzlichen Pfad `/voice-studio`
dorthin weiter. Die vorhandenen Modell- und Voice-Routen bleiben erhalten.
Abhängigkeiten stehen in `requirements.txt`; verwendet wird die vorhandene
native Bridge-Python-Umgebung. Code und Zugangsdaten werden getrennt
gespeichert. `runtime/` und die Stimmenreferenzen werden nicht eingecheckt.

Tests: `python -m unittest discover -s voice/voice-studio -p 'test_*.py'`.
Die HTTP-Tests verwenden temporäre Profile und ersetzte Native-Schnittstellen;
Live-TTS und Mikrofonaufnahme benötigen die getrennte Integrationsprüfung.
