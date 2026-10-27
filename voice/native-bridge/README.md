# Nativer ServiceNow-Voice-Adapter

Stand: 19.10.2026. Dieser Adapter verbindet den nativen Voice-/Now-Mobile-Medienpfad mit lokalem STT, TTS und der vorhandenen Bot-Bridge. Das Modell wird über den nativen ServiceNow-Skill-/Custom-LLM-Pfad angesprochen. Modell- und Skillwahl bleiben in AI Control Tower / Skill Kit; Sprache und Voice-Anweisungen kommen aus dem Voice Assistant.

## Aktueller Nachweisstand

- Früherer Android-/iPhone-Betrieb und ein externer IPv4-Medienpfad sind historisch belegt.
- Frische externe Versuche erreichen Session und SDP, aber keinen ICE-/DTLS-Audiopfad. TTS beginnt lokal nach 46–47 ms; dies beweist keine Wiedergabe auf dem Telefon.
- Die neue optionale Host-TURN-Konfiguration benötigt einen öffentlichen Relaydienst und private Credentials. Sie ist keine bestätigte Behebung des aktuellen Telefonfehlers.
- Die neue Konfiguration wurde unabhängig geprüft. Details zu Regressionstests und dem bekannten bereits zuvor bestehenden Begrüßungs-Testfehler stehen im Release-Nachweis.
- Der laufende Prozess wurde für die bloße Quellcode-Erweiterung nicht neu gestartet; Relaybetrieb ist nicht aktiviert.

Historische Probeberichte im Repository beschreiben ihren damaligen Stand. Insbesondere frühere Halogen-Zeiten, Testaufträge, feste Demosprachen und einzelne Geräteerfolge sind keine aktuelle Gesamtfreigabe.

## Endpunkte und Autorisierung

Der HTTP-Listener bindet an `127.0.0.1:8860`; `GET /health` ist ein begrenzter Dienststatus und kein ICE-/Audio-Bereitschaftsnachweis.

Der native mobile SDK-Pfad unter `/api/webrtc/sessions` verwendet begrenzte Bearer-Authentisierung und die native ServiceNow-Service-/Agent-Autorisierung. Die zusätzliche eigene Settings-v1-Ressource akzeptiert plattformautorisierte opaque OAuth-Tokens; reine JWT-Formprüfung ist für diesen mobilen Pfad kein Ersatz. Ungültige oder abgelehnte native Autorisierung bleibt ein Fehler.

Der separate Browser-Test-Assistant-WebSocketpfad prüft zusätzlich den exakten Instanz-Origin und besitzt weiterhin seinen eigenen JWT-Syntaxguard. Beide Einstiegspfade sind getrennt zu qualifizieren. Weder Tokenform noch eine private Entwicklungsidentität erteilen fachliche Rechte. Die Bot-Bridge verwendet ihre konfigurierte Integrationsidentität; Voice-Login bedeutet keine beliebige Benutzerimpersonation.

SessionCreate liefert für SDK 2.26 HTTP 200, nicht 201. Die SDP-Antwort behält ihren verschachtelten Vertrag. Mobile TURN-Zugangsdaten werden von beiden untersuchten SDKs durch ServiceNow-OAuth ersetzt; generische TURN-Passwörter werden deshalb nicht an die mobilen DTOs angehängt.

## Netzwerk

Standardmäßig wird STUN verwendet; diese Version ist nicht mehr der historische reine Host-Kandidaten-Stand. HTTPS-Tunnel/Funnel transportieren die Signalisierung, aber keine UDP-Medien. Ein erfolgreicher Health- oder Session-Aufruf beweist keine erreichbare WebRTC-Verbindung.

Die optionale private `host_ice_config_file` wird relativ zur Bridge-Konfigurationsdatei aufgelöst und beim Prozessstart geladen. Sie enthält genau einen TURN-Endpunkt und Environment-Verweise für die Credentials. Siehe [HOST-RELAY.md](HOST-RELAY.md). Ohne diese Option bleibt der bisherige STUN-Default erhalten.

Ein öffentlicher Relayhost benötigt erreichbare Listener und Relayports. TURN/TLS auf 443 beschreibt hier Host → Relay; der Telefonpfad zum publizierten Relaykandidaten benötigt weiterhin UDP. Für beliebige vollständig UDP-gesperrte Telefonnetze ist zusätzlich ein passender SDK-OAuth-TURN-Vertrag erforderlich.

## Lokale Dienste und Konfiguration

| Dienst | Referenzport |
| --- | ---: |
| Native Adapter | 8860 |
| Bot-Bridge / authentisierter Callback | 8850 / 8853 |
| STT | 8861 |
| TTS | 8862 |
| Optionale Stimmenverwaltung | 8863 |
| Modell-Gateway | 8841 |

STT/TTS-Engine, Modellgewichte und aktive Custom-Stimme werden durch diesen Adapter nicht ersetzt. Native Sprachauswahl allein beweist keine mehrsprachige Synthese der eingesetzten TTS-Engine.

Eine eigene private Konfiguration aus der generischen Vorlage erstellen. Bestehende `config.example.json`-Dateien aus einer Betreiberinstallation können reale Werte enthalten und sind kein veröffentlichbares Template. Keine Credentials, Ziel-IDs, Stimmenaufnahmen oder Laufzeitlogs übernehmen.

Die vollständige Schrittfolge steht in [NEUINSTANZ-INSTALLATION-DE.md](../../docs/local-voice/NEUINSTANZ-INSTALLATION-DE.md). Die Untersuchung steht in [NETZWERK-UND-LATENZ-20261019.md](../../docs/local-voice/NETZWERK-UND-LATENZ-20261019.md).

## Start und Abnahme

Den Zielhost mit passenden Python-/Engineumgebungen und qualifiziertem Modellprofil vorbereiten. Der historische Halogen-Launcher ist kein generischer Gemma-Installer. Private Konfiguration, Modell-/Binäridentität und Prozessbesitz vor einem Start prüfen.

Die Reihenfolge ist STT/TTS und aktive Stimme, Modell, Gateway, Bot-Bridge/Native Adapter, öffentliche Routen, optional VoiceStudio. Die vollständigen geprüften Aufrufe und ihre Voraussetzungen stehen in der Installationsanleitung.

Nur eigene Prozesse kontrolliert bei inaktiver Sitzung neu starten. Bestehende fachliche ServiceNow-Anfragen nicht blind wiederholen. Barge-in unterbricht Audio, nicht automatisch die bereits eingereichte Aktion. Ein unklar beendeter eigener Dialog kann die Kapazität bis zur Klärung belegt halten.

Abnahme auf Android und iPhone jeweils mit Begrüßung, erstem Turn, Folgeturn, Unterbrechung, sauberem Abschluss und neuem Anruf durchführen; LAN, 5G und fremdes WLAN getrennt prüfen. ICE, DTLS und Audio in beide Richtungen müssen funktionieren.

Die optionale RTC-Diagnose ist standardmäßig ausgeschaltet. `SCC_VOICE_MEDIA_DIAGNOSTIC_CALLS=1` begrenzt sie auf einen autorisierten SDK-Call und maximal drei Zustandsaufnahmen. Sie protokolliert keine SDP-, Adress-, Credential- oder Gesprächsinhalte. Andere allgemeine Bibliothekslogs können Netzwerkadressen enthalten und bleiben privat.
