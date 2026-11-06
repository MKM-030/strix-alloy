# Voice-Start vom 6. November 2026 erreicht die Bridge nicht

Instanz: `soprasteriaassvsdemo14`. Assistant: `8aa131d793f787105c8132d47aba1095`. Dieser Vorfall ist vom [früheren iPhone-Dialogfehler](INCIDENT-20261106-IPHONETEST.md) getrennt: Beim neuen Start entstand keine lokale Voice-Sitzung und kein neues ServiceNow-Gespräch.

**Ergebnis um 21:55 UTC:** Der öffentliche Zugang antwortet wieder. Eine neue Prüfung aus ServiceNow erhielt HTTP200 / `status:ok` in **684 ms**. Der öffentliche Einstiegslink lieferte in 297 ms die erwartete Weiterleitung zum richtigen Assistant. Konto, Einstellungen, fünf Weiterleitungen und alle zwölf Modell-/Voice-Prozessidentitäten blieben unverändert. Dies bestätigt den Transport; ein neues hörbares Gerätegespräch ist weiterhin offen.

## Nachgewiesene Fehlergrenze

Die lokale Native-Bridge antwortete mit HTTP200, null Sitzungen und bereiter Spracherkennung. Der bereits gewählte Halogen und die vorhandenen Sprachdienste waren bereit. Derselbe HTTPS-Hostname lieferte über die Tailnet-Adresse `100.103.94.78` eine vertrauenswürdig geprüfte TLS1.3-Verbindung und HTTP200 in 47 ms. Sein Zertifikat war bis 28. Dezember 2026 gültig.

Über alle drei öffentlichen DNS-Ziele gelang dagegen nur der TCP-Aufbau auf443; der TLS-Handshake lief ins Zeitlimit. Auch der Hintergrundbrowser erreichte die öffentliche Health-Seite nicht. Damit liegt der nachgewiesene Abbruch vor Native und vor einem möglichen ServiceNow-Geschäftsdialog. Gesunde lokale Statuswerte belegen keine öffentliche Erreichbarkeit.

