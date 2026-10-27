# Hostseitiges TURN – Konfiguration und Betrieb

Stand: 19.10.2026. Die aktualisierte Lieferung enthält die geprüfte Host-Relay-Erweiterung separat unter `relay-overlay/`. Der bisherige Stand unter `host-overlay/` bleibt unverändert. Ein tatsächlicher Relayendpoint und seine Credentials sind nicht bereitgestellt; kein Native-Prozess wurde für diese Erweiterung neu gestartet und kein Live-Relay aktiviert. Der aktualisierte Quellstand ist auf dem Referenzhost übernommen; die anschließend ausgeführten neun Host-ICE-Tests bestanden. Der laufende Native-Prozess verwendet weiterhin seinen bisherigen Stand. Ein Ende-zu-Ende-Erfolg mit Android/iOS ist noch nicht nachgewiesen.

Die ServiceNow-XML bleibt bytegleich. Modell/Prompts bleiben in AI Control Tower/Skill Kit, Voice-Anweisungen/Sprachen am Voice Assistant; STT/TTS und Custom-Stimmen bleiben unverändert.

## 1. Quellstand übernehmen

Zuerst den vollständigen Host-Grundbestand und den bisherigen 2.0-Overlay nach [NEUINSTANZ-INSTALLATION-DE.md](NEUINSTANZ-INSTALLATION-DE.md) vorbereiten. Danach `relay-overlay/APPLY.md` und `relay-overlay/manifest.json` verwenden:

1. Die `baseline_sha256`-Werte mit den vorhandenen Dateien vergleichen und diese sichern. Bei Abweichungen zunächst zusammenführen und erneut prüfen.
2. Entweder die drei vollständigen Dateien `native_bridge.py`, `host_ice.py` und `test_host_ice.py` unter `voice/native-bridge/` übernehmen und den minimalen `demo_audio_smoke.patch` anwenden, **oder** alternativ den gesamten `relay-overlay.patch` verwenden. Nicht beide Wege zusätzlich anwenden.
3. Ein Patch zuerst aus dem Repository-Stamm mit `git -c core.autocrlf=false apply --check <Patchdatei>` prüfen und nach erfolgreicher Prüfung mit `git -c core.autocrlf=false apply <Patchdatei>` anwenden. Die Einstellung gilt nur für diesen einzelnen Git-Aufruf; die globale Git-Konfiguration bleibt unverändert. Der Smoke-Patch ersetzt nur den direkten Config-Aufbau durch `production.load_config(args.config)`. Private Smoke-Fixtures werden nicht mitgeliefert.
4. Die `after_sha256`-Werte prüfen; der in `unchanged_contract` dokumentierte Hash von `sdk_sessions.py` bleibt unverändert.
5. Fokussierte Offline-Tests ausführen. Quellübernahme allein startet keinen Prozess und aktiviert kein Relay.

## 2. Öffentlichen Relaydienst bereitstellen

Erforderlich ist ein tatsächlich betriebener, vom Host und Mobilgerät erreichbarer TURN-Dienst mit autorisierten Credentials. Das Paket enthält weder Dienstkonto noch Relayendpoint oder produktive Zugangsdaten. Einen eigenen öffentlichen Relayhost oder verwalteten Dienst nach dessen Betreiberanleitung bereitstellen; Konto, Vertrag oder Abrechnung werden nicht vorausgesetzt.

TURN-Listener, TLS-Zertifikat soweit verwendet, Adressfamilien und öffentlicher Relay-Portbereich sind vom Betreiber zu prüfen. Ein HTTP-Pfadproxy beziehungsweise Funnel-only ersetzt diese Netzwege nicht.

TURN/TCP oder TURN/TLS auf Port 443 ist in dieser Umsetzung der Weg **vom Betreiberhost zum Relay**. Der veröffentlichte Relaykandidat ist weiterhin UDP. Das Mobilgerät braucht einen passenden UDP-Medienweg dorthin. Ein vollständiges UDP-Verbot im Telefonnetz wird damit nicht umgangen.

## 3. Private Konfiguration

In der ausgewählten vollständigen Native-Bridge-Konfiguration die optionale Eigenschaft ergänzen:

```json
{
  "host_ice_config_file": "D:/Private/voice/host-ice.json"
}
```

Dies ist kein Ersatz für die übrigen Bridge-Einstellungen. Relative Pfade gelten relativ zu dieser Bridge-Konfigurationsdatei, nicht zum Prozess-Arbeitsverzeichnis.

Die private Datei enthält:

```json
{
  "turn_servers": [
    {
      "url": "",
      "username_env": "SCC_VOICE_TURN_USERNAME",
      "credential_env": "SCC_VOICE_TURN_PASSWORD"
    }
  ]
}
```

