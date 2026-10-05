# NPU-Batch-Cut: Quellenentscheidung, 5. Oktober 2026

Der vorhandene native normalisierte Embedding-Cut ist kein früher Prefill-Seam.
Er wird erst innerhalb des vollständigen MTP-Heads bereitgestellt; der normale
mehrzeilige Head folgt dem Target-Trunk. Ein neuer Metadaten-Trace ist für diese
Reihenfolge und die Batchfähigkeit unnötig. Für den Vorschlag, vorhandene
normalisierte Zeilen während desselben Trunk-Prefills auf der NPU vorzurechnen,
fehlt damit der erforderliche frühe Input. Diesen vorhandenen Cut nicht weiter
entwickeln und keinen neuen NPU-Batchgraphen darauf aufbauen.

Diese Entscheidung widerlegt keine neu implementierte tokenabhängige
Vorbereitung. Embedding/RMS/Embedding-FC hängt mathematisch nicht vom Hidden-
Residual ab. Dafür wären jedoch eine neue frühe Token-zu-Normzeilen-Lineage,
qualifizierte Tabellen-/Gammazugriffe, eine Batchpublikation und deren gemessene
Kosten nötig. Diese Implementierung und Nachweise sind nicht vorhanden.

## Praktische Entscheidung und Falsifikator

**Jetzt keinen frischen Batchgraph-/Provider-Versuch starten.** Batch-M allein
liefert keinen frühen Input, und der bestehende gepaarte Graph benötigt auch
Hidden-Normzeilen, die erst nach dem Trunk entstehen. Ein neuer Graph ohne
frühen Produzenten würde dieselbe späte Quelle lediglich anders verarbeiten.
Die nächste begründete Arbeit ist der unabhängig koordinierte GPU-/HSA-Kontrolllauf.

Der konkrete Quellenfalsifikator für den vorhandenen Cut ist die Reihenfolge
`Trunk-Layers0..47 -> Head -> Embedding-Gather/RMS -> Embedding-FC -> Hidden-RMS`.
Der automatische Head-Aufruf bei `0x17de231` liegt nach den Target-Layers;
seine erste normalisierte Embedding-Zeile wird erst innerhalb dieses Heads
produziert. Die Hypothese "vorhandene native Normzeilen überlappen denselben
Trunk-Prefill" scheitert damit an ihrer Inputverfügbarkeit. Dies sagt nichts
über bislang ungemessene physische Warteschlangenüberlappung aus.

Eine neue reine Embedding-Vorbereitung wäre ein anderer Cut. Deren Umsetzung
wäre erst dann ein sinnvoller Graphversuch, wenn die frühe Token-/Normzeilen-
Lineage und der Zugriff auf dieselben Tabellen/Gamma-Werte qualifiziert sind
und ein plausibles gemessenes Zeitbudget einschließlich Publikation vorliegt.
Für einen zeitlichen Gewinn muss `max(0, L-W) < G` gelten: Kandidatenzeit L,
verfügbare unabhängige Überlappung W, tatsächlich entfernte GPU-Arbeit G.

Als begrenzte Orientierung beträgt die vorhandene **gepaarte** GPU-Projektion
0,487170 ms Hostzeit bzw. 0,311702 ms GPU-Eventzeit; der korrigierte **gepaarte**
NPU-Lauf braucht 1,850025 ms Sessionzeit bzw. 3,539513 ms für den beobachteten
Diagnosepfad. Selbst mit dem großzügigen GPU-Hostbudget wären mehr als
1,362855 ms unabhängige Überlappung für die Session allein bzw. 3,052342 ms für
den beobachteten Pfad nötig, zusätzlich zu nicht gemessenem Live-Transport.
Der Diagnosepfad enthält reduzierbare Diagnosearbeit; er ist keine feste
Produktionsuntergrenze. Diese gepaarten Einzelaufrufe messen weder den Gewinn
eines neuen Embedding-only-Batchgraphen noch dessen Amortisierung oder
Prefill-/Decode-Tokenrate. Belege:
`docs/research/halogen-npu-precision-correction-20261004.{md,json}`.

## Exakte erhaltene Aufrufbelege

Alle Textzeilen beziehen sich auf
`mtp-route-static-20261004/host-text-disassembly.txt`, SHA256
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.
Die Rollen sind aus dem erhaltenen Disassembly/ABI abgeleitet, keine
nachträglich erfundenen exportierten Symbolnamen. Gepinnter Engine-SHA256:
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.

