# Modellregistrierung mit Registrar v2.1

Diese neue Version v2.1 schließt vor der Integration die unabhängig nachgewiesene Capture-Lücke des unverändert eingefrorenen v2-Vorgängers: Ein sichtbarer aktueller ES-Companion darf in der Payload nicht fehlen. V2 wurde nicht nativ ausgeführt. Sämtliche v2-Quellen, Tests, Anleitungen und Handoffs bleiben als historische Prüfstände unverändert.

[RegisterCapabilityModel.v2.1.background.js](../../servicenow/byollm/capability-model-management/RegisterCapabilityModel.v2.1.background.js) ist ein eigenständiges ES5-Skript für **Global / Scripts – Background**. Der bisherige Registrar, Add und Switch bleiben unverändert. Diese neue Version wurde ausschließlich anhand lokaler simulierter Plattformdaten geprüft; sie wurde nicht nativ ausgeführt und hat kein Modell angelegt.

Der Registrar legt bei einem geprüften Apply eine neue Modellkonfiguration und deren eigenen Transformer unter einer bestehenden Custom-LLM-Implementierung an. Die Modellkennung, beispielsweise Gemma oder Halogen, ist ein Parameter. Die fachliche Eignung des Adapters, Tokenlimits, Thinking und Function Calling müssen zum Zielmodell passen. Registrierung, Aktivierung, ausgewählte Capability-Alternativen und Veröffentlichung bleiben getrennte Schritte im AI Control Tower / Skill Kit. Der Registrar startet kein Modell und führt keine Inferenz aus.

## Standard: kurze Skripte exakt übernehmen

Der Standard bleibt `apply:false`, `active:false`, `scriptCopyMode:'exact'`, `reviewedLongCopy:null`. Request und Response müssen jeweils nichtleer, von den nativen Platzhalterdefaults verschieden und höchstens 4.000 Zeichen lang sein. Der bestehende Scanner für TODO-/Placeholder-Inhalte bleibt aktiv. Im Standardmodus werden Zeilenumbrüche nicht geändert.

Die Basisauswahl kann vor die vollständige Skriptdatei gestellt oder im internen Parameterblock eingetragen werden. Die Platzhalter sind echte Instanz-IDs, keine Modellnamen:

```javascript
var CapabilityModelRegisterParameters = {
    apply: false,
    targetModel: '<exakte neue Modellkennung>',
    displayName: '<Anzeigename>',
    sourceModelConfigId: '<aktive vorhandene Custom-LLM-Modell-sys_id>',
    sourceTransformerId: '<deren Transformer-sys_id>',
    providerMappingId: '<Mapping des ausgewählten Quellmodells>',
    providerId: '<zugehöriger sys_gen_ai_provider>',
    connectionAliasId: '<bestehender Connection Alias des Quellmodells>',
    capabilityIds: ['<gewählte vorhandene Capability-sys_id>'],
    maxTokens: 8192, // Beispiel; durch den geprüften Zielmodellvertrag ersetzen.
    outputTokenSize: null,
    active: false,
    thinkingEnabled: false,
    enableFunctionCalling: false,
    loggingEnabled: false,
    logSamplingPercentage: 100,
    scriptCopyMode: 'exact',
    reviewedLongCopy: null,
    expectedSourceGraphHash: '',
    expectedRequestHash: '',
    expectedResponseHash: '',
    expectedCopiedRequestHash: '',
    expectedCopiedResponseHash: '',
    updateSetId: ''
};
```

Vor Preview muss der tatsächliche Application Picker auf Global stehen. Das Skript prüft sichere Lese-, Create- und Feldschreibrechte sowie ausschließlich im Speicher erzeugte neue Prototypen. Es ändert weder Scope noch Rollen, ACLs oder Schutzregeln. Ein lesbares Quellmodell darf aus einem anderen Scope stammen; die neuen Zielprototypen und gespeicherten Ziele müssen Global gehören. Scope und Package werden nicht aus der Quelle kopiert und nicht direkt geschrieben.

