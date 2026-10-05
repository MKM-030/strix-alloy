# NPU: Genauigkeit und tatsächlicher Nutzen

Der laufende Server bleibt beim ursprünglichen GPU-MTP-Pfad. Für die aktuelle
NPU-Auslagerung ist kein positiver Nutzen im vollständigen Engine-Lauf
nachgewiesen. Die Änderung in Prefill-tok/s, Decode-tok/s und Akzeptanz ist
weiterhin unbekannt. Aus den Zeiten einzelner Komponenten lässt sich dieser
Unterschied nicht ableiten.

Die getestete MTP-Projektionskomponente besteht nach der Korrektur die
unveränderte Entwicklungstoleranz `rtol=0.03, atol=0.003`: keine Überschreitung
auf beiden eingefrorenen Eingabesätzen in zwölf NPU-Aufrufen. Dafür werden
Aktivierungen und Gewichte in einen stabilen Hauptanteil und einen Rest
zerlegt. Die BF16-Ausgabegrenzen bleiben erhalten. Das ist keine vollständige
Modell-, Logit- oder MTP-Vorschlagsprüfung; die strengere CPU-Prüfung hat noch
eine Abweichung. Der Live-Austausch bleibt deshalb geschlossen.

Die inzwischen separat geprüfte **Embedding-Projektion** besteht beide
unveränderten Grenzen: CPU `rtol=0.002, atol=0.0002` und NPU
`rtol=0.03, atol=0.003`. Je zwölf wechselnde A/B-Aufrufe überschreiten keinen
Wert. Der NPU-Kontext belegt alle neun dynamischen Graphwerte auf STX-Hardware,
und das Profil belegt zwölf VitisAI-Ausführungen ohne CPU-Fallback.
Die Ausgabe ist innerhalb der Toleranz, nicht bitgleich: auf der NPU unterscheiden
sich 858/847 BF16-Wörter von der nativen GPU-Referenz. Die offene strengere
Hidden-Prüfung wurde dadurch nicht repariert oder umgangen.

Für diesen kleineren Zweig wurden **0,9674 ms** reine NPU-Session und
**2,1048 ms** einschließlich frischer Vorbereitung und Diagnose gemessen.
Das ist eine einzelne Embedding-Projektion; die folgende ältere Vergleichszeile
umfasst beide Projektionen. Es gibt weiterhin keinen vollständigen Engine-Lauf
mit NPU-Ersatz und keinen gemessenen NPU-Gewinn in tok/s.
[Ausgeführte CPU- und NPU-Prüfung](../research/halogen-npu-early-embedding-component-20261005.md).

Der am 5. Oktober zusätzlich geprüfte Kandidat mit kompensierter Addition
repariert diese strengere Prüfung nicht: Die ursprüngliche Abweichung bleibt,
und ein weiterer Wert überschreitet die unveränderte CPU-Toleranz. Er wird
nicht übernommen und wurde wegen der fehlgeschlagenen CPU-Voraussetzung
nicht auf der NPU gestartet. Die zuvor bestandene NPU-Entwicklungstoleranz
wurde weder erweitert noch durch den neuen Kandidaten ersetzt.
[Ausgeführter Genauigkeitsvergleich](../research/halogen-npu-compensated-split-20261005.md).

| Dieselbe gepaarte Projektion | Gemessene Zeit |
|---|---:|
| GPU, Host-Aufruf mit Warten | 0,487 ms |
| Korrigierte NPU, nur Session-Ausführung | 1,850 ms |
| NPU einschließlich Vorbereitung und Diagnose | 3,540 ms |

Schon die reine NPU-Ausführung dauert etwa 3,8-mal so lange. Live-Transport
zwischen Windows und WSL ist dabei noch nicht enthalten. Diese Auslagerung
bleibt deaktiviert. Am vorhandenen Einhängepunkt stehen die normierten
Eingaben erst nach dem Trunk bereit; sie können dort nicht während desselben
Trunk-Prefills vorbereitet werden. Eine frühere tokenbasierte Vorbereitung ist
jetzt als begrenzter Offline-Eingabeproduzent implementiert. Ihre Planung wurde
ausgeführt; inzwischen ist auch die Produktion von 64 ausgewählten
Checkpoint-Embedding-Zeilen abgeschlossen. Live-Veröffentlichung und
Tempo-Vorteil sind weiterhin unqualifiziert.

| Neueste normale GPU-Kontrolle | Prefill tok/s | MTP-Decode tok/s | Akzeptanz |
|---|---:|---:|---:|
| GPU, 8.192 Eingabe / 128 Ausgabe | 1.277,14 | 41,28 | 60,0 % (207/345) |
| NPU-Auslagerung im vollständigen Engine | nicht gemessen | nicht gemessen | nicht gemessen |

