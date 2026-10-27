# Externe Mobile-Verbindung und Gemma-Latenz – 19.10.2026

## Ergebnis und Betriebsstatus

Der Abbruch liegt im WebRTC-Medienaufbau. Authentisierung und HTTPS-Signalisierung funktionieren; eine hörbare Begrüßung ist nicht nachgewiesen. Die bisherige Architektur hat ausschließlich STUN und keinen TURN-Ausweichweg. Die separate Host-Erweiterung schließt die Konfigurationslücke, benötigt aber einen öffentlich erreichbaren Relaydienst mit gültigen Credentials. Solange dieser fehlt, gilt der externe Android-/iPhone-Fehler **nicht als behoben**.

TTS, STT, Custom-Stimme, Modellgewichte und AI-Control-Tower-/Skill-Konfiguration wurden für diesen Netzwerkbefund nicht geändert. Das native Update-Set-XML bleibt bytegleich.

## Beobachtungen

| Nachweis | Ergebnis | Grenze |
| --- | --- | --- |
| Frische vom Nutzer gemeldete Android-/iPhone-Versuche aus fremdem Netz/5G | Session, Offer und Kandidaten HTTP 200; Client schließt mit DELETE 202 | Einzelne Logsession nicht plattformspezifisch markiert |
| Instrumentierte Session | Zwei gebündelte Medienabschnitte; Wire-/Local-SDP identisch; Media-IDs, ICE-Ufrags und zehn Trickle-Kandidaten konsistent | Keine vollständige Paketaufzeichnung |
| Medien | Kein verbundenes ICE/DTLS; eingehende Audioframes und DTLS/RTP-Zähler null | Diese Zähler zählen keine STUN-Pakete |
| Begrüßung | Erster lokaler TTS-Chunk nach 46–47 ms | PCM-Erzeugung beweist keine Zustellung |
| Host | Private IPv4-Adressen und ULA-IPv6, kein globales IPv6 | Keine automatische IPv6-Reparatur |
| Mobiler Peer | CLAT-kompatible IPv4-Service-Continuity-Adresse, globales IPv6 und serverreflexive Kandidaten | Kein Beweis für Carrier oder NAT-Typ |
| Host-UDP-Probe 10:31 UTC | Google → Cloudflare → Google aus demselben UDP-Socket; Antworten 31–47 ms; gleiche öffentliche Zuordnung | Nur zwei Ziele; kein Nachweis des Telefon-Pfads |
| Öffentliche Exposition | Funnel HTTPS/TCP 443 mit HTTP-Pfadrouten | Kein UDP-Medienrelay |
| Erfolgreicher Vortag | 18.10., 20:50 lokale Logzeit: öffentlicher IPv4-Peer, ICE verbunden, über 2.000 empfangene Frames | Carrier/Gerät unbestimmt; weitere Erfolge im LAN |

Der Vergleich mit dem funktionierenden Quellstand ergab keine Änderung der SDP-Aushandlung und Kandidatenpublikation außer optionalen Diagnose-Lesezugriffen. aiortc/aioice wurden nicht für diesen Fehler neu aktualisiert. Das genaue NAT-/Firewall-Gerät, das den heutigen direkten Pfad verhindert, ist nicht bestimmt. Firewallregeln wurden nicht pauschal geöffnet oder abgeschaltet.

## Hostseitige Korrektur

Die separate Erweiterung unter `relay-overlay/` stellt `host_ice_config_file` bereit. Die private Datei enthält einen TURN-Endpunkt und Namen von Umgebungsvariablen für Username/Credential. Der Loader prüft die URL, erlaubt genau einen TURN-Server entsprechend der installierten aiortc-Beschränkung und löst Secrets beim Prozessstart auf. Ohne Konfiguration bleibt der bestehende STUN-Default erhalten.

Die PeerConnection erhält STUN plus privaten TURN-Server; ein tatsächlich allokierter Relaykandidat wird im bestehenden Answer-SDP veröffentlicht. Der mobile Session-DTO bleibt im STUN-Vertrag. Android und iOS SDK 2.26 ersetzen mobile TURN-Authentisierung durch ServiceNow-OAuth. Ein normales coturn-Passwort darf deshalb dort nicht als wirksam durchgereicht vorausgesetzt werden.