Die leere URL ist absichtlich ungültig. Sie muss durch die echte URL des eigenen Relays ersetzt werden. Unterstützte Syntax: `turn:<relay-host>:<port>?transport=udp`, `turn:<relay-host>:<port>?transport=tcp` oder `turns:<relay-host>:<port>?transport=tcp`. Diese Syntaxbeispiele benennen keinen bereitgestellten Dienst. Im Paket liegen auch `host-ice.bridge-config.example.json` und `host-ice.private.example.json`.

Die referenzierten Umgebungsvariablen müssen über die private Dienst-/Secretverwaltung im Environment des Native-Prozesses bereitstehen. Im JSON stehen ausschließlich Variablennamen. Secretwerte nicht in öffentliche JSON, Kommandozeilen, Repository oder mobile Antworten schreiben. Zugriff auf die private Datei auf Dienstbenutzer und berechtigte Administratoren begrenzen.

Ohne `host_ice_config_file` bleibt der bisherige STUN-Standard unverändert. Wird eine Relaydatei ausdrücklich ausgewählt, führen ungültige Datei-/Secretwerte zur Startverweigerung; sie werden nicht still durch STUN ersetzt.

## 4. Start und Secretrotation

Der Native-Prozess liest private Datei und referenzierte Umgebungswerte genau einmal beim Start. Laufende Anrufe und Änderungen auf der Platte laden diesen Snapshot nicht neu.

Für die erste Aktivierung:

1. Relay tatsächlich bereitstellen und dessen Erreichbarkeit/Authentisierung separat prüfen.
2. Vollständige Bridge-Konfiguration, private ICE-Datei und Secretvariablen vorbereiten.
3. Laufende Gespräche geordnet beenden; keine unklar zugestellten fachlichen Aktionen wiederholen.
4. Nur den eindeutig zugeordneten eigenen Native-Prozess im vorgesehenen Betriebsfenster kontrolliert beenden. Der allgemeine Native-Koordinator hat keinen Stop-All-Befehl.
5. Den Native-Dienst mit der ausgewählten Konfiguration und den privaten Umgebungswerten starten. Der vorhandene Startweg nach korrekt vorbereiteten Zielprofilen lautet:

```powershell
.\voice\Start-NativeVoice.ps1 -Action Voice `
  -BotConfig '.\voice\bridge.local.json' `
  -NativeConfig '.\voice\native-bridge\config.local.json'
```

Der Koordinator startet beziehungsweise prüft Bot und Native; einen bereits laufenden Native-Prozess mit altem Snapshot aktualisiert er nicht automatisch. Der zuvor kontrollierte Neustart ist deshalb notwendig. TTS, STT, Modell und aktive Stimme müssen für diese Konfigurationsänderung nicht neu gestartet werden.

Bei Secretrotation neue Werte zuerst in der privaten Betriebsumgebung bereitstellen, danach denselben kontrollierten Native-Neustart und die Verbindungsprüfung durchführen. Gültigkeitsdauer und eine gegebenenfalls notwendige Überlappung alter/neuer Credentials müssen zur tatsächlichen Relaypolicy passen. Alte Werte nicht in Logs oder öffentliche Rotationsnachweise übernehmen.

Solange Relayendpoint oder Credentials fehlen, keinen Neustart als vermeintliche Aktivierung ausführen. Kopierte Quellen und eine gültige Beispieldatei stellen keinen Relaydienst bereit.

## 5. Implementierte Konfigurationsgrenzen

| Punkt | Validierung |
| --- | --- |
| Datei | UTF-8, höchstens 16 KiB |
| Struktur | Genau `turn_servers` mit genau einem Server und einer URL |
| Keys pro Server | Genau `url`, `username_env`, `credential_env`; keine zusätzlichen/duplizierten Keys |
| URL | `turn` über UDP als Standard oder TCP; `turns` über TCP/TLS |
| Ungültige URL-Teile | Inline-Zugangsdaten, Pfade, Fragmente, zusätzliche Query-Parameter, Steuerzeichen und `turns` mit UDP |
| Host | DNS-Name oder IPv4-Literal; keine IPv6-Literale im geprüften Parser |
| Port | Falls angegeben 1–65535 |
| Secretverweise | Portable Environment-Variablennamen, höchstens 128 Zeichen |
| Username | Nicht leer, höchstens 256 Zeichen, keine Steuerzeichen |
| Passwort | Nicht leer, höchstens 4096 Zeichen, keine Steuerzeichen |
| Fehlerausgabe | Keine Secretwerte oder privaten Dateiinhalte |

Mehrere TURN-Server werden ausdrücklich abgewiesen, da der geprüfte aiortc-Pfad sonst nur den ersten verwenden würde. Die bestehende STUN-Konfiguration bleibt zusätzlich erhalten.