| Beleg | RVA / Textzeile | Aussage |
|---|---|---|
| Target-Forward | `0x17dd020`, Zeile193814; `0x17dd031`, 193821 | Count aus EDX bleibt in R14D. |
| Trunk-Layers | `0x17dd61f`, 194166; `0x17dd791`, 194254; `0x17dd6ad..6b4`, 194199..194201 | Layerindex beginnt bei0, Dispatcher `0x17d9eb0`, Grenze48. |
| Automatischer Head-Replay | `0x17ddf88..fc1`, 194696..194707; `0x17de22b`, 194847; `0x17de231`, 194849 | Nach Trunk und Replay-Gates; EDX bleibt Target-Count. Head-Return `0x17de236`. |
| Head-Count | `0x17db333`, 192156 | Head-EDX bleibt in R14D. |
| Embedding-Gather/RMS | `0x17db449`, 192215; `0x17db517`, 192259 | Innerhalb des Heads; Gather-Identität `0x18d5b40`, RMS `0x18d5160`. |
| Embedding-FC | `0x17db520..543`, 192261..192267; Return `0x17db548`, 192268 | Descriptor `model+0x908`, Input `model+0x6c8`, Output `model+0xb00`, N=K2560; R8D=M=Head-Count. Dispatcher `0x178cf90`. |
| D-Hidden-RMS/FC | `0x17db62d`, 192316; `0x17db64b`, 192321; `0x17db65e`, 192325; Return `0x17db663` | Folgt dem Embedding-FC; Hidden-M=4*Count. Embedding-FC liegt also vor der Hidden-Norm, nicht dahinter. |
| Projektionsverbrauch | `0x17db9e0..9ee`, 192515..192517; `0x17dbb91`, 192605; `0x17dbbe1`, 192624 | Erst Seed-Add, dann Layer48. Der vorhandene gepaarte Cut wartet bis beide Norminputs vorliegen. |

Die vier im erhaltenen Text gefundenen direkten Head-Calls sind
`0x17dcc03`/Return`0x17dcc08` (Count1),
`0x17dcd4f`/Return`0x17dcd54` (accepted-prefix Count),
`0x17dcf44`/Return`0x17dcf49` (Count1) und
`0x17de231`/Return`0x17de236` (normaler Target-Count).
Native Verifikation setzt `model[0]=1` bei `0x17dcfe4`, ruft Target bei
`0x17dcfef` auf und überspringt dadurch automatischen Head-Replay über
`0x17ddfa1/fa3`. Expliziter accepted-prefix Replay folgt getrennt über
`0x173bb5e -> 0x17dcc90 -> 0x17dcd4f`.

## Prefill-Batches und Grenzen

Chunking-Frontend `0x17e6050` gibt bei `0x17e6139` Target-Chunks in EDX weiter
(Zeilen202432..202450), oder im direkten Pfad den vollständigen Count
(202470..202481). Berechtigter automatischer Replay führt diesen Count bis
Embedding-M durch. Mehrzeilige Embedding-FC ist statisch belegt.

Bei nichtfinalen Chunks steht sogar der folgende bekannte Inputtoken schon bei
`0x17e6130` (202447) in ECX; Target speichert ihn bei `0x17dd034` (193822) und
setzt ihn bei `0x17de1c0/1c7` (194822..194823) als letzten verschobenen Headtoken
ein. Nur ein negativer Wert führt über `0x17ddfc7/fcf` zur Target-Vorhersage.
Das erlaubt in Prinzip eine neue frühere tokenabhängige Vorbereitung, beweist
aber keinen vorhandenen frühen normierten Buffer oder NPU-Seam.

Der erhaltene Lauf hat115 Head-Aufrufe, davon73 Count1 und42 andere Counts.
Er ordnet die42 nicht einzeln Bootstrap, Prefill oder accepted-prefix Replay
zu; reale Prefill-Batchgrößen bleiben ungeklärt. Diese Unklarheit ändert die
belegte native Aufrufreihenfolge nicht. Host-Reihenfolge ist keine Messung
physischer GPU/NPU-Überlappung oder eines Batch-Zeitbudgets.

Der bestehende Quality/Discovery-Shim bleibt unverändert. Seine
`valid_head_entry` verlangt Count1 (Quellzeile367), Embedding-M1/Hidden-M4
(Dimensionschecks619/626, Guards618/625), und schließt andere Counts aus
(679/709). Der vorhandene kompilierte
Shim kann daher reale Batchgrößen nicht als erfolgreiche Discovery ausgeben.
Ihn zu laden würde die Batch-Unklarheit nicht lösen. Falls Batchzuordnung später
ein eigenes notwendiges Ziel wird, reicht eine getrennte reine Metadatenvariante
dieser zwei bestehenden Detours: ein armiertes Requestfenster, feste begrenzte
Hostrecords von Head-Caller/Count/Position und FC-Caller/N/M/K/Reihenfolge,
originale Funktionen genau einmal, Ausgabe nach dem Request. Keine GPU-Copies,
Synchronisationen, Norminputs, Tokenpayloads, Provider oder Tokenratenclaims.
Eine solche Variante wurde hier weder geschrieben noch gebaut.

Die Empfehlung für diesen Falsifikationsschritt ist **kein neuer Trace**.
Es wurden nur Quellen/erhaltene Text- und JSON-Belege gelesen. Keine ELF-Reader,
Engine, GPU/NPU, Provider, Builds, Modelle oder Hardware ausgeführt/gelesen.