Die neueste Stock-Kontrolle endete am 5. Oktober 2026 um 02:43:05 UTC. Sie nutzt einen
eingefrorenen, nicht repetitiven synthetischen Wortmix aus einem kleinen
Wortschatz, erzeugt mit festem Zufallsseed. Es gab einen Aufwärmlauf und drei
Messläufe mit Cache Off, MTP-Tiefe 2 und PLD 3,3. Die frühere Spitze von
48,42 Decode-tok/s wurde ebenfalls ohne NPU gemessen. Der Unterschied zum
obigen Lauf ist kein NPU-an/aus-Effekt. Es gibt bislang keinen belegten
NPU-Gewinn in Prefill- oder Decode-tok/s. Komponenten-Millisekunden werden
nicht in Tokenraten umgerechnet.

Die neuen langen Eingaben aus einem einmal verwendeten Romanpräfix bilden
einen anderen Workload. Ihre Tokenraten und Akzeptanz können deshalb nicht als
direkter Leistungsunterschied zu dieser synthetischen 8K-Kontrolle berichtet
werden.

Der neue Vergleich der n-gram-Dateiablage ergab für Stock A **1.321,26 / 41,62**,
für native WSL-Ablage **1.316,04 / 41,90** und für Stock B **1.277,14 / 41,28**
Prefill-/Decode-tok/s. Akzeptanz und Ausgaben bleiben gleich. Die native Ablage
überschreitet die Schwankung der beiden Kontrollen nicht zuverlässig und bleibt
für dieses normale 8K-Profil deaktiviert. Der Server ist wieder bereit und
bleibt offen. [Vollständige Kohorte](halogen0162-native-lookup-stock8k-20261005.md).

Ein früherer echter GPU/NPU-Koexistenztest auf Halogen 0.15.1 mit 512 Eingabe-
und 128 Ausgabetokens zeigte den Effekt eines separaten NPU-Helfers:
MTP-Decode sank bei kontinuierlichen Hilfsanfragen von **43,13 auf 39,93 tok/s**,
also um rund **3,20 tok/s beziehungsweise 7,4 %**. Der Helfer ersetzte dabei
keinen Teil des MTP-Heads. Dieser ältere, anders aufgebaute Versuch ist kein
NPU-an/aus-Vergleich der aktuellen 0.16.2-Projektion. Er begründet, einen ständig
aktiven Helfer ebenfalls nicht als Beschleunigung zu aktivieren.
[Gemessene Koexistenz](../research/npu-coexistence-measured-20261001.md).

Ein separater CPU-Runtime-Patch wurde ohne NPU mit demselben Workload geprüft.
Er erreichte 1.356,50 Prefill- und 42,39 Decode-tok/s. Gegenüber den beiden
Original-Kontrollen entspricht das +16,11 bis +38,73 Prefill-tok/s und +0,59
bis +0,74 Decode-tok/s. Gegenüber dem aus derselben Quelle gebauten ungepatchten
Runtime sind es +44,20 und +0,42 tok/s. Alle Ausgaben stimmen exakt überein;
die Akzeptanz bleibt bei 60 %. Das sind kleine beobachtete Unterschiede in
einer Kohorte, keine allgemeine Leistungszusage oder NPU-Beschleunigung.
Die Phasenraten wurden gegen die Windows-Uhr kalibriert. Das ursprüngliche
GPU-Profil ist danach bereit und offen geblieben; der Patch ist ein opt-in
Kandidat. [Vollständiger Runtime-Vergleich](halogen0162-rocr-stock8k-20261005.md).

Die Kontextkapazität beträgt **262.144 Positionen**. Im neuen Roman-Workload
bestätigen native Timings und Usage tatsächlich **131.072 Eingabe- und 128
Ausgabetokens** für einen einzelnen Aufwärmlauf. Der Lauf endete mit `length`,
ohne Cache-Tokens und ohne Reasoning-Tokens.

| Einzel-Aufwärmlauf; keine qualifizierte Messkohorte | Prefill tok/s | MTP-Decode tok/s | Akzeptanz |
|---|---:|---:|---:|
| GPU, 131.072 Eingabe / 128 Ausgabe | 664,99 | 27,59 | 48,84 % (63/129) |