Nur der lokale aiortc-Peer erhält TURN. Mobile/browserseitige `iceServers`-Antworten bleiben beim bisherigen STUN-Vertrag; TURN-Username/-Passwort gelangen nicht in diese DTOs. Der Host veröffentlicht tatsächlich gesammelte Relaykandidaten über den bestehenden SDP-Antwortweg.

## 6. Verifikation und Nachweisgrenzen

Die unabhängige Code-Review ist abgeschlossen. Die dokumentierten Offline-Ergebnisse sind:

| Prüfung | Ergebnis |
| --- | --- |
| Neue Host-ICE-Tests | 9/9 bestanden; nach Quellübernahme erneut 9/9 bestanden |
| Relay-, Input-Lifecycle- und Mic-Gap-Prüfung | 41/41 bestanden |
| Vollständige native Suite | 344/345 bestanden |
| Verwendete Bibliotheken | aiortc 1.15.0, aioice 0.10.2 |
| Echte TURN-Allokation | Nicht nachgewiesen |
| Physische Android-/iOS-Abnahme | Offen |

Der eine fehlschlagende Test ist `test_voice_created_lifecycle.CreatedLifecycleTests.test_real_native_call_emits_configured_introduction_and_selection_once`. Er erwartet eine andere Reihenfolge von Begrüßung und Sprachauswahl. Derselbe Fehler wurde auf der unveränderten Basis reproduziert; dieser Gesprächsablauf wurde durch das Relay nicht geändert. Die vollständige Suite ist damit ausdrücklich nicht vollständig grün.

Reproduktion im vollständigen Hostrepository mit dessen vorbereiteter Umgebung:

```powershell
$VoicePython = Join-Path $VoiceRepo 'voice\native-bridge\.venv\Scripts\python.exe'
Push-Location -LiteralPath (Join-Path $VoiceRepo 'voice\native-bridge')
try {
    & $VoicePython -B -m unittest test_host_ice -v
    if ($LASTEXITCODE -ne 0) { throw 'Host-ICE-Pruefung fehlgeschlagen.' }
    & $VoicePython -B -m unittest test_host_ice test_input_lifecycle test_mic_gap -v
    if ($LASTEXITCODE -ne 0) { throw 'Relay-/Lifecycle-Pruefung fehlgeschlagen.' }
}
finally {
    Pop-Location
}
```

`$VoiceRepo` bezeichnet den eigenen vollständigen Repositorypfad aus der Installationsanleitung. Die Tests prüfen Parser, den aiortc-Konfigurationspfad, Secretschutz, Snapshotverhalten und unveränderten mobilen HTTP-Vertrag. Sie kontaktieren keinen echten Relay-, ServiceNow-, STT- oder TTS-Dienst und erzeugen keinen echten mobilen Call. Die vollständigen Testzahlen stehen in `relay-overlay/verification.json`.

Eine akzeptierte JSON-Datei, ein gestarteter Prozess, HTTP 200 oder abgeschlossene ICE-Sammlung beweisen keine funktionierende Relayverbindung. Eine TURN-Allokation kann scheitern, ohne dass ein Relaykandidat entsteht. Die Erweiterung führt deshalb keinen öffentlichen `relay-ready`-Status ein.

Nach kontrollierter Aktivierung sind mindestens zu prüfen:

1. Tatsächliche TURN-Allokation und gesammelter Relaykandidat; keine Secrets in Logs/DTOs.
2. Ausgewähltes funktionierendes Kandidatenpaar und DTLS-Verbindung.
3. Begrüßung auf physischem Android und iPhone über 5G hörbar.
4. Audio in beide Richtungen, erster/weiterer Turn und sauberer Abschluss.
5. Zweiter Call und Test aus einem weiteren externen Netz.

Der untersuchte mobile SDK-2.26-Vertrag ersetzt mobile TURN-Authentisierungswerte durch ServiceNow-OAuth. Ein generisches coturn mit unabhängigem Username/Passwort kann deshalb nicht einfach als mobiler TURN-Server eingetragen werden. Ein echter mobiler TCP/TLS-Fallback braucht einen SDK-kompatiblen Authentisierungsvertrag. Die hostseitige Unterstützung ist keine Zusage für jedes restriktive Telefonnetz.

## 7. Rücknahme

Zum Deaktivieren `host_ice_config_file` aus der privaten Bridge-Konfiguration entfernen und den eigenen Native-Dienst geplant neu starten. Danach gilt wieder ausschließlich der bisherige STUN-Standard. Ein laufender Prozess behält seinen bisherigen Snapshot bis zum Neustart.

Für eine vollständige Quellrücknahme die gesicherten Basisdateien anhand des Manifests wiederherstellen und nur die durch diese Erweiterung neu hinzugefügten Dateien entfernen. TTS/STT, Custom-Stimme, Modell-/Skillkonfiguration und native Voice-Anweisungen bleiben erhalten.
