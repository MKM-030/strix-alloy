# Strix Alloy – NPU-Praxistest auf dem BOSGAME M5

Stand: 1. Oktober 2026. Dieser Bericht dokumentiert neue Messungen auf dem Windows-Rechner, nicht die historischen Vergleichswerte aus dem Konzept. Ein nativer Flash-Next-MTP-Head wurde nicht auf die NPU portiert.

## Ergebnis

Die NPU funktioniert mit dem portablen FastFlowLM 1.0.7 und Qwen3-0.6B. Ein geladenes, inaktives NPU-Modell beeinflusste die GPU-Raten kaum. Kontinuierliche NPU-Hilfsanfragen kosteten dagegen rund 7 % GPU-Decode-Leistung. Der Modus „balanced“ senkte die NPU-Leistung, beseitigte die GPU-Einbuße aber nicht. Vier Sekunden Pause zwischen den NPU-Anfragen begrenzten den GPU-Verlust in dieser Probe auf ungefähr 2,1 % bei Serial und 3,1 % bei MTP. Dadurch wird weniger NPU-Arbeit pro Zeit erledigt; eine Beschleunigung gegenüber der allein arbeitenden GPU ist das nicht.

Es wurde kein neuer Produktionsstandard aktiviert. Insbesondere ist dies kein Nachweis eines funktionierenden oder schnelleren nativen NPU-MTP-Offloads.

## Prüfstand und Durchführung

| Eigenschaft | Tatsächlich verwendeter Stand |
|---|---|
| Hardware | BOSGAME M5, Ryzen AI Max+ 395, Radeon 8060S, 128-GiB-System |
| Grafiktreiber | 32.0.32015.2008; nicht geändert |
| NPU-Treiber | 32.0.20102.3930; `flm validate --json` meldet `ready: true` |
| GPU-Engine | Halogen 0.15.1, v2, über Strix-Alloy-Gateway auf Port 8840 |
| GPU-Kapazität / belegte Eingabe | 262144 Positionen / exakt 512 Tokens einschließlich Chattemplate |
| GPU-Ausgabe | Genau 128 Tokens, Temperatur 0, Thinking aus, Prefix-Cache aus |
| NPU-Runtime / Modell | FastFlowLM 1.0.7 portable / `qwen3:0.6b`, Kapazität 2048 |
| NPU-Endpunkt während Tests | Nur `127.0.0.1:52628`, CORS aus, Queue-Länge 1 |
| Git-Stand zu Beginn | `f221eaba0a34fa7503b663aa751fdcbe6f6863e4` |
| Durchgehend erhaltene GPU-Run-ID | `f09bc011fb454fbc8c66268da8d78181` |

Drei Versuchsreihen mit jeweils fünf Blöcken. Jeder Block enthält Serial und MTP bei NPU aus (vorher), NPU geladen, NPU mit Hilfsanfragen und NPU aus (nachher). Reihenfolge von Serial/MTP und geladen/aktiv alterniert. Insgesamt 120 gemessene GPU-Anfragen plus sechs ausgeschlossene GPU-Warmups. NPU-Start und Modell-Warmup liegen außerhalb der GPU-Messfenster. Die NPU erledigt einen synthetischen Nummerierungsauftrag, keine produktive Nebenaufgabe.

## GPU-Ergebnisse

Alle Raten sind Token/s. GPU-Decode-Raten sind aus den Engine-Phasen und der Windows/WSL-Zeitkalibrierung abgeleitet. Windows-Gesamtzeiten bleiben separat in den Rohdaten. „Kontrolle“ ist der Mittelwert der Vorher-/Nachher-Arme derselben Versuchsreihe; Prozentänderungen der ersten beiden Reihen stammen aus den gepaarten Blockvergleichen.

| NPU-Betrieb | GPU-Modus | Kontrolle: NPU aus | NPU nur geladen | NPU mit Hilfsanfragen | Änderung gegenüber Kontrolle |
|---|---|---:|---:|---:|---:|
| Performance, kontinuierlich | Serial | 36,68 | 36,87 | 33,89 | −7,61 % |
| Performance, kontinuierlich | MTP | 43,13 | 43,30 | 39,93 | −7,40 % |
| Balanced, kontinuierlich | Serial | 36,32 | 36,78 | 33,93 | −6,52 % |
| Balanced, kontinuierlich | MTP | 43,19 | 43,38 | 40,04 | −7,30 % |
| Performance, 4-s-Pause | Serial | ≈36,70 | ≈36,80 | ≈35,93 | ≈−2,1 % |
| Performance, 4-s-Pause | MTP | ≈43,33 | ≈43,29 | ≈42,00 | ≈−3,1 % |

