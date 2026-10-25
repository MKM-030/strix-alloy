# Halogen 0.18.15: historische Einordnung und native Lookup-Platzierung

Halogen 0.18.15 wurde mit dem vorhandenen HGN-v2-Checkpoint aktualisiert und mit
echten Modellanfragen geprüft. Der zusätzlich implementierte native Lookup-Pfad
bewahrt im abgeschlossenen A/B-Vergleich alle Ausgaben und Draft-Zähler. Seine
kleinen, gemischten Zeitänderungen belegen bislang keinen verlässlichen
Geschwindigkeitsgewinn. Er wird deshalb nicht zum Standard erklärt. Prefill von
1.925 tok/s oder ein Gesamtmittel von 66 Decode-tok/s sind hier nicht bestätigt.

**Messungen abgeschlossen:** A, B, der abschließende Kontrolllauf A′ und die
neue 60-Request-Kurzserie sind abgeschlossen. Der abschließende Root-Nachweis
bestätigt den geöffneten, bereiten Stock-Server. Die ursprünglichen A/B-Werte werden durch
die späteren Abschnitte nicht rückwirkend ersetzt.

## Gleiche Modellgewichte, unterschiedliche Vergleichsbedingungen

Beide Versionen verwenden denselben nativen v2-Checkpoint mit SHA-256
`71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`.
Es handelt sich nicht um einen Wechsel zu einem IQ4_XS-GGUF. Die Engine änderte
sich von 0.16.2 zu 0.18.15; alte und neue 8K-Ausgabehashes unterscheiden sich.
Ein gleiches Eingabefragment beweist daher keine gleiche Rechenfolge oder
Fortsetzung über diese Versionen hinweg.

| Einstellung | Frühe schnelle 0.16.2-Referenz | Aktueller 0.18.15-Vergleich |
| --- | --- | --- |
| Kontextkapazität / KV-Pool | 262.144 / 262.144 | 32.768 / 32.768 |
| Slots | 1 | 1 |
| Prefill-Chunk | Geerbt/automatisch, kein expliziter Override | 8.192 |
| Prefill-Arena / maximale Prefill-Tokens | 32.768 | 8.192 |
| MTP | Fest 2 | Adaptiv, Gate 0,90 |
| PLD | 3,3; separate PP1-Zelle mit PLD 0 | 3,3 |
| Prompt-Cache | Off | Global Flexible; Messrequests `no_store`, tatsächliche Cache-Tokens 0 |
| Vision | Kein Tower im Manifest | An; 897.863.168 registrierte Gerätebytes |
| Decode-Prefetch | Damalige Version/Defaults | Explizit 0 |

Die aktuelle Hardware hat 128 GiB physischen RAM, aufgeteilt in ungefähr 64 GiB
für Windows sichtbaren Speicher und 64 GiB dedizierte UMA. Für die exakten
historischen Spitzen existiert kein passend gebundener Leistungs- oder
Taktverlauf. Ein separater früherer Sensorlauf wird nicht als Ursache dieser
Spitzen eingesetzt. Die Änderungen an Arena, Kontext, Vision und MTP lassen sich
aus diesem Versionsvergleich nicht einzeln kausal bewerten.

| Historische 8K-Zelle | Tatsächliche Ein-/Ausgabe | Prefill tok/s | MTP-Decode tok/s | Einordnung |
| --- | ---: | ---: | ---: | --- |
| 0.16.2 Stock A | 8.192 / 128 | 1.866,54 | 48,42 | Zusammengehörige MTP128-Phasen |
| 0.16.2 PLD Off, seriell | 8.192 / 1 | 1.925,16 | — | Separate PP1-Anfrage |
| 0.16.2 später Stock | 8.192 / 1 bzw. 128 | 1.714,94 | 47,06 | PP1 und MTP128 aus getrennten Anfragen |

