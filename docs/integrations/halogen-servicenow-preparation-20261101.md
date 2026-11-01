# ServiceNow-Vorbereitung mit Halogen 0.18.22

Stand: 1. November 2026. Die Messreihen sind beendet. Auf Marcels Wunsch laufen
keine weiteren Modellmessungen während seiner League-Sitzung; eine spätere
Messung benötigt eine erneute ausdrückliche Freigabe. Die weitere Vorbereitung
erfolgt ohne Inferenz und ohne Neustart des laufenden Servers.

## Lokaler Anschluss

| Einstellung | Vorbereiteter Wert |
| --- | --- |
| Engine / Startprofil | Halogen 0.18.22 / `CurrentText32K` |
| Lokale Basisadresse | `http://127.0.0.1:8840/v1` |
| Bestehender HTTPS-Anschluss | `https://strix-alloy.tail7f425a.ts.net/v1/chat/completions` |
| Öffentlicher Modellname | `halogen-v2` |
| Authentifizierung | Bestehender geschützter API-Key im Bearer-Header |
| Kontext / gleichzeitige Anfragen | 32.768 Positionen / eine Anfrage |

Die lokalen Prozessidentitäten und der Listener sind bestätigt. Die heutige
Vorbereitung enthält keinen neuen Aufruf aus einer ServiceNow-Instanz und keinen
Nachweis ihrer externen Erreichbarkeit. Body-Felder, Antwortverarbeitung und
Credential-Einbindung stehen in der [REST-Anleitung](halogen-servicenow.md).

Die [Messung zweier paralleler Anfragen](../benchmarks/halogen01822-concurrency2-20261101.md)
ergab etwa 5,7 % mehr Gesamtdurchsatz bei längerer Antwortzeit je Anfrage.
Für den laufenden ServiceNow-Anschluss bleibt deshalb das bisherige Profil aktiv.

## Konsolenprotokoll vorbereitet

Der folgende Start wurde mit `-PrintOnly` ohne Modellstart geprüft:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -ConsoleTrace
```

Er ist für den nächsten regulären Start vorgesehen. Die vorbereitete
Konfiguration unterscheidet sich vom laufenden Profil ausschließlich durch
`console_trace: true`; PowerShell 7 ist dafür nicht erforderlich. Der aktuelle
Server bleibt unverändert mit normalem Betriebsprotokoll und ohne Inhalts-Trace
online. Während dieser Vorbereitung wurden keine Anfragen gesendet und keine
Session-Dateien vom Starter angelegt.

## Vorbereiteter Agent-Wartungsschritt

Der bestehende, unabhängig geprüfte Abschluss bleibt erhalten:

- Datei: `complete-halogen-agent-existing-stage.compact.js`, 379.190 Bytes.
- SHA-256: `9bfd4ef356c5bf3fc88153a235ef4c01e9a4a08dac3d5adb0d38b9a94d1ef3c4`.
- Alle 18 eingefrorenen Eingaben und der kanonische lesbare Plan stimmen mit
  der bestehenden Prüfung überein. Es wurde keine neue Variante erzeugt.
- Die vorbereitete Fortsetzung verwendet das vorhandene Staging-Set und den
  korrigierten Parent. Offen bleiben die im
  [Post-Run-Audit](../../servicenow/byollm/halogen-agents-20261101/POSTRUN.md)
  beschriebenen Child-/Capture-Korrekturen und der Ledger-Schritt.

Die konkrete Freigabefrage zur einmaligen SDK-Ausführung im bestehenden
ServiceNow-Chat bleibt offen. Hier wurden ausschließlich lokale Dateien
geprüft; keine Instanzänderung, Geschäftsaktion oder Voice-Ausführung erfolgte.
Der alte Freeze und alle bisherigen Ausführungsbelege bleiben unverändert.

Private lokale Belege: `readiness-handoff.json`, `trace-profile-check.json` und
`prepared-console-trace-profile.json` unter
`server/.local/halogen-update-20261101/primary01822/servicenow-preparation/`.

Die [Prefix-Cache-Vorbereitung](halogen-servicenow-prefix-cache-20261101.md)
ergänzt einen netzwerkfreien Anfragegenerator und eine geprüfte Offline-Auswertung
für spätere Folgefragen. Sie sendet keine Anfragen und verändert weder den
laufenden Server noch die eingefrorene ServiceNow-Fortsetzung.