Die Ausgabe trägt `[CAPABILITY_MODEL_REGISTER]`, `version:2.1`. `source` enthält rohe Hashes, Zeichen-/UTF-8-Längen, IDs und beobachtete Ownership/Revisionen; `copy` enthält den tatsächlich geplanten Inhalt als Hashes/Längen und den Kopiermodus. Transformer-Inhalte und Zugangsdaten werden nicht protokolliert. Bei einer normalen Inhalts-/Manifestablehnung bleiben bereits sicher gelesene skalare Quellfakten sichtbar. Das ist keine Freigabe des Inhalts.

Für Standard-Apply die geprüften Werte `source.graphHash`, `source.requestHash` und `source.responseHash` in die drei entsprechenden `expected...`-Parameter übernehmen. Zusätzlich ist ein vorhandenes Global-Root-Update-Set ohne Parent im Status In progress erforderlich. Preview wählt kein Update Set und schreibt keine Datensätze.

## Expliziter Modus für eine geprüfte lange eigene Quelle

`scriptCopyMode:'reviewed-lf-copy-v1'` ist eine gesonderte, ausdrücklich zu wählende Inhaltsableitung für **neue Ziele**. Die rohe Quelle bleibt unverändert. CRLF wird zu LF; ein alleinstehendes CR wird ebenfalls zu LF. Dadurch bleiben auch die durch alleinstehendes CR markierten Zeilengrenzen erhalten. Die Capture-Prüfung bekommt keine CR-/Whitespace-Ausnahme: Die vollständig zurückgelesenen Zielwerte müssen weiterhin exakt mit ihrer vollständig aufgezeichneten XML-Darstellung übereinstimmen.

Für diesen Modus gelten **je Feld höchstens 65.536 UTF-16-Codeeinheiten und 65.536 UTF-8-Bytes**, sowohl für die rohe Quelle als auch die abgeleitete Kopie. Das sind feste Anwendungsgrenzen. Der Dictionary-Vertrag bleibt `internal_type=script, max_length=4000`; die Prototyp-/ED-Ausnahme gilt nur für die exakten abgeleiteten Request-/Response-Werte im neuen eigenen Zieltransformer. Andere Felder behalten ihre Grenzen und Rechte.

Eine Quelle muss aktiv, `customer`, `usage_mode=none`, ungeschützt und ohne Vorgänger-/Override-Verweise sein. Die Modell-Scope/Package-Zuordnung und Revision werden exakt im Manifest gebunden. Der eigene Quelltransformer muss Global/Global, ungeschützt und eindeutig dem ausgewählten Modell zugeordnet sein. Das Manifest enthält genau die folgenden 14 Felder; fehlende oder zusätzliche Felder werden abgelehnt:

```javascript
scriptCopyMode: 'reviewed-lf-copy-v1',
expectedRequestHash: '<vollständig geprüfter roher Request-SHA256>',
expectedResponseHash: '<vollständig geprüfter roher Response-SHA256>',
reviewedLongCopy: {
    sourceModelConfigId: '<source.modelConfigId>',
    sourceTransformerId: '<source.transformerId>',
    sourceModelScope: '<source.modelScope>',
    sourceModelPackage: '<source.modelPackage>',
    sourceTransformerScope: 'global',
    sourceTransformerPackage: 'global',
    sourceModelRevision: '<source.modelRevision als String>',
    sourceTransformerRevision: '<source.transformerRevision als String>',
    requestHash: '<source.requestHash>',
    responseHash: '<source.responseHash>',
    requestCharacters: 60419,   // Ausschließlich konkrete geprüfte Zahlen übernehmen.
    requestUtf8Bytes: 60419,
    responseCharacters: 1616,
    responseUtf8Bytes: 1616
},
expectedCopiedRequestHash: '',
expectedCopiedResponseHash: ''
```

Zunächst kann der Standardmodus mit der vollständigen Basisauswahl die skalaren Daten einer langen Quelle liefern und dann mit `Refused` ablehnen. Anschließend die tatsächlichen Source-Dateien vollständig prüfen und das genaue Manifest für eine neue LF-Preview bilden. Bei LF-Apply müssen zusätzlich `copy.requestHash` und `copy.responseHash` als `expectedCopiedRequestHash` und `expectedCopiedResponseHash` sowie der geprüfte `source.graphHash` gesetzt sein. Ein kopierter Hash ersetzt keinen rohen Quellhash. Änderungen an Inhalt, Beziehungen oder Revisionen verlangen eine neue konkrete Prüfung und ein aktuelles Manifest.

