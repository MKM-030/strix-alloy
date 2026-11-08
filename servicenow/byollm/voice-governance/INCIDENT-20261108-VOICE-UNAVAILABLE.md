# Voice nicht verfügbar am 8. November 2026

Stand: 8. November 2026, 20:40:54 MEZ (19:40:54 UTC). Das ausgewählte Halogen 0.19.1 ist wieder bereit. Die korrigierte Bereitschaftsanzeige ist in der Native Bridge aktiv und über den öffentlichen HTTPS-Zugang bestätigt. Ein neuer vollständiger iPhone-Dialog nach dieser Wiederherstellung ist noch nicht nachgewiesen.

## Beobachteter Fehler

Marcel meldete erneut: „Es passiert wieder nichts“. Das Native-Protokoll belegt am 8. November einen SDK-Aufruf mit Anfragekennung `1dfaee4a36bd`: Beginn um 20:31:07,400 MEZ, Antwort HTTP503 um 20:31:10,682 MEZ. Der Aufruf erreichte die lokale Bridge. Der vorhandene Protokolleintrag bezeichnet den Weg als `native_sdk`; er belegt allein weder die konkrete Geräteart noch einen begonnenen ServiceNow-Geschäftsdialog.

Die anschließende lesende Diagnose durch Root um 20:32–20:33 MEZ zeigte keine Controller-/Modell-Listener auf 8840 und 8731. Gleichzeitig antwortete die damalige Native-Gesundheitsprüfung mit HTTP200, `status=ok`, `nativeSessions=0`, `authMode=servicenow` und `asrReady=true`. Ein Feld zur Modellbereitschaft fehlte. Diese konkrete Statusbeobachtung liegt im Werkzeugprotokoll `f7303c`; dafür wurde keine eigenständige JSON-Belegdatei angelegt.

Der Quellstand bestätigt den Widerspruch: Die Gesprächserstellung prüfte bereits die Modellbereitschaft, die Gesundheitsroute dagegen nur die Spracherkennung. Eine erreichbare Bridge mit bereiter ASR wurde deshalb als gesund ausgewiesen, obwohl das für den Gesprächsstart benötigte Modell fehlte. Die neue Diagnose ergänzt außerdem den fehlenden Protokollschritt zur Unterscheidung von Modell- und ASR-Bereitschaftsfehlern. Der alte 503-Eintrag enthält diese Unterscheidung noch nicht.

## Ursache des fehlenden Modells

Der ursprüngliche äußere Controllerlauf `654d152776da452782f388a2aed8805d`, PID19368, endete am Morgen nach Unterschreitung der bestehenden 18-GiB-Speicherreserve. Sein Fehler lautet: `Windows physical/commit reserve crossed 18 GiB; cleanup: Halogen cleanup/recovery did not complete`.

Der zugehörige Backendlauf `11dbbf3d1ed342398e168c9b91456429`, PID24360, wurde beendet und räumte seinen Container auf. Das Ergebnis dokumentiert `cleanup=true`, aber `recovery=false`. Im Backendlauf existiert kein gesonderter `guard-failure.json`-Beleg: Die Reserveverletzung ist im äußeren Controller dokumentiert; der Backendfehler betrifft die danach fehlgeschlagene Speichererholung.

Die ursprüngliche Ausgangsbasis betrug 31,034324646 GiB freien physischen Speicher. Die unveränderte Erholungsregel verlangt fünf aufeinanderfolgende gültige Messungen mit mindestens 29,034324646 GiB freiem Speicher und 18 GiB Commit-Spielraum. Nach 180 Messungen lag der letzte Wert nur bei 24,1008 GiB. Daher blieb die Besitzsperre erhalten und verhinderte einen ungeprüften weiteren Start. Welcher andere Speicherverbrauch die Reserveverletzung verursachte, ist durch diese Belege nicht bestimmt.

## Implementierte Korrektur

Quellcommit `4f249f53fd41ecec2b9730eee9a40642d5c8820d` ändert `voice/native-bridge/native_bridge.py`:

- `/health` prüft nun die konfigurierte Modellverbindung und meldet `modelReady` zusätzlich zur unabhängigen ASR-Bereitschaft.
- Bei einer fehlenden benötigten Abhängigkeit lautet der Gesamtstatus `unavailable` mit HTTP503. `bridgeAlive=true` bezeichnet weiterhin die erreichbare Bridge.
- Die Gesprächserstellung protokolliert die fehlgeschlagene Phase als `model_readiness` oder `asr_readiness`, ohne private Verbindungsdetails oder Nutzerinhalte auszugeben.

`voice/native-bridge/test_native_readiness.py` deckt fehlendes Modell bei bereiter ASR, vollständige Bereitschaft, fehlende ASR bei bereitem Modell sowie beide Ablehnungen beim SDK-Gesprächsstart ab. Die Prüfungen verwenden die realen lokalen Anwendungsrouten mit nachgebildeten Abhängigkeiten; sie sind kein Nachweis akustischer Qualität oder eines ServiceNow-Geschäftsabschlusses.

