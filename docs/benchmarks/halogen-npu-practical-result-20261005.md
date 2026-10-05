# NPU: Genauigkeit und tatsächlicher Nutzen

Die getestete MTP-Projektionskomponente besteht nach der Korrektur die
unveränderte Entwicklungstoleranz `rtol=0.03, atol=0.003`: keine Überschreitung
auf beiden eingefrorenen Eingabesätzen in zwölf NPU-Aufrufen. Dafür werden
Aktivierungen und Gewichte in einen stabilen Hauptanteil und einen Rest
zerlegt. Die BF16-Ausgabegrenzen bleiben erhalten. Das ist keine vollständige
Modell-, Logit- oder MTP-Vorschlagsprüfung; die strengere CPU-Prüfung hat noch
eine Abweichung. Der Live-Austausch bleibt deshalb geschlossen.

| Dieselbe gepaarte Projektion | Gemessene Zeit |
|---|---:|
| GPU, Host-Aufruf mit Warten | 0,487 ms |
| Korrigierte NPU, nur Session-Ausführung | 1,850 ms |
| NPU einschließlich Vorbereitung und Diagnose | 3,540 ms |

Schon die reine NPU-Ausführung dauert etwa 3,8-mal so lange. Live-Transport
zwischen Windows und WSL ist dabei noch nicht enthalten. Diese Auslagerung
bleibt deaktiviert. Am vorhandenen Einhängepunkt stehen die normierten
Eingaben erst nach dem Trunk bereit; sie können dort nicht während desselben
Trunk-Prefills vorbereitet werden. Eine neue frühere tokenbasierte Vorbereitung
ist möglich, aber noch nicht implementiert und ohne gemessenen Vorteil.

| Neueste normale GPU-Kontrolle | Prefill tok/s | MTP-Decode tok/s | Akzeptanz |
|---|---:|---:|---:|
| GPU, 8.192 Eingabe / 128 Ausgabe | 1.317,77 | 41,65 | 60,0 % (207/345) |
| NPU-Auslagerung im vollständigen Engine | nicht gemessen | nicht gemessen | nicht gemessen |

Der neue Vergleich endete am 5. Oktober 2026 um 01:35:44 UTC. Er nutzt den
eingefrorenen nicht repetitiven Prosa-Prompt, einen Aufwärmlauf und drei
Messläufe, Cache Off, MTP-Tiefe 2 und PLD 3,3. Die frühere Spitze von
48,42 Decode-tok/s wurde ebenfalls ohne NPU gemessen. Der Unterschied zum
obigen Lauf ist kein NPU-an/aus-Effekt. Es gibt bislang keinen belegten
NPU-Gewinn in Prefill- oder Decode-tok/s. Komponenten-Millisekunden werden
nicht in Tokenraten umgerechnet.

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

Die Kontextkapazität beträgt 262.144 Tokens. Die Tabelle enthält keine
qualifizierte Messung mit 128K oder 260K tatsächlich belegter Eingabe.

Belege: [Genauigkeitskorrektur](../research/halogen-npu-precision-correction-20261004.md),
[CPU-/Paging-Kontrolle](../research/halogen-cpu-paging-control-20261005.md),
[NPU-Batch-Aufrufprüfung](../research/halogen-npu-batch-cut-source-disposition-20261005.md).