Die native Halogen-Rücklesung vom 5. November 2026 bestätigte Quelle `ff74fcef93a70350e7f2b9fa6aba10ea`, Transformer `bc126377936f8750e7f2b9fa6aba1012`, Modell-Scope/Package `7cc4ec81533121106b38ddeeff7b12ee`, Modellrevision 2 und Transformerrevision 20. Der rohe Request hat 60.419 Zeichen/Bytes und SHA256 `99cb5d8733faca9955ec274f21dc4b5f46f0b2c4159cbb63b9c5954bf85c4e58`. Die ausdrücklich geprüfte LF-Kopie hat 60.180 Zeichen/Bytes, 330 LF und SHA256 `6b626c5a1b25e32c3272c52565dc301fe9f90aff7ce1a187a90ae948511cafc8`. Der 1.616-Zeichen/Byte-Response bleibt bei SHA256 `4cf888866db8c19788d721fdaec132ab0a41c3fee4682356f64cb1e094abeae6`. Diese Werte sind konkrete historische Prüfwerte, keine automatisch nachgeführten Parameter.

Der bekannte rohe Halogen-Request enthält das Wort „placeholder“ als Daten in eingebetteten nativen Templates. Nur für das **Request-Feld** mit den beiden oben genannten Identitäten und exakt dem freigegebenen `99cb...`-Inhalt existiert daher eine eng gebundene Scanner-Ausnahme. Sie wird erst nach vollständiger Manifest-, Hash-, Längen- und Ownership-Prüfung wirksam. Die tatsächlichen Revisionen bleiben frisch im Manifest/Graph gebunden; ein Metadata-Save bei identischen Request-Bytes erfordert keinen neuen Codepin. Der Response erhält keine geerbte Ausnahme. Geänderte Requests und beliebige TODO-/Placeholder-Skripte bleiben verweigert. Leere Inhalte und der exakte native Dictionary-Default werden immer verweigert.

Andere lange eigene Quellen benötigen dieselbe ausdrückliche Inhalts-/Semantikprüfung und alle Manifestwerte. Die LF-Äquivalenz ist hier konkret für den beibehaltenen Halogen-Code geprüft; daraus folgt keine pauschale Äquivalenz für Code, der seine eigene Quelldarstellung oder Stack-Zeilenpositionen auswertet. Eine zusätzliche Wortscanner-Ausnahme benötigt einen gesondert geprüften Codepin.

## Native Aufzeichnung und Model History

Native Transformer-Captures können unter `record_update` neben dem einen Zieltransformer genau einen `sys_es_latest_script`-Companion enthalten. v2.1 lässt ausschließlich diese belegte Geschwisterform zu. Beide Records müssen `INSERT_OR_UPDATE` und ausschließlich direkte Felder enthalten; andere Geschwister, doppelte Records/Felder, verschachtelte Elemente, DTDs, Entities und Löschaktionen werden verweigert. Payloads sind auf 524.288 Zeichen und UTF-8-Bytes begrenzt und werden vollständig verarbeitet; es wird nichts abgeschnitten.

Der Companion wird ausschließlich sicher gelesen, niemals durch dieses Skript angelegt oder verändert. Seine `id`-/`table`-Werte müssen exakt den Zieltransformer referenzieren. Bei jeder Transformer-Transportprüfung wird der aktuelle sichtbare native Companion unabhängig davon sicher abgefragt, ob die Payload einen Companion enthält. Es darf höchstens eine sichtbare aktuelle Zeile geben; ihre Präsenz muss in beide Richtungen exakt mit der Payload übereinstimmen. Ein sichtbarer aktueller Companion ohne aufgezeichneten Companion sowie ein aufgezeichneter Companion ohne sichtbare aktuelle Zeile verhindern den Erfolg. Bei beiderseitiger Präsenz muss der Companion eindeutig und vollständig lesbar sein; sämtliche neun aufgezeichneten Felder einschließlich seiner eigenen ID und Revision werden mit dem sicheren vollständigen aktuellen Snapshot verglichen. Bei beiderseitiger Nichtpräsenz bleibt das gewöhnliche Ein-Record-Capture zulässig; null sicher sichtbare Zeilen beweisen weiterhin keine globale Abwesenheit. Fehlende, veraltete, fremde oder nicht lesbare Companion-Daten verhindern den Erfolg. Die beobachtete Source-Companion-Präsenz und ihre Metadaten gehören zum Source-Graph. Gewöhnliche Ein-Record-Captures behalten ihren bisherigen Prüfweg. Sichere Abfragen können unlesbare Zeilen ausblenden; daraus wird keine allgemeine Abwesenheitsgarantie abgeleitet.