Die Phasenraten sind gegen die Windows-Uhr kalibriert; die Windows-Wandzeit
beträgt 202,056 s. Das Verhältnis monotonic/raw ist 1,024663, raw/QPC
1,000000103; die Handshake-Unsicherheit beträgt 0,502 ms. **Die Kohorte ist
fehlgeschlagen (`passed=false`): ein ausgeschlossener Aufwärmlauf, null
Messwiederholungen.** Nach dem Aufwärmlauf wurde die nächste Anfrage mit
`RuntimeError: 22 GiB physical/commit reserve unavailable` nicht zugelassen.
Die aggregierten Prefill-, Decode- und Akzeptanzwerte sind deshalb `null`;
die Tabellenwerte sind keine Mittelwerte. Die beobachteten Minima von
21,624 GiB freiem physischem Speicher und 114,470 GiB Commit-Reserve blieben
über der kontinuierlichen 18-GiB-Untergrenze. Diese Untergrenze ersetzt die
22-GiB-Zulassung vor einer neuen Anfrage nicht. **260.000 Eingabetokens wurden
nicht gestartet.** Der Server blieb offen und wurde abschließend als bereit
und im Leerlauf bestätigt; NPU-Auslagerung war nicht integriert.
[Fehlgeschlagene Langtext-Kohorte](../../server/.local/long-input-admission-source-20261005/measurement-422ad410db5145b081cec88daa5c5967/131072/result.json),
SHA-256 `e6b8237e440d4c425ac704c2be2ef610051178d0790374fb55bc0643a50fed1a`;
[einzelner Aufwärmlauf](../../server/.local/long-input-admission-source-20261005/measurement-422ad410db5145b081cec88daa5c5967/131072/samples.json).

Für die aktuelle 0.16.2-Engine ist der Unterschied durch eine NPU-Auslagerung
in **Prefill-tok/s, Decode-tok/s und Akzeptanz weiterhin nicht gemessen**.
Der Live-Server verwendet den ursprünglichen GPU-MTP-Pfad; es gibt keinen
NPU-Anteil, dem seine Tokenrate zugerechnet werden kann. Die Entscheidung ist
daher: synchrone FC-Auslagerung und ständig laufenden Helfer deaktiviert lassen.
Eine frühe tokenbasierte NPU-Vorbereitung darf erst nach korrekter nativer
Eingabelinie und einem vollständigen, vergleichbaren Engine-An/Aus-Vergleich
aktiviert werden. Ein komponentenweiser Genauigkeitsnachweis allein genügt
dafür nicht.

Ein neuer kleiner Original-GPU-Vergleich hat am 5. Oktober um 03:34:43 UTC die
ausgewählte Token-Embedding-Zeile bestanden: Beide originalen Q4C-Decoder und
der anschließende Gather liefern alle 2.560 BF16-Werte exakt wie die eingefrorene
Referenz. Es wurde nur die ausgewählte Zeile umgepackt und eine eigene kleine
GPU-Tabelle verwendet. Dieser Beleg qualifiziert weder die Tabelle im laufenden
Engine noch andere Tokens, den vollständigen MTP-Head oder einen Tempo-Gewinn.
Die frühe NPU-Vorbereitung bleibt im Live-Engine deaktiviert. Der neue
Offline-Produzent hat inzwischen **64 ausgewählte Token-Embedding-Zeilen aus
dem realen Checkpoint** erstellt. Die abgeschlossene Produktion las genau
**194.688 Checkpointbytes**; die vollständige Checkpointdatei wurde nicht erneut
gehasht, und es wurden keine FC-Gewichte gelesen. Dieser Lauf führte weder
CPU- noch NPU-FC aus, lud keine Kandidaten auf ein Gerät und veröffentlichte
keine Daten im Live-Engine. Er belegt Kandidaten-Eingaben, keinen vollständigen
MTP-Head und keinen Tempo-Vorteil. Für unbekannte und zurückgestellte Tokens
bleibt der ursprüngliche GPU-Pfad vorgeschrieben.
[Abgeschlossene 64-Zeilen-Produktion](../../server/.local/optimization9h-20261004/early64-candidates-40e19242264d414e91a2570f8e964e0e/complete.json),
SHA-256 `0cbdf9b414840b7c2a3ed1be079faef5d68e3770e836c1be99251332e8dfb563`.
[Ausgeführter Embedding-Vergleich](../research/halogen-q4c-selected-row-oracle-20261005.md).