Eine einzelne Prüfung **aus ServiceNow** erhielt ebenfalls keine HTTP-Antwort: Status0, leerer Inhalt,10358ms bei10Sekunden HTTP-Zeitlimit. Die SDK-Ausführung selbst war erfolgreich. [Ausführungshistorie](https://soprasteriaassvsdemo14.service-now.com/sys_script_execution_history.do?sys_id=67dbf78393dcd394e7f2b9fa6aba10fb). Diese Prüfung enthielt genau einen unauthentifizierten GET auf `/scc-native/health`, keine Audiodaten, Anmeldung, Sitzung, Modellanfrage oder fachliche Aktion. Status0 allein benennt keine bestimmte TLS-Ursache; er bestätigt zusammen mit den unabhängigen Verbindungsprüfungen die fehlende externe Erreichbarkeit.

Die begrenzte ServiceNow-Nachlesung fand seit21:10UTC weder ein neues Gespräch noch eine neue Interaktion oder Voice-/OAuth-Transaktion. Acht Mobile-Route-Ereignisse um21:18:28–30UTC meldeten gültige lokale Route, Freigabe und Endpoints. Daraus wird keine erfolgreiche nachgelagerte Autorisierung abgeleitet. Ein lokaler `/launch`-Diagnoseaufruf um22:32:31MEZ stammt vom Agenten, nicht vom Nutzer. ServiceNow- und Windows-Uhren sind versetzt; Laufzeiten werden nur innerhalb derselben Uhr verglichen.

## Erhaltener Umfang

| Pfad | Vorhandenes lokales Ziel |
|---|---|
| `/` | `http://127.0.0.1:8841` |
| `/scc-native` | `http://127.0.0.1:8860` |
| `/scc-voice` | `http://127.0.0.1:8853` |
| `/scc-demo` | `http://127.0.0.1:8854` |
| `/voice-studio` | `http://127.0.0.1:8863` |

Die vollständigen `TCP`, `Web` und `AllowFunnel`-Strukturen wurden vor Eingriffen gesichert. Auch der bereits vorhandene AllowFunnel-Eintrag10000 wurde erhalten. Es wurde kein neuer Port oder Dienst veröffentlicht.

Halogen-Controller20840, Backend21368, Launcher6572 sowie Native23008/26724, TTS5644, ASR16592/27560, Bot20180/24504 und Gateway21028/24336 wurden jeweils mit ihrer Erstellungszeit verglichen. ServiceNow bleibt Quelle für Begrüßung, Sprache, Stimme und Modellzuordnung sowie alleiniger fachlicher Ausführer. Die sechs Task94-Customer-Updates und die frühere Dokumentation wurden nicht erneut installiert.

## Durchgeführte Transportdiagnose

1. Ein normaler Neustart ausschließlich des Windows-Dienstes `Tailscale` wurde versucht. Windows verweigerte das Öffnen des Dienstes. **Es erfolgte kein Neustart und keine Rechteumgehung.**
2. Ein unterstütztes `debug rebind` wurde einmal ausgeführt. Die öffentliche TLS-Verbindung blieb gestört; alle Weiterleitungen und zwölf Modell-/Voice-Prozessidentitäten blieben erhalten.
3. Ein unterstütztes `debug break-derp-conns` wurde einmal ausgeführt. Die öffentliche TLS-Verbindung blieb gestört. Der aktuelle Netzwerkstatus meldete weiterhin Running/Online ohne Health-Warnung. Diese Meldung beweist keine funktionierende Funnel-Verbindung.

Die Diagnose stellte aktive Control-/DERP-Verbindungen und einen laufenden Control-Map-Leser fest. Eine veraltete Funnel-Registrierung oder eine andere Störung zwischen öffentlichem Relay und Gerät blieb als Ursache offen; ein globaler Tailscale-Ausfall wurde nicht behauptet. `break-tcp-conns` wurde nach Quellenprüfung **nicht** ausgeführt, weil diese Version für Windows keine Implementierung besitzt.

4. Der installierte Tailscale-Client 1.104.1 dokumentiert, dass `up` **ohne Optionen** die bestehenden Einstellungen unverändert wieder aktiviert. Nach frischen Leerlauf-, Konto-, Einstellungs-, Routen- und Prozessprüfungen wurde um 21:50:02 UTC genau einmal die reguläre Folge `down` → `up` ausgeführt. Beide Befehle endeten erfolgreich. Der vollständige Preferences-Snapshot, Serve/Funnel-Konfiguration und Knotenidentität waren anschließend identisch; alle zwölf Modell-/Voice-Prozessidentitäten blieben erhalten. Keine Anmeldung, kein Logout, kein Reset und keine neuen Optionen.

Die unmittelbar folgende öffentliche Prüfung hatte noch einen TLS-Timeout. Um 21:53:39 UTC antwortete derselbe öffentliche Health-Endpunkt ohne weiteren Eingriff mit HTTP200 / `status:ok` in 1,594 Sekunden. Gleichzeitig stieg der Ingress-Zähler von 281 auf 282. Die folgende öffentliche `/launch`-Prüfung lieferte HTTP302 in 297 ms, `Cache-Control: no-store` und exakt die erwartete ServiceNow-Voice-Test-Adresse.

Die unabhängige neue [ServiceNow-Ausführung](https://soprasteriaassvsdemo14.service-now.com/sys_script_execution_history.do?sys_id=cf8e3fc393101794e7f2b9fa6aba1065) bestätigte HTTP200 / `status:ok` in 684 ms, null Native-Sitzungen, bereite ASR und aktivierten nativen SDK-Pfad. Sie verwendete einen neu erstellten einmaligen Prüfhelfer; der erste verbrauchte Helfer wurde nicht wiederholt. Beide sind als **SPENT** markiert.

Damit ist die öffentliche Erreichbarkeit nach der regulären Wiederverbindung nachgewiesen. Ob eine verzögerte Aktualisierung am Relay, der Aufbau der Peer-Verbindung oder ein anderer transienter Zustand die Verzögerung verursacht hat, ist nicht abschließend bewiesen. Die Wiederverbindung darf deshalb nicht als pauschale automatische Reparatur oder als Modellstartrezept hinterlegt werden.

Die nachfolgende Prüfung der Tunnel-Voraussetzungen ergab passende PeerAPI-Ports, 23 Funnel-Ingress-Peers und vorhandene passende Ingress-Berechtigungen. Das Fehlen von `IngressEnabled` im zurückgegebenen Self-Hostinfo wurde nicht als Fehler ausgelegt. `debug hostinfo` erzeugt außerdem einen neuen Snapshot im CLI-Prozess und ist keine verlässliche Ansicht der Anmeldung des Dienstes. In der schreibgeschützt angesehenen NetLimiter-Regelliste waren keine Blocker-Regeln sichtbar; Blocker On war nicht aktiviert. Filter und Sicherheitsregeln wurden nicht geändert.

## ServiceNow und Update Sets

Dieser Transportvorfall änderte keine ServiceNow-Konfiguration und erzeugte keine fachlichen Customer Updates. Die SDK-Diagnose erzeugte lediglich ihre normale Ausführungshistorie und technische Protokolle. Es wurden keine ACLs, Rollen, Voice-Einstellungen, Promptbindungen, Modellhistorien oder Update-Set-Payloads verändert. Die bisherigen Artefaktbeschreibungen bleiben im [Änderungskatalog](CHANGELOG-20261106.md) und im früheren iPhone-Vorfall dokumentiert.

## Belege und Grenzen

Lokales Belegpaket: `C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102/task96-voice-entry-20261106-v1`. Es enthält DNS-/TLS-Vergleiche, unveränderte Routen, Prozessidentitäten, beide ServiceNow-Prüfungen und einmalige Aktionsbelege. Die wesentlichen Abschlussdateien sind `normal-network-reconnect-action.json`, `public-probe-correlated-ingress.json`, `restored-launch-and-preservation.json` und `public-health-once.v2.SPENT.json`. Private Rohdateien werden nicht als allgemeine Produktdokumentation veröffentlicht. Verbrauchte Aktionshelfer dürfen nicht wiederholt werden.

Die erfolgreichen öffentlichen Health-Aufrufe bestätigen den Transport. Hörbare Begrüßung, natürliches Gespräch mit Korrektur, der tatsächliche Prompt-Konfigurationsfehler, vollständiger Prozessabschluss und Gleichheit auf iPhone/Android/Desktop benötigen weiterhin echte Gerätedaten. Es wurden keine Mikrofonaufnahme, Audiodatenübertragung, Testbestellung oder zusätzlichen Inferenzgespräche ausgeführt. Der unauthentifizierte Gateway-Aufruf wurde erwartungsgemäß mit HTTP401 abgewiesen; er wird nicht als positiver Modell-Bereitschaftsnachweis gezählt.

Herstellerquellen: [Funnel-Verbindungsweg](https://tailscale.com/docs/features/tailscale-funnel#how-funnel-works), [DERP-Wiederverbindung in1.104.1](https://github.com/tailscale/tailscale/blob/v1.104.1/wgengine/magicsock/derp.go#L835), [Verhalten von up ohne Optionen](https://github.com/tailscale/tailscale/blob/v1.104.1/cmd/tailscale/cli/up.go#L49).