Die 1.925,16 Prefill-tok/s dürfen nicht mit den 48,42 Decode-tok/s zu einer neuen
gemeinsamen Messung verbunden werden. Die historischen Raten waren Mittel
kalibrierter Phasenmessungen. Aktuelle Phasenraten unten sind gepoolte native
Beobachtungen; ihre Phasenuhren wurden nicht unabhängig qualifiziert.

## Relevante Upstream-Änderungen

Die gepinnten Upstream-Unterlagen erklären, weshalb ein beibehaltenes festes
MTP2-Profil die neuen Defaults nicht vollständig nutzt. Seit 0.17.2 soll die
feste Draft-Tiefe für die adaptive Auswahl entfallen. 0.18.5 führt das
Confidence-Gate 0,90 ein; die dort genannten rund 6,4% sind ein
**Upstream-Ergebnis**, keine lokal isolierte Verbesserung. Der aktuelle
adaptive Vergleich verwendet dieses Gate und setzt keine feste Tiefe.

`CACHE_STAGE2` aus 0.18.12 betrifft Prompt-/Fork-Snapshots und ist kein neuer
innerer MTP-Verifikationskern. Die 64 n-gram-Prefill-Leser gibt es bereits seit
0.6.3; sie erklären allein keinen neuen Versionsgewinn. Die aktuelle Binärdatei
erkennt außerdem `NGRAM_DECODE_PAR`, dessen interne Erkennung ohne dokumentierte
Semantik und Messung keine Freigabe als schneller Standard darstellt. Der
zusätzliche Vision-Arbeitsbereich von ungefähr 0,8 GiB wird laut Upstream erst
beim ersten Bild angelegt; das ist ein anderer Speicherposten als die oben
genannten registrierten Tower-Gewichte.