Konfiguration ist kein Bereitschaftsnachweis. Benötigt wird ein öffentlich erreichbarer TURN-Dienst oder eigener öffentlicher Relayhost. Listener, Relay-Portbereich, Zertifikat, Credentials und Adressfamilien müssen passen. Ein lokaler TURN-Dienst hinter einem reinen HTTP-/Funnel-Pfad reicht nicht.

Hostseitiges TURN/TLS auf TCP 443 beschreibt Host → Relay. Das Telefon erreicht die publizierte Relayadresse weiterhin per UDP. Für vollständig UDP-gesperrte Telefonnetze wäre zusätzlich ein SDK-kompatibler mobiler TURN-TCP/TLS-Vertrag erforderlich. Die Erweiterung ist keine Zusage für jedes fremde Netz.

## Gemma-Latenz

| Abschnitt | Vorherige Probe | Jüngste Probe |
| --- | ---: | ---: |
| Bis Input-ready | 37,625 s | 45,172 s |
| Sitzungsstart | 3,547 s | 9,282 s |
| Modell-Prefill | 22,338 s | 22,494 s |
| Modell-Decode | 6,720 s | 5,878 s |
| Modell insgesamt | 29,057 s | 28,372 s |
| Rest außerhalb Modell | 8,568 s | 16,800 s |

Beide Fenster enthalten drei erfolgreiche Modellaufrufe. Die Zuordnung erfolgt nach isoliertem Zeitfenster und Reihenfolge, nicht anhand einer End-to-End-ID. CREATE-/START-Callbacks erklären den Anstieg des Sitzungsstarts nahezu vollständig. Der jüngste ReAct-Aufruf verarbeitet 12.195 Tokens in 17,035 Sekunden Prefill und 1,572 Sekunden Decode. Kein Beleg für neues Hidden Thinking oder einen Pollingfehler.

Historische Halogen-Messungen hatten andere Cache-Treffer: Ein damaliger Rückgang von 39,859 auf 19,594 Sekunden fiel mit mehr Cache-Tokens und weniger frisch verarbeiteten Tokens zusammen. Das ist kein kontrollierter Vergleich Halogen gegen Gemma. Die qualifizierten Gemma-Flags wurden nicht blind zurückgestellt und native Voice-Anweisungen nicht zur Beschleunigung gekürzt.

Für die nächste normale Dialogmessung empfehlen sich inhaltsfreie Zeitmarken für Bot CREATE/START, Queue, Prefill, Decode und Ready. Bestehende Bot-Request-IDs können innerhalb dieser Schicht pseudonymisiert korreliert werden. Umfangreiches Console-Tracing darf dafür nicht einfach eingeschaltet werden: Es enthält Prompt-/Antwortinhalte.

## Verbleibende Abnahme

1. Öffentliches Relay bereitstellen und private Credentials in den Native-Prozess injizieren.
2. Quellstand gegen Hashes übernehmen, Konfiguration prüfen und nur den eigenen Native-Prozess bei inaktiver Sitzung kontrolliert neu starten.
3. Tatsächliche TURN-Allokation und Relaykandidat nachweisen.
4. Android und iPhone über 5G und fremdes WLAN prüfen: Begrüßung, erster Turn, Folgeturn, Abschluss und neuer Anruf.
5. Ausgewähltes ICE-Paar, DTLS und Audio in beide Richtungen prüfen; HTTP 200 reicht nicht.
6. Frischen Zielimport des gesamten nativen Batches separat abnehmen.

Siehe `NEUINSTANZ-INSTALLATION-DE.md` einschließlich notwendiger lokaler Dienste und fehlender Basisquellen im bisherigen Overlay.

## Primärquellen

- [Tailscale Funnel](https://tailscale.com/docs/features/tailscale-funnel)
- [aiortc API](https://aiortc.readthedocs.io/en/latest/api.html)
- [WebRTC TURN](https://webrtc.org/getting-started/turn-server)
- [Cloudflare STUN-/TURN-Adressen](https://developers.cloudflare.com/realtime/turn/)
- [coturn Serverkonfiguration](https://github.com/coturn/coturn/wiki/turnserver)

SDK-Aussagen beruhen auf den lokal bereitgestellten SDKs 2.26; andere Versionen sind neu zu qualifizieren. Bibliotheksgrenzen wurden gegen installierte Quellen aiortc 1.15.0 und aioice 0.10.2 geprüft.