Die Pausenreihe ist vollständig ausgeführt und ihre Integritätsprüfung bestanden. Ihre obigen Näherungswerte wurden aus den auf zwei Dezimalstellen gerundeten CLI-Messwerten rekonstruiert, weil der gesonderte Aggregationsaufruf vom Werkzeug blockiert wurde. Unrunde Rohwerte liegen weiterhin in `gpu-samples.jsonl`. Eine vollständige zusätzliche Überlappungs- und Tail-Latenzauswertung dieser Reihe wird nicht behauptet.

Keine Ausreißer wurden entfernt. Balanced enthält unter anderem einen langsamen Serial-Kontrollwert und eine längere aktive Serial-Anfrage. Auch die Pausenreihe enthält eine längere Serial-Anfrage. Kleine positive Unterschiede beim lediglich geladenen Modell sind kein nachgewiesener Speedup. Fünf Blöcke sind ein Screening, keine belastbare allgemeine p95-Garantie. Die vorab vorgeschlagenen strengen Durchsatz-/Latenzgrenzen sind nicht vollständig qualifiziert.

## NPU-Ergebnisse und Sicherheit

Im separaten Funktionstest bei weiterhin geladenem, aber nicht inferierendem GPU-Modell erzeugte Qwen3-0.6B dreimal jeweils 99 Tokens: 106,30 / 105,74 / 105,93 Token/s laut FLM-Decode-Timer; jeweils ungefähr 1,46 Sekunden gesamte HTTP-Anfrage. Das sind weder Flash-Next-Raten noch ein Qualitätsbenchmark. Die Beispielausgabe wiederholte teilweise falsche Zahlwörter; daraus folgt keine Empfehlung für produktive Antworten.

Unter kontinuierlicher gleichzeitiger GPU-Last erreichte die NPU gewichtet 96,75 Token/s im Performance-Modus (30 Lastanfragen, 3405 Ausgabetokens) und 76,64 Token/s in Balanced (26 Lastanfragen, 2893 Ausgabetokens). Diese Raten schließen Prefill und Pausen aus. Unterschiedliche Modell-Tokenraten werden nicht addiert. Die protokollierte HTTP-Anfrageüberlappung der kontinuierlichen Tests war nahezu vollständig; das ersetzt keine Hardware-Auslastungsspur.

Das bestehende GPU-Modell wurde nicht gestoppt oder neu geladen. Der zusätzliche Wächter prüfte physischen Speicher und Commit-Spielraum alle 0,1 Sekunden und hätte nur den eigenen NPU-Prozess unter 18 GiB beendet; Startzulassung ab 22 GiB. Die bestehenden Schutzmechanismen wurden nicht abgesenkt. Der GPU-Controller meldete als Minimum rund 35,78 GiB verfügbaren Windows-RAM; nach dem letzten Test rund 37,95 GiB. Kein Reservefehler trat auf. Abtastung ist keine harte momentane Speichergarantie.

Die generierten GPU-Texte waren innerhalb jeder vollständigen Versuchsreihe über alle Arme und beide Decode-Modi identisch. Die sechs Hilfstests für Reserveprüfung, Token-/Cache-Kontrollen, Quantile und unterbrechbare Pausen bestanden. Das ist nicht als neuer vollständiger Regressionstest sämtlicher strix-alloy-Komponenten ausgewiesen.

## Befunde, Grenzen und nächster sinnvoller Ansatz

Der erste Funktionstest scheiterte beim Wiederverwenden einer HTTP-Verbindung. Frische Verbindungen im Testclient beseitigten das beobachtete `ServerDisconnected`-Problem in den folgenden Läufen. FastFlowLM selbst wurde dafür nicht gepatcht. Der fehlgeschlagene Lauf bleibt in `smoke-01` erhalten.

Die Ergebnisse belegen Konkurrenz unter zusätzlicher NPU-Last, isolieren aber nicht deren Aufteilung auf Speicherbandbreite, Leistungsbudget, CPU-Arbeit oder Scheduling. Ein NPU-MTP-Drafter würde GPU-Draftarbeit ersetzen, während dieser Test zusätzliche unabhängige Arbeit erzeugt. Die gemessene Einbuße widerlegt daher nicht einen zukünftigen nativen Head-Split.