Quellen sind das gepinnte [Changelog](https://github.com/peonist-ai/halogen-flash-server/blob/e9a1a713abb26be4e51822d77b5192f0f33fa44e/CHANGELOG.md),
die [Flags](https://github.com/peonist-ai/halogen-flash-server/blob/e9a1a713abb26be4e51822d77b5192f0f33fa44e/docs/FLAGS.md)
und die [Performance-Bedingungen](https://github.com/peonist-ai/halogen-flash-server/blob/e9a1a713abb26be4e51822d77b5192f0f33fa44e/docs/performance.md).
Diese Quellenprüfung ersetzt weder einen kontrollierten Versionsvergleich noch
die getrennte lokale QPC-Messung.

## Bereits abgeschlossene Prefetch-Prüfung vor dem Lookup-Vergleich

Diese früheren 0.18.15-Kohorten bleiben vom neuen A/B-Vergleich getrennt.
Adaptive MTP-Policy, Requests und jeweilige Ausgabehashes stimmen innerhalb
dieses Prefetch-Vergleichs überein; Reihenfolge und Dateicache-Historie bleiben
Störgrößen. Je Zeile: ein ausgeschlossener Warmup und drei Messrequests.

| Eingabetokens | Prefetch | Native Prefill tok/s | Native Decode tok/s | Head akzeptiert / entworfen | Ganze HTTP-Anfrage, QPC-Mittel |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8.192 | Automatisch | 1.249,00 | 35,76 | 210 / 318 = 66,04% | 10,1893 s |
| 8.192 | Aus, spätere warme 8K-Serie | 1.144,49 | 45,21 | 210 / 318 = 66,04% | 10,0564 s |
| 16.384 | Automatisch | 1.125,08 | 26,59 | 177 / 336 = 52,68% | 19,5039 s |
| 16.384 | Aus | 1.181,30 | 39,77 | 177 / 336 = 52,68% | 17,2036 s |

Bei 8K steigt die native Decode-Rate um 26,44%, während die Prefill-Beobachtung
um 8,37% sinkt; die ganze Anfrage ist nur 1,30% kürzer. Bei 16K ist die ganze
Anfrage 11,79% kürzer. Die identischen Draft-Zähler zeigen keinen durch Prefetch
veränderten Akzeptanzwert. Prefetch Off verbessert damit nicht jede Phase
einheitlich; die höhere Phasenrate wird nicht als entsprechend großer Gewinn
der gesamten Anfrage ausgegeben.

Die frühere Kurzserie mit Prefetch Off enthielt 30 MTP-Requests und ergab
**46,39 tok/s als arithmetisches Gesamtmittel** über zehn Fälle. 64,10 tok/s war
das Mittel des schnellsten einzelnen Falls. Dieses Fallmaximum ist kein
Gesamtmittel. Ihre 30 MTP-only-Requests hatten außerdem eine andere Reihenfolge
und Cache-Historie als die vorherigen 60 alternierenden Serial/MTP-Requests.
Diese Serie ersetzt die getrennte abschließende 60-Request-Serie unten nicht.

## Native Lookup-Platzierung: abgeschlossene A/B-Messung

A verwendet den bisherigen kompletten w4b-Lookup-Quellpfad auf `/mnt/c`.
B wählt dieselben zuvor vollständig geprüften Tabellenbytes aus dem kanonischen
Wrapper auf nativem WSL-Dateisystem. Der vollständige Stock-Quellpfad bleibt
montiert und integritätsgeprüft. Hinzu kommt ausschließlich der geprüfte
Read-only-Bind `/candidate/ngram.hgn` mit passendem `HALOGEN_NGRAM_TABLE`.
Dies betrifft die trainierte n-gram-Feature-Tabelle, nicht die spekulative
Prompt-Lookup-Policy.

Beide Arme behalten 0.18.15/v2, 32K Kontext und Pool, einen Slot, Vision On,
Chunk und Arena 8.192, adaptives MTP/Gate 0,90, PLD3,3, Prefetch Off und Thinking
Off. Die langen Requests verwenden Temperatur 0, Seed 1 und `no_store`. Der
8K-Fall ist die eingefrorene historische Pseudoprosa, der 16K-Fall ein echtes
Romanpräfix. Beide sind auf tatsächlich 8.192 beziehungsweise 16.384 komplette
Eingabetokens gebunden. Die PP1-Anfrage bleibt eine separate serielle Anfrage.

Jeder Arm umfasst drei Fälle mit je **einem ausgeschlossenen Warmup und drei
Messungen**: zwölf abgeschlossene Requests, davon neun gemessen. A und B ergeben
zusammen 24 abgeschlossene Requests und 18 Messrequests. Alle passenden
Request-Hashes, alle vier Ausgabehashes je Fall einschließlich Warmup und die
kombinierten sowie getrennten Draft-Zähler stimmen zwischen A und B überein.
Das belegt die beobachtete Ausgabeparität; es ist kein allgemeiner Qualitätsbeweis.

### Ganze Anfrage: unabhängige Windows-QPC-Zeit

| Fall | A: Mittel ± Stichproben-SD | B: Mittel ± Stichproben-SD | B gegen A |
| --- | ---: | ---: | ---: |
| 8.192 / 128, MTP | 9,4795 ± 0,1846 s | 9,3310 ± 0,2502 s | −1,57% |
| 16.384 / 128, MTP | 17,0070 ± 0,4233 s | 16,5080 ± 0,2360 s | −2,93% |
| 8.192 / 1, serielles PP | 6,7217 ± 0,2188 s | 6,8626 ± 0,2960 s | +2,10% |

Die jeweils drei Einzelzeiten bleiben im [JSON-Beleg](halogen01815-comparison-20261025.json).
Die Zeit umfasst den vollständigen HTTP-Request bis zum vollständigen
Antwortkörper. Es wird kein Overhead abgezogen oder in eine reine GPU-Rate
umgerechnet.

### Native Phasen und Akzeptanz: getrennte Engine-Beobachtungen

| Fall | Arm | Prefill tok/s | Decode tok/s | Head akzeptiert / entworfen |
| --- | --- | ---: | ---: | ---: |
| 8.192 / 128, MTP | A | 1.213,19 | 47,66 | 210 / 318 = 66,04% |
| 8.192 / 128, MTP | B | 1.241,60 | 47,80 | 210 / 318 = 66,04% |
| 16.384 / 128, MTP | A | 1.186,70 | 41,36 | 177 / 336 = 52,68% |
| 16.384 / 128, MTP | B | 1.232,33 | 41,26 | 177 / 336 = 52,68% |
| 8.192 / 1, serielles PP | A | 1.217,01 | — | Nicht anwendbar |
| 8.192 / 1, serielles PP | B | 1.206,34 | — | Nicht anwendbar |

Die Raten sind tatsächliche Phasentokens geteilt durch die Summe der nativen
Phasenzeiten. Diese Uhren sind unabhängig nicht qualifiziert. In den MTP-Fällen
meldet der Head alle akzeptierten Draft-Tokens; Lookup und Grammar melden
jeweils null Drafts. Ihre Akzeptanz ist deshalb nicht 0%, sondern nicht
anwendbar.

Die native Decode-Änderung beträgt nur +0,31% bei 8K und −0,24% bei 16K.
Prefill steigt in den MTP-Anfragen um 2,34% beziehungsweise 3,85%, fällt aber in
der separaten PP1-Anfrage um 0,88%. Bei nur drei Messungen, sichtbarer Streuung,
sequentieller Armreihenfolge und nicht kontrollierter Betriebssystem-
Dateicache-Historie ist dies kein konsistenter Beschleunigungsnachweis. Der
korrekte optionale Pfad wird implementiert behalten, aber nicht als schnellerer
Standard beworben. Der inzwischen abgeschlossene A′-Lauf unten zeigt deutliche
Drift auch ohne die Lookup-Änderung.

## Implementierung und Grenzen

Die neue Qualifikation bindet ausschließlich den kanonischen Receipt, den exakt
geprüften alten Readback-Seal und die frisch übereinstimmenden Metadaten an das
konkrete 0.18.15-Image und seinen HGN-Loader. Vor Create und Start werden die
Metadaten erneut geprüft. Die laufende Ownership-Prüfung verlangt den echten
Read-only-Bind und das passende Environment. Ein Cache-Miss erzeugt weder einen
neuen 50-GB-Hashlauf noch einen erfundenen Ersatz-Seal. Details und genaue
Prüfsummen stehen in der [Feature-Dokumentation](../research/halogen01815-native-lookup-placement.md).

Zwei gezielte CPU-Tests des Lookup-Ports und sechs Tests des Inspection-Watchdogs
sind bestanden. Der Fix trennt Docker-Inspection und laufende Speicherabtastung,
verbraucht abgeschlossene Inspection-Ergebnisse vor der Altersprüfung und
verwendet Dateiausgabe mit begrenztem Warten/Reaping statt unbeschränktem
Pipe-Drain. Ein Timeout erneuert keine Ownership-Frische. Das ist ein
Lifecycle-Zuverlässigkeitsfix, kein gemessener Rechenkern-Geschwindigkeitsgewinn.

18 GiB physische und Commit-Reserve gelten durchgehend, 22 GiB vor neuen
Messrequests. Startup-Zulassung, cgroup-Grenze und Watchdog/Lease-Zeiten wurden
für den Lookup-Port nicht gelockert. Modelle, Treiber, BIOS, Spannungen und
globale WSL-Einstellungen wurden für diese Messungen nicht geändert. NPU-Beschleunigung ist nicht
aktiviert.

## Gemessene Konfiguration nach einem Neustart starten

Das zusätzliche, ausdrücklich gewählte Launcher-Profil verwendet die geprüfte
Stock-Konfiguration ohne den optionalen nativen Lookup-Override:

```powershell
.\scripts\Start-Halogen-ServiceNow.ps1 -Profile Measured32K -ConsoleTrace
```

Es verwendet Windows PowerShell 5.1 und den normalen Generator/Controller mit
dem vorhandenen stabilen ServiceNow-Token. Das Profil setzt 0.18.15/v2, 32K
Kontext und Pool, Vision On, 8K Chunk/Arena, Flexible Cache, adaptives
MTP/Gate 0,90, PLD3,3, Prefetch Off und Thinking Off mit niedrigem Effort und
Budget 2.048. Der vorhandene Token wird nicht ausgegeben oder ersetzt.
`-ConsoleTrace` bleibt eine bewusste Auswahl für sichtbare Anfrage-/Antwortdaten.

`-Profile Measured32K -PrintOnly` gibt die aufgelöste Konfiguration mit
Token-Dateiverweisen aus, ohne Session-Datei oder Engine-Start. Explizit
widersprechende Versions-, Thinking-, MTP- oder Cache-Optionen werden
zurückgewiesen. Andere Profile und die bisherigen Launcher-Defaults bleiben
unverändert. Drei gezielte PrintOnly-Tests unter PowerShell 5.1 bestätigen die
Parität zum eingefrorenen Messprofil, Konfliktbehandlung, Trace-Auswahl und
bisherige Current4K-Defaults; sie starten keine Engine.

## Abschließender Kontrolllauf und Kurzserie

<!-- ROOT_CONTROL_BOOKEND_COMPLETE -->
**A′ ist abgeschlossen.** Es wurde derselbe normale Stock-Pfad nach B erneut
gestartet und mit denselben drei Fällen geprüft. Je Fall: ein ausgeschlossener
Warmup und drei Messrequests. Alle Request-Hashes, Ausgabepräfixe und
kombinierten sowie getrennten Draft-Zähler stimmen über A, B und A′ überein.
Insgesamt umfasst A/B/A′ damit 36 abgeschlossene Requests, davon 27 gemessen.

| A′-Fall | HTTP-Mittel ± Stichproben-SD | Native Prefill tok/s | Native Decode tok/s | HTTP-Drift A′ gegen A |
| --- | ---: | ---: | ---: | ---: |
| 8.192 / 128, MTP | 9,7730 ± 0,2156 s | 1.166,89 | 47,47 | +3,10% |
| 16.384 / 128, MTP | 18,5880 ± 1,3117 s | 1.084,32 | 38,09 | +9,30% |
| 8.192 / 1, serielles PP | 7,6929 ± 0,6525 s | 1.074,60 | — | +14,45% |

Die unveränderten Stock-Kontrollen streuen und driften stärker als die kleinen
anfänglichen A/B-Unterschiede. Auch das langsamere A′ wird unverändert
berichtet. B ist bei 8K/16K gegenüber A′ zwar schneller, aber die sequentielle
Entwicklung isoliert den Dateisystemeffekt nicht. Der optionale native Pfad wird
daher **nicht als schnellerer Standard ausgewählt**; der Stock-Pfad bleibt
gewählt. Es wird keine thermische oder Leistungsgrenzen-Ursache behauptet.

Die beiden Stock-Fenster lassen sich zusätzlich als sechs Kontrollmessungen je
Fall zusammenfassen. Das beseitigt die Drift nicht und ersetzt die einzelnen
A/B/A′-Fenster nicht:

| Stock A + A′, je sechs Messungen | HTTP-Mittel | Gepoolter nativer Prefill tok/s | Gepoolter nativer Decode tok/s | Head akzeptiert / entworfen |
| --- | ---: | ---: | ---: | ---: |
| 8.192 / 128, MTP | 9,6263 s | 1.189,59 | 47,56 | 420 / 636 = 66,04% |
| 16.384 / 128, MTP | 17,7975 s | 1.133,20 | 39,66 | 354 / 672 = 52,68% |
| 8.192 / 1, serielles PP | 7,2073 s | 1.141,38 | — | Nicht anwendbar |

## Passive Sensorbeobachtung während der Kurzserie

Eine getrennte passive ADLX-Aufzeichnung erfasste 30 gültige Samples über
29,246 Sekunden, vom 25. Oktober 2026, 19:24:24,916 bis 19:24:54,162 UTC.
Sie ist ein Ausschnitt des gesamten Kampagnenablaufs und keinem Prefill- oder
Decode-Abschnitt zugeordnet.

| ADLX-Metrik | Bereich | Mittel |
| --- | ---: | ---: |
| GPU-Takt | 1.159–1.920 MHz | 1.556,87 MHz |
| GPU-Temperatur | 60–68 °C | 64,53 °C |
| GPU-Leistung (`GPUPower`) | 54–55 W | 54,5 W |
| GPU-Auslastung | 64–89% | 80,1% |
| VRAM-Takt | 1.000 MHz | 1.000 MHz |
| NPU-Aktivität | 0% | 0% |

`GPUPower` ist keine nachgewiesene CPU-/APU-Package-Leistung und wird nicht mit
dem Package-Leistungswert der Herstellerkonfiguration gleichgesetzt. Diese
Samples beweisen weder Thermal Throttling noch ein Power-Limit oder die Ursache
der Durchsatzdrift. Alle sechs abgefragten Tuning-Fähigkeiten meldeten nicht
unterstützt; es wurde daraus keine Takt-, Spannungs- oder Treiberänderung
abgeleitet. Die aktuelle `amdadlx64.dll` als ADLX-Telemetriekomponente hat andere
Bytes als die Aufzeichnung vom 4. Oktober, trotz derselben gemeldeten Version
1.5.0.124. Das beweist weder eine Änderung des GPU-Kerneltreibers noch eine
Ursache der Regression. Eine unveränderte historische Sensor-Binäridentität
wird deshalb nicht angenommen; für die genaue frühere 48,42-Kohorte fehlt
weiterhin ein passend gebundener Leistungsstrom.

## Abschließende Kurzserie und Endzustand

<!-- ROOT_FINAL60_COMPLETE -->
**Abschließende Kurzserie: bestanden.** Auf dem nach A′ weiter geöffneten
Stock-Server liefen 60 Requests: zehn kurze Promptformen, drei Wiederholungen,
jeweils Serial direkt vor MTP, maximal 256 Ausgabetokens und kein ausgeschlossener
Warmup. Alle 60 Antworten erzeugten tatsächlich 256 Tokens. Alle sechs
Ausgabehashes pro Fall stimmen überein; die 30 MTP-Ledgerzeilen und alle 60
unabhängigen QPC-Zeiten sind vollständig und konsistent.

Das native MTP-Decode-Gesamtmittel beträgt **50,13 tok/s**, berechnet als Mittel
von drei Raten je Fall und danach gleichgewichtet über zehn Fälle. Gepoolt sind
es **48,78 tok/s**. Die Fallmittel reichen von **40,49 bis 63,61 tok/s**; das
Maximum ist kein Gesamtmittel. Native Phasenraten bleiben unabhängig nicht
uhrqualifiziert.

| Drafter, je 30 Requests | Ganze HTTP-Zeit, Summe | Ganze HTTP-Zeit, Mittel | Ausgabe / ganze HTTP-Zeit | Eingabe verarbeitet / gecacht |
| --- | ---: | ---: | ---: | ---: |
| Serial | 271,4889 s | 9,0496 s | 28,29 tok/s | 867 / 0 |
| MTP | 157,9708 s | 5,2657 s | 48,62 tok/s | 0 / 867 |

MTP war in allen 30 Paaren schneller. Das Verhältnis der gesamten gemessenen
Serial- zur MTP-Zeit beträgt **1,719×**, entsprechend **41,81% kürzerer
HTTP-Zeit**. Jedes MTP folgte jedoch unmittelbar auf Serial mit derselben
Eingabe und nutzte deren Prompt-Cache. Dieser beobachtete Paarvergleich isoliert
daher keinen reinen MTP-Effekt. Er ist auch keine neue cachefreie Prefill-Messung.

Die gepinnte API definiert `timings.prompt_n` ausdrücklich als verarbeitete
Eingabetokens (`n_prompt − n_cached`), `timings.cache_n` als gecachte Tokens und
`usage.prompt_tokens` als volle Eingabe. Die Summe verarbeitet plus gecacht wurde
für jede Antwort geprüft. Beide Drafter hatten insgesamt jeweils 867 volle
Eingabe- und 7.680 Ausgabetokens. Die langen 8K-/16K-Tests mit `no_store` bleiben
eine getrennte Kohorte.

| MTP-Akzeptanz, über alle 30 Requests summiert | Akzeptiert / entworfen | Anteil |
| --- | ---: | ---: |
| Gesamt | 4.830 / 6.804 | 70,99% |
| Head | 4.638 / 6.525 | 71,08% |
| Lookup | 192 / 279 | 68,82% |
| Grammar | 0 / 0 | Nicht anwendbar |

Serial hat ebenfalls 0 / 0 Drafts; dessen Akzeptanz ist nicht anwendbar. Die
Akzeptanzanteile verwenden Summenzähler, keine ungewichteten Request-Prozente.
Ausgabeparität dieser gespeicherten Fortsetzungen ist kein allgemeiner
Qualitätsnachweis.

Der veröffentlichte Herstellerwert **65,88 tok/s** ist damit **nicht bestätigt**.
Er stammt aus einer anderen Plattformkonfiguration mit nativem Linux und etwa
85 W anhaltender Package-Leistung. Lokale WSL-, Kontext-, Slot-, Arena- und
Vision-Unterschiede bleiben bestehen. Thinking bleibt Off entsprechend der
veröffentlichten Tabellenzeile; der bloße Reproduktionsbefehl mit `low` setzt
Thinking Off nicht ausdrücklich. Eine dokumentierte lokale Gleichheit aller
Herstellerbedingungen liegt nicht vor.

<!-- ROOT_READY_COMPLETE -->
**Endzustand: bereit und geöffnet.** Der gespeicherte Root-Nachweis vom
25. Oktober 2026, 19:31:28 UTC bestätigt API und Engine 0.18.15 mit passender
Versionsidentität, öffentlichen Port 8840 und nativen Endpunkt 8731. Es ist
weiterhin derselbe Stock-Server wie bei A′ und der finalen Kurzserie: 32K Kontext
und Pool, ein Slot, Vision On, Thinking Off, adaptives MTP/Gate 0,90 und Prefetch
Off. Aktive und wartende Requests waren null. Die frische Speicherprobe meldete
23,52 GiB verfügbaren Windows-Speicher (`available_bytes / 2³⁰`); die 18-GiB-Dauerreserve und die
22-GiB-Eingangsreserve bleiben bestehen.

Der kanonische native Lookup-Pfad bleibt optional und standardmäßig aus. Alle
eigenen Messsammler und die passive Sensorprobe sind laut Root abgeschlossen;
weitere GPU-Tests sind nicht geplant. Die gespeicherten Runtime-Quellkopien
binden die tatsächlich gemessenen Bytes. Die Controller-Kopie enthält zusätzlich
eine bereits bestehende, sachfremde Native-only-Fehlerbehandlung; diese wurde
bewahrt und nicht in den Git-Hunk dieser Änderung aufgenommen. Exakte
Run-Identitäten und SHA-256-Belege stehen im JSON-Bericht. Das gesamte
Beschleunigungsziel und die Hersteller-65,88-Bestätigung sind weiterhin nicht
erreicht.

Quellen: [Maschinenlesbare A/B-Daten](halogen01815-comparison-20261025.json),
[frühere 0.18.15-Kohorten](halogen01815-20261025.json),
[historische 0.16.2-8K-Kohorten](halogen0162-pld-stock8k-20261004.md),
[0.18.10-Vergleich](halogen01810-regression-check-20261018.md).
Private Rohbelege liegen unter
`server/.local/halogen-update-20261025/primary01815/optimization-next/measurements/{control,canonical,control-bookend,final-official}`.