Commit `b0daa02` bindet den geänderten Native-Quellstand in die bestehende Startprüfung ein. `pin-refresh.json` dokumentiert ausschließlich den geänderten Artefakteintrag `native_bridge`; alle anderen Einträge blieben erhalten. Die Manifest-Prüfsumme änderte sich von `464817c0014f760dd1985fa09778d03971395530b43f2e086bf31f4e100f64da` auf `60933a24f8f8a4993d6e3638b5d01cda2f904e0f2d9b7b75abc8b96eb692141a`.

## Tatsächliche Wiederherstellung und Aktivierung

Um 20:36:40 MEZ wurde genau ein neuer Wiederherstellungsversuch verbraucht. Vor der Archivierung wurden die fehlenden alten Besitzer, der beendete zugehörige Container, die unveränderten Belege und die zentral ausgewählte Profilprüfsumme geprüft. Elf neue Speichermessungen erfüllten sowohl die ursprüngliche Erholungsregel als auch die normalen Startgrenzen 30 GiB physisch/131 GiB Commit. Die niedrigsten Werte waren 30,9002 GiB bzw. 183,5046 GiB. Die 18-GiB-Laufzeitreserve blieb bestehen.

Die exakte alte Sperre wurde innerhalb ihres ursprünglichen Laufverzeichnisses als `runner.lock.late-recovery-20261108` archiviert. Die ursprünglichen Fehler- und Erholungsbelege wurden nicht umgeschrieben; insbesondere bleibt das historische `recovery=false` erhalten. `recovery-start.SPENT.json` hält den einmaligen Vorgang fest und darf nicht als wiederverwendbare Startfreigabe behandelt werden.

Der reguläre Modellstart verwendete weiterhin das zentral ausgewählte Profil `serving0191-text32k-one-slot-2048.json`, SHA256 `69b91ddae6daa21b7c4d7666077847e4913fd9b59aedd149201c9d0ccd994b84`. Das inzwischen installierte 0.20.0 wurde nicht ausgewählt. Der neue Controller PID17228/Lauf `d45de059cc5b4c2fbb7011ad53ebbff9` und das Backend PID29472/Lauf `5841121582184fb0a9108097d17849fc` waren zunächst im Start; `model-ready.json` belegt die tatsächlich erreichte Bereitschaft um 20:39:58 MEZ. Die bestehenden Bridge-, Gateway-, Bot- und Sprachdienstgenerationen wurden während dieses Modellstarts erhalten.

Anschließend wurde ausschließlich die unbenutzte Native Bridge einmal über den bestehenden Startmechanismus neu geladen, um die korrigierte Gesundheitsroute zu aktivieren. `native-readiness-activation.json` belegt um 20:40:33 MEZ den neuen Native-Prozess PID20632, HTTP200, `bridgeAlive=true`, `modelReady=true`, `asrReady=true`, `nativeSessions=0` und `authMode=servicenow`. Alle anderen beobachteten Dienstgenerationen, die Quellbindungen und die Einstellungen blieben erhalten. Die nicht angemeldete Text-Route lieferte weiterhin HTTP401. `native-readiness-reload.SPENT.json` ist ebenfalls verbraucht.

Die abschließende öffentliche HTTPS-Prüfung um 20:40:54 MEZ antwortete nach 2,422 Sekunden mit HTTP200 und ebenfalls `bridgeAlive=true`, `modelReady=true`, `asrReady=true` sowie null Sitzungen. `public-ready.json` dokumentiert diese reine Statusabfrage ohne Inferenz.

## ServiceNow und offene Abnahme

Diese Korrektur änderte ausschließlich die lokale Bridge, ihre Quellbindung und den lokalen Laufzustand. Es wurden hierfür keine ServiceNow-Artefakte, Capability-/Modellzuordnungen, Zugriffsregeln oder Customer Updates angelegt oder geändert. Die eigene Stimme, die Assistentenkonfiguration und ServiceNow als fachlicher Ausführer bleiben maßgeblich.

Die Aktivierungsprüfung erzeugte keinen Voice-Dialog, keine Audioaufnahme und keine fachliche ServiceNow-Anfrage. Die Statusprüfung belegt erreichbare und bereite Abhängigkeiten; sie belegt noch kein hörbares natürliches Gespräch auf dem iPhone. Offen bleiben der tatsächliche neue Dialog, Namenserkennung und gezielte Rückfragen, vollständige hörbare eigene TTS bei wiederholten Anrufen, sinnvolle Fortsetzung des ServiceNow-Ablaufs sowie Gerätegleichheit. Agententests stoppen an jeder Bestellfreigabe.

Private Belege: `server/.local/voice-repair-20261102/task99-runtime-unavailable-20261108/` mit `recovery-start.SPENT.json`, `model-ready.json`, `pin-refresh.json`, `native-readiness-reload.SPENT.json`, `native-readiness-activation.json` und `public-ready.json`. Der ursprüngliche SDK-503 steht in `voice/native-start/runtime/native.stderr.log`. Originale Backendbelege liegen unter `backends/halogen-wsl2-0.19.1/.local/services/11dbbf3d1ed342398e168c9b91456429/`.