Die aktuelle Halogen-Antwort enthält Draft- und Akzeptanzzahlen, aber keine getrennten Draft-/Verify-Zeiten. Eine historische Draftquote von 16 % wird deshalb nicht als heutiges Zeitbudget eingesetzt. Für den nativen Head sind als nächste Nachweise getrennte aktuelle Phasenzeiten, korrekter Hidden-State-Vertrag und Head-only-Latenz erforderlich. Ein kleiner Chat-Server ist keine native MTP-Schnittstelle.

Das Anlegen der separaten binären IPC-Probe wurde durch das Werkzeug blockiert; sie wurde nicht ausgeführt. Es gibt keine neue GPU/NPU-Tensortransfermessung, keinen neuen Hidden-State-Replay-Nachweis und keinen NPU-Output-Head-Benchmark. Auch 2048-/8192-Token-Eingaben, tatsächlich gefüllte lange Kontexte, SSE/TTFT und echte ausgelagerte Fachaufgaben wurden in diesem Praxistest nicht qualifiziert.

Praktische Konsequenz: keine dauernde NPU-Vollast neben der latenzkritischen GPU als Standard. Ein geladenes Hilfsmodell mit begrenzter Hintergrundarbeit ist ein weiterer Kandidat; die Pausenprobe zeigt die Richtung, nicht eine breite Produktionsfreigabe. Für höhere Flash-Next-Token/s bleibt ein echter Head-only-Test beziehungsweise die unabhängige PROJFIX-MTP-Loader-Reparatur der relevante nächste technische Ansatz. Keine automatisch aktivierten Helfer und kein Cloud-Fallback.

## Dateien und Reproduktion

Lokales Versuchspaket: `C:\AI\reports\strix-alloy-npu-20261001`. Es enthält `run_probe.py`, `probe_core.py`, `test_probe_core.py`, `summarize_probe.py`, Treiber-/Validierungsnachweise und die Ordner `smoke-01`, `smoke-02`, `coexist-512-performance-01`, `coexist-512-balanced-01`, `coexist-512-gap4-01`. Die ersten beiden Vergleichsreihen besitzen `summary.json`; alle drei besitzen Rohdaten, `identity.json`, `result.json` und `cleanup.json`. Frühere Harness-Versionen der ersten beiden Reihen wurden nach SHA-256-Prüfung gesichert.

Portabler Runtime-Pfad: `C:\AI\runtimes\flm-1.0.7-npu-probe\portable`. Modellpfad: `C:\AI\models\flm-npu-probe`. Keine systemweite Installation oder PATH-Änderung. SHA-256 des offiziellen ZIP: `0377e501afe3595d491cde1ff91923f225240053437d6e55b47c6e86fadc54d8`. FLM prüfte die heruntergeladenen Modelldateien erfolgreich. Der Testclient ist auf diesen lokalen Prüfstand zugeschnitten, kein allgemeiner Fresh-Install-Installer.

Reproduktion aus dem Versuchspaket, bei unverändert bereitem Halogen und ohne andere Inferenzanfragen: `C:\Projects\strix-alloy-publication-20260929\server\.local\venv\Scripts\python.exe -B -u run_probe.py --reps 5 --size 512 --pmode performance --npu-gap 4 --out EIN_NEUER_AUSGABEORDNER`. Für die kontinuierlichen Kontrollen `--npu-gap 0` und wahlweise `--pmode balanced`. Ein vorhandener Ausgabeordner wird nicht überschrieben.

Nach dem letzten Test war der NPU-Port geschlossen, der GPU-Controller weiterhin READY, gleiche Run-ID, keine aktiven Anfragen und keine Wächterfehler. Es wurde kein NPU-Testprozess absichtlich weiterlaufen gelassen, kein Treiber/BIOS verändert und kein Modell-Endpunkt öffentlich freigegeben.

## Primärquellen für das verwendete Runtime-Verhalten

- FastFlowLM v1.0.7: https://github.com/ROCm/FastFlowLM/releases/tag/v1.0.7
- Windows-Voraussetzungen und NPU-Leistungsmodi: https://fastflowlm.com/docs/install_win/
- Server-Kontext, Queue und Ports: https://fastflowlm.com/docs/instructions/server/

Die Tabellen stammen aus den lokalen Messungen, nicht aus den Herstellerbenchmarks. Das ursprüngliche NPU-Konzept bleibt ein separater Plan; dieser Bericht ersetzt seine noch offenen Schritte nicht durch Erfolgsaussagen.
