# Private TURN-Konfiguration auf dem Host

Dieses optionale Overlay ergänzt den privaten Host. Es ist keine bestätigte Reparatur der aktuellen Mobilfunkverbindung. Ohne konfigurierte Ergänzung bleibt die bisherige Google-STUN-Konfiguration unverändert. Die veröffentlichte Basisversion 2.0 wird durch dieses separate Overlay nicht nachträglich als TURN-fähig ausgewiesen.

## Wirkung und Grenze

Nur der aiortc-Peer auf dem Host erhält einen zusätzlichen TURN-Server. Der Host veröffentlicht tatsächlich gesammelte Relay-Kandidaten im bestehenden SDP-Answer. Das Session-Create-DTO und die Browser-Antwort liefern weiterhin ausschließlich das bisherige STUN-Array. Beide nativen mobilen SDKs ersetzen TURN-Zugangsdaten durch ihre ServiceNow-OAuth-Anmeldung; deshalb dürfen generische TURN-Passwörter nicht über diese DTOs ausgegeben werden.

Ein gültiges Config-File, ein gestarteter Prozess, HTTP 200 oder abgeschlossene ICE-Sammlung beweisen keine funktionierende Relay-Verbindung. Der Host kann eine fehlgeschlagene TURN-Allokation ohne Relay-Kandidaten beenden. Dieses Overlay ergänzt bewusst keinen öffentlichen relay-ready-Status.

## Voraussetzungen

- Ein tatsächlich bereitgestellter, vom Host und Mobilgerät erreichbarer TURN-Dienst mit autorisierten Zugangsdaten. Dieses Paket erfindet keinen Dienst und enthält keine produktiven Zugangsdaten.
- Erreichbare TURN-Listener und Relay-UDP-Ports gemäß der tatsächlichen Serverkonfiguration.
- Falls der Host TURN über TCP oder TLS benötigt: ein passender Listener des Dienstes. TCP/TLS auf Port 443 ist nur der Host-zu-TURN-Weg. Der veröffentlichte Relay-Kandidat ist weiterhin UDP; dies umgeht kein vollständiges UDP-Verbot auf dem Mobilgerät.
- Der HTTPS-Signalisierungsproxy bzw. Funnel wird dadurch nicht zum UDP-Medienrelay.

## Konfiguration

1. Änderungen zuerst anhand des Manifests und Diffs prüfen. Die vorhandene Konfiguration sichern; dieses Overlay aktiviert keinen Dienst automatisch.
2. Eine private Datei außerhalb öffentlicher Ausgaben anlegen, auf die ausschließlich der Dienstbenutzer und berechtigte Administratoren zugreifen können. Die Vorlage host-ice.private.example.json enthält absichtlich eine leere URL und ist vor dem Ergänzen einer echten Betreiber-URL ungültig.
3. Genau einen TURN-Eintrag angeben. username_env und credential_env benennen vorhandene Umgebungsvariablen des Hostprozesses. Deren Werte kommen aus der privaten Betriebsumgebung bzw. dem Secret Store, nicht aus diesem Paket. Im JSON stehen keine Inline-Zugangsdaten.
4. Im bestehenden Bridge-JSON das optionale Feld host_ice_config_file ergänzen; host-ice.bridge-config.example.json zeigt nur dieses zusätzliche Feld. Ein relativer Pfad gilt relativ zum Bridge-JSON, nicht zum Prozess-Arbeitsverzeichnis.
5. Erst nach einem geplanten Neustart liest der Prozess die Datei und Umgebungswerte einmal ein. Laufende Anrufe und per-call-Einstellungen verändern diesen Snapshot nicht. Ohne bereitgestellten TURN-Dienst ist kein Neustart allein zur Scheinaktivierung nötig.

Die Datei enthält ausschließlich turn_servers, ein Array mit exakt einem Objekt und genau den Feldern url, username_env und credential_env. Mehrere TURN-Server werden explizit abgewiesen, weil die installierte aiortc-Version ansonsten nur den ersten verwendet. Das bisherige STUN bleibt zusätzlich automatisch gesetzt.

Unterstützt werden turn mit UDP als Standard oder transport=tcp sowie turns mit TCP/TLS als Standard oder transport=tcp. turns mit UDP, STUN-URLs in der TURN-Liste, Benutzerinformationen in URLs, Pfade, Fragmente, zusätzliche Query-Parameter und Steuerzeichen sind ungültig. Ein optionaler Port muss zwischen 1 und 65535 liegen. DNS-Namen und IPv4-Literale werden unterstützt; IPv6-Literale in der TURN-URL kann die hier geprüfte aiortc-Version nicht parsen.

Die private Datei ist auf 16 KiB begrenzt und UTF-8. Doppelte oder unbekannte Schlüssel werden abgewiesen. Umgebungsreferenzen müssen portable Bezeichner mit höchstens 128 Zeichen sein. Benutzername: höchstens 256 Zeichen. Passwort: höchstens 4096 Zeichen. Werte dürfen weder leer sein noch Steuerzeichen enthalten. Fehlertexte geben keine Werte oder Dateiinhalte aus.

## Prüfung und Rücknahme

Die fokussierten Offline-Tests laufen im Verzeichnis voice/native-bridge mit:

    python -B -m unittest test_host_ice -v

Sie prüfen den installierten aiortc-Konfigurationspfad, strikte Eingaben, Secret-Abschirmung, Snapshot-Verhalten und den unveränderten mobilen HTTP-Vertrag. Sie kontaktieren keinen echten Relay-, ServiceNow-, ASR- oder TTS-Dienst und erzeugen keinen echten mobilen Anruf.

Für den tatsächlichen Mobilfunknachweis sind anschließend ein gesammelter Relay-Kandidat, ein ausgewählter funktionierender Kandidatenpfad sowie empfangenes und ausgegebenes Audio erforderlich. Ein vorhandener Relay-Kandidat allein reicht nicht. Sichere Metadaten genügen; keine Zugangsdaten oder vollständigen SDP-Daten veröffentlichen.

Zum Deaktivieren das Feld host_ice_config_file aus der Bridge-Konfiguration entfernen und einen geplanten Neustart durchführen. Danach gilt wieder ausschließlich der unveränderte STUN-Standard. Vollständige Quell-Rücknahme anhand der gesicherten Basisdateien und des Manifests durchführen.

## Teststand dieses Kandidaten

- Neue fokussierte Tests: 9 bestanden; Relay-/Input-Lifecycle-/Mic-Gap-Prüfung zusammen: 41 bestanden.
- Gesamte native Testsuite: 345 Tests, 344 bestanden. Ein bereits auf der unveränderten Basis reproduzierbarer Test erwartet eine andere Reihenfolge von Begrüßung und Sprachauswahl: test_voice_created_lifecycle.CreatedLifecycleTests.test_real_native_call_emits_configured_introduction_and_selection_once. Dieser unabhängige Ablauf wurde nicht geändert.
- Geprüfte Transportbibliotheken: aiortc 1.15.0, aioice 0.10.2.
- Kein produktiver TURN-Endpunkt, keine echte TURN-Allokation und kein Ende-zu-Ende-Nachweis mit Android/iOS wurden für dieses Overlay durchgeführt.