Die anschließende CPU-RMS-Korrektur folgt der GPU-Reihenfolge für die
eingefrorenen rohen Embedding-Zeilen. Sie stimmt auf **64 Zeilen mit jeweils
2.560 Werten (163.840 insgesamt)** exakt mit den erhaltenen nativen
GPU-Ausgaben überein: null unterschiedliche BF16-Wörter, null Überschreitungen
der ursprünglichen CPU-Toleranz `rtol=0.002, atol=0.0002`, maximale absolute
Abweichung null. Die Toleranz blieb unverändert. Der Vergleich selbst führte
weder GPU noch NPU aus und ließ keine Live-Veröffentlichung zu. Dieser
64-Zeilen-Beleg qualifiziert weder die vollständige Tabelle, Live-Allokation,
FC oder den vollständigen MTP-Head noch zukünftige Zeilen oder einen
Tempo-Gewinn. Die separate offene Hidden-/MTP-Projektionsprüfung bleibt davon
unberührt.
[CPU-RMS-Korrektur auf 64 Zeilen](../../server/.local/optimization9h-20261004/q4c-multirow-owned-35bf1b51d916442b8101605ab80b6dcc/cpu-tree-original-tolerance.json),
SHA-256 `233d5c97c85e1e923956b50401a1ba091159438ec1f3f79a17b89626ec5f5711`;
Quell-SHA-256 `ff635c3f295a7044dd388aa9699146c3f752e74c393fcc2dea7af1d02a479185`.
Der ursprüngliche NumPy-/Kandidatenlauf bleibt als fehlgeschlagen erhalten
(`passed=false`, `exact-BF16-word-gate`). Sein ergänzender Toleranzvergleich
enthält zwei BF16-Wortunterschiede und zwei Überschreitungen der ursprünglichen
CPU-Toleranz bei maximal 0,001953125 absoluter Abweichung; er war keine
bestandene exakte Parität und kein NPU-Lauf.
[Ursprüngliches fehlgeschlagenes Gate](../../server/.local/optimization9h-20261004/q4c-multirow-owned-35bf1b51d916442b8101605ab80b6dcc/result/replay/replay.json),
[ergänzender Toleranzbeleg](../../server/.local/optimization9h-20261004/q4c-multirow-owned-35bf1b51d916442b8101605ab80b6dcc/supplemental-normalized-tolerance.json).

Unterstützter gleichzeitiger GPU/NPU-Betrieb setzt laut aktuellen
[Halogen-Flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/main/docs/FLAGS.md)
einen gehaltenen Fabric-Takt voraus. Der neue Windows-Collector wurde gebaut
und einmal ausgeführt; er liest GPU-Node- und Speicherfrequenz, belegt aber
keinen Fabric-Takt oder gehaltenen Zustand. Der Server blieb unverändert bereit;
alle neuen NPU-Aufrufe fanden im überwachten GPU-Leerlauf statt.

Belege: [Genauigkeitskorrektur](../research/halogen-npu-precision-correction-20261004.md),
[CPU-/Paging-Kontrolle](../research/halogen-cpu-paging-control-20261005.md),
[NPU-Batch-Aufrufprüfung](../research/halogen-npu-batch-cut-source-disposition-20261005.md).

Die portable Python-3.12-Implementierung der RMS-Korrektur wurde ebenfalls auf
allen 163.840 gespeicherten Werten ausgeführt: exakt null BF16-Abweichungen bei
unveränderten Toleranzen. Der neue Offline-Adapter bindet diese Implementierung
explizit mit `--native-rms`; seine erneute Checkpoint-Produktion wurde noch nicht
gestartet. [Implementierung](../../scripts/benchmarks/halogen0162_embedding_rms_cpu_tree_portable.py),
[ausgeführter Vergleich](../../server/.local/optimization9h-20261004/q4c-multirow-owned-35bf1b51d916442b8101605ab80b6dcc/cpu-tree-portable-original-tolerance.json).

Für die langen Messungen ist ein Profil mit `prefill_chunk=8192`, weiter
262.144 Kontextpositionen, MTP2, PLD3,3, Cache Off und 18 GiB Reserve vorbereitet
und vom Controller validiert. Es wurde nicht gestartet; die Freigabe zur kurzen
Unterbrechung der Kollegeninstanz ist angefragt. Die installierte Originalinstanz
verwendet die ungesetzten Prefill-Standardwerte. Laut den
[Flags der installierten Version 0.16.2](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/v0.16.2/docs/FLAGS.md)
dimensioniert `HALOGEN_MAX_TOK` den Prefill-Arbeitsbereich; der Standard 32.768
benötigt etwa 9 GB. Diese Parameter werden beim Start gelesen. Ein kleinerer
Arbeitsbereich ist eine konkrete Speichermaßnahme; sein Tok/s-Effekt wurde
noch nicht gemessen.