Neue Registrierungen bleiben standardmäßig inaktiv mit leerem Lifecycle, `model_source=customer`, `usage_mode=none` und leeren `preceding_model_config`/`sys_overrides`. Die schreibgeschützten Identitätsdefaults werden nur geprüft. Es werden keine Now-LLM-Modellversionen oder fremde „Model History“-Einträge kopiert. Normale Business Rules und native Metadaten-/Indizierungseffekte bleiben aktiv; unerwartete native Historienkinder werden inventarisiert und als Teilfehler gemeldet.

`Applied` setzt vollständige Zielrücklesungen, frische Source-Abhängigkeiten, vollständige passende Captures und erfolgreiche Wiederherstellung des vorherigen Update Sets voraus. Eine inaktive Registrierung liefert `readyForAdd:false`. Ein vollständig identisches vorhandenes Ziel kann `NoOp` ergeben; abweichende oder mehrdeutige Ziele werden verweigert. Jeder unklare Insert-/Capture-/Readback-Ausgang oder eine fehlgeschlagene Kontextwiederherstellung bleibt `Partial`, mit versuchten IDs und Beobachtungen. Kein automatischer Wiederholungslauf, keine Löschung und kein nachträgliches „Reparieren“ veralteter Captures folgt.

Für die anschließende Capability-Alternative den separat geprüften [Add- und Switch-Ablauf](capability-model-management.md) verwenden. Dieser Registrar wählt oder veröffentlicht keine Capabilities. Die bestehenden Model-History-Wartungsläufe bleiben abgeschlossen und werden nicht wiederholt.

## Prüfung dieser Lieferung

[register-capability-model.v2.1.test.cjs](../../servicenow/byollm/capability-model-management/register-capability-model.v2.1.test.cjs) prüft Preview, sichere Schreibwege, native ES-Geschwister, Drift, Historie, Teilfehler, Rechte, beide Längengates, LF-Ableitung, rohe/abgeleitete Hashes und die eng gebundene Scanner-Ausnahme mit simulierten Datensätzen. Native In-memory-Prototypen hatten zuvor exakte 60.419-Zeichen-Zuweisung trotz ED4000 bestätigt; das beweist keine persistierte Neuanlage.

Eine vollständige native neue Registrierung mit dieser v2.1-Datei, ihre spätere Add-/Publish-Übergabe und der Modellbetrieb bleiben gesonderte Prüfungen. Keine solche Ausführung folgt aus lokalen grünen Tests.

Die unveränderlichen LF-Belege liegen im bestehenden privaten Evidenzverzeichnis `C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102/halogen-transformer-lf-spike-20261105/`:

- `LF-SPIKE.v1.SOURCE-HANDOFF.json`, SHA256 `ee2f5f74c728d3fe776e7ded32f354a890b54d2bc93f8e54bd133121bbe95616`.
- `LF-NORMALIZATION.v1.DECISION-SUPPORT.md`, SHA256 `318f7ef03553a14321f10dfffefed83e34da246226e92c032f8d72ace2a5dd08`.
- `comparison-v2-once/LF-NORMALIZATION.v2.RESULT.json`, SHA256 `716f88833014d830de39416e4ecddff09d96668b29071e0a0160aaa0a597910d`.
- `NODE-TESTS.v2.SUMMARY.json`, SHA256 `5b6b32314db128506cbc2e33049bb245761eb01dd569044cd24a5e3441683572`.

Diese Unterlagen prüfen die beibehaltenen genauen Request-Bytes anhand von ES5-AST, Tokens, dekodierten Literalen, Zeilenpositionen und simulierten Verhaltensfällen. Sie ersetzen keine native Speicherung oder Capture-Rücklesung des neuen Ziels.
