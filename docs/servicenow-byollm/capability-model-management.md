# Capability-Modellzuordnungen verwalten

Die beiden eigenständigen Skripte verwalten die ServiceNow-Konfiguration für vorhandene Capabilities. [SwitchCapabilityModels.fix.js](../../servicenow/byollm/capability-model-management/SwitchCapabilityModels.fix.js) ändert bestehende Modellzuordnungen; [AddCapabilityModel.background.js](../../servicenow/byollm/capability-model-management/AddCapabilityModel.background.js) ergänzt eine neue Modellalternative mit Definition, Prompt-Konfiguration und Verknüpfungen. Beide beginnen mit einer Vorschau (`apply: false`).

Die Modellregistrierung, Capability-Auswahl und Veröffentlichung bleiben in ServiceNow AI Control Tower / Skill Kit. Die Skripte laden oder starten kein lokales Modell. Der zentrale lokale Controller muss das tatsächlich gewählte Modell separat bedienen können. Dialog, Agent-Schritte, STT und TTS behalten ihre getrennten Konfigurationen.

## Vorbereiten und Ergebnis lesen

Die Dateien sind vollständige serverseitige ES5-Skripte für **Global**. Das Switch-Skript kann als Fix Script oder unter **Scripts - Background** ausgeführt werden; das Add-Skript ist für **Scripts - Background** vorbereitet. Den Parameterblock anpassen und zunächst die gesamte Datei mit `apply: false` ausführen. Beim Add-Skript wird auch für die Vorschau die Rolle `admin` verlangt. Eine Vorschau kann wegen fehlender Lese- oder Schreibrechte ablehnen: Sie prüft die Voraussetzungen des geplanten Schreibwegs bereits vorab.

`targetModel` ist der genaue Wert von `sys_generative_ai_model_config.model`, beispielsweise `halogen-v2` oder `Gemma 4 26B-A4B`. Ein Anzeigename oder Dateiname reicht nicht. Die aktive Registrierung muss bereits vorhanden sein, einschließlich Custom-LLM-Provider-Mapping, Flow-Implementierung, Connection Alias sowie Request-/Response-Transformer. Diese Skripte erstellen keine Modellregistrierung oder Zugangsdaten. Andere Modelle funktionieren über denselben geprüften Custom-LLM-Vertrag; beliebige andere Provider-Implementierungen sind nicht abgedeckt.

Bei mehrdeutigen Namen die passende Registrierung mit `modelConfigId`, gegebenenfalls zusätzlich `providerMappingId` und `providerId`, auswählen. Die Werte sind `sys_id`s der jeweiligen Tabellen:

| Parameter | Tabelle |
| --- | --- |
| `modelConfigId` | `sys_generative_ai_model_config` |
| `providerMappingId` | `sys_generative_ai_provider_mapping` |
| `providerId` | `sys_gen_ai_provider` |

Eine doppelte Modellkennung innerhalb derselben Implementierung bleibt ein Fehler, auch mit expliziter Registrierungs-ID: Native Prompt- und Tokenauflösung verwenden dort weiterhin den Modellstring. Die Registrierung zuerst eindeutig machen.

Die Ausgabe steht im Systemprotokoll als JSON hinter `[CAPABILITY_MODEL_SWITCH]` beziehungsweise `[CAPABILITY_MODEL_ADD]`. Das Add-Protokoll enthält geplanten Prompt-/Schema-Inhalt und gehört in eine entsprechend geschützte Ablage. Erst nach Prüfung von Auswahl, Ausschlüssen, Modell und Änderungsumfang `apply: true` für denselben gewünschten Lauf setzen.

## Bestehende Zuordnungen umstellen

Das Switch-Skript verändert ausschließlich das Feld `model` geeigneter aktiver, veröffentlichter eigener Prompt-Konfigurationen. Dabei zählen auch aktive veröffentlichte Prompts ohne Standardbindung zur Auswahl; es ist keine Beschränkung auf den einen Standardprompt. Prompttext, Schema, Validatoren, Provider-Auswahl, Filter, Standardzuordnungen und historische Alternativen bleiben erhalten. `request_tokens` ist nativ berechnet und kann sich durch die Modellwahl ändern; das Skript schreibt diesen Wert nicht.

Für **VA Input Response Generation** mit Halogen den vorhandenen `PARAMETERS`-Block beispielsweise so setzen:

```javascript
var PARAMETERS = {
    apply: false,
    allCapabilities: false,
    capabilityIds: ['aca5634f4312121038520464dbb8f236'],
    targetModel: 'halogen-v2',
    modelConfigId: 'ff74fcef93a70350e7f2b9fa6aba10ea',
    providerId: '',
    providerMappingId: '',
    includeInactive: false,
    allowAdminMaintenance: false,
    updateSetId: '',
    updateSetIdsByScope: {},
    customerDefinitionIds: []
};
```

Diese Capability- und Halogen-Registrierungs-ID gehören zur geprüften Quellinstanz `soprasteriaassvsdemo14`; auf einer anderen Instanz die dortigen IDs verwenden. Für mehrere ausgewählte Capabilities deren eindeutige IDs in `capabilityIds` eintragen, höchstens 500.

Für Gemma lediglich die gewünschte Modellkennung ersetzen und gegebenenfalls deren Registrierungs-ID setzen:

```javascript
targetModel: 'Gemma 4 26B-A4B',
modelConfigId: ''
```

Für ein anderes bereits registriertes Modell entsprechend dessen exakten Modellstring und bei Bedarf dessen `modelConfigId` einsetzen.

Für alle geeigneten Capabilities die Auswahl im Parameterblock ändern:

```javascript
allCapabilities: true,
capabilityIds: []
```

„Alle“ umfasst die geprüften eigenen Custom-LLM-Definitionen der aufgelösten Implementierung und Verbindung. Fremde Provider oder geschützte, nicht zuordenbare beziehungsweise historisch inkonsistente Definitionen werden ausgeschlossen und im Bericht genannt. Bei expliziter Einzelauswahl führt ein solcher Definitionsfehler zum Abbruch der Vorprüfung. Deshalb auch bei einem erfolgreichen Gesamtlauf die Liste `excluded` lesen.

`includeInactive: true` schließt zusätzlich inaktive **Definition-Auswahlen** ein. Entwürfe, inaktive Prompt-Konfigurationen und unveröffentlichte/historische Promptversionen werden dadurch nicht umgestellt. Das Skript aktiviert keine Definition und veröffentlicht keinen Prompt.

Eigentum wird über die vorhandene Clone-Map-Herkunft belegt. Für eine anderweitig angelegte, ausdrücklich geprüfte eigene Definition deren ID in `customerDefinitionIds` aufnehmen. Das ist eine konkrete Eigentumsbestätigung; Scope, Package, Schutzstatus und Historienprüfung gelten weiterhin. Keine pauschale Liste von Hersteller-Definitionen eintragen.

### Änderungsaufzeichnung beim Switch

Die Vorschau nennt `requiredScopes` für tatsächlich nötige Änderungen. Vor einem Apply passende bestehende Update Sets im Status **In progress** bereitstellen; das Skript legt keine Sets an und korrigiert keine Header. Bei genau einem Scope dessen Set als `updateSetId` eintragen. Bei mehreren Scopes die in der Vorschau ausgegebenen Scope-IDs verwenden:

```javascript
updateSetId: '',
updateSetIdsByScope: {
    'global': '<sys_id des Global-Update-Sets>',
    '<Scope-sys_id aus requiredScopes>': '<sys_id des passenden Update-Sets>'
}
```

Platzhalter durch echte 32-stellige IDs ersetzen. Die Anwendung jedes Update Sets muss zum jeweiligen Zieldatensatz passen. Die Sets dürfen nur passende `INSERT_OR_UPDATE`-Einträge ohne eingebettete Löschaktionen enthalten. Das Skript wählt sie mit dem nativen Update-Set-Setter, erfasst und prüft jeden Customer Update und stellt die vorherige Auswahl abschließend wieder her. Reines Speichern der Benutzerpräferenz ist kein Ersatz für diesen nativen Setter.

## Modellalternative ergänzen

Das Add-Skript ergänzt ein **bereits registriertes** Modell für 1 bis 100 ausdrücklich ausgewählte vorhandene Capabilities. Es erstellt keine neue Capability oder Skill-Kopie. Quellen sind passende aktive Now-LLM-Definitionen; standardmäßig muss genau ein aktueller Standardprompt eindeutig ausgewählt werden können.

Im internen `PARAMETERS`-Block zum Beispiel setzen:

```javascript
var PARAMETERS = {
    apply: false,
    capabilityIds: ['aca5634f4312121038520464dbb8f236'],
    targetModel: 'halogen-v2',
    modelConfigId: '',
    providerId: '',
    providerMappingId: '',
    sourceDefinitionOverrides: {},
    sourcePromptIds: {},
    updateSetId: '',
    allowAdminMaintenance: false
};
```

Für Gemma `targetModel: 'Gemma 4 26B-A4B'` verwenden; für ein anderes registriertes Modell dessen exakten Wert. Bereits vorhandene Modellalternativen bleiben bestehen und werden als `ExistingAlternativeRetained` gemeldet. Bei einer früheren unvollständigen Anlage stoppt die Prüfung zur gezielten Untersuchung.

Wenn mehrere geeignete Quelldefinitionen oder aktuelle Prompts vorhanden sind, die Auswahl explizit angeben:

```javascript
sourceDefinitionOverrides: {
    '<Capability-sys_id>': '<Now-LLM-Quelldefinition-sys_id>'
},
sourcePromptIds: {
    '<Capability-sys_id>': ['<aktueller Prompt-sys_id>']
}
```

Mehrere IDs in einem Prompt-Array wählen mehrere geprüfte aktuelle Quellsnapshots; sie wählen keine komplette Historie aus. Jeder ausgewählte Prompt muss zur Quelldefinition gehören, aktiv sein und einen zulässigen aktuellen Zustand besitzen. Historische oder fremde Prompts werden abgelehnt.

Schon für die **Vorschau einer neuen Alternative** muss der **Application Picker tatsächlich auf Global** stehen; allein die Skriptauswahl „Global“ genügt dafür nicht. Native neue Datensatz-Prototypen übernehmen die aktuelle Anwendung bereits bei der Vorprüfung. Das reine Erkennen einer vorhandenen Alternative (`NoOp`) funktioniert auch in einer anderen Anwendung. Für Apply muss `updateSetId` außerdem ein vorhandenes Global-Root-Update-Set ohne Parent im Status **In progress** bezeichnen. Der Lauf erfasst neue Definitionen, Prompt-Konfigurationen, native Verknüpfungen und erforderliche Validator-Verweise ohne Löschungen. Native Generatoren erstellen die streng schreibgeschützten Definition-/Prompt-Verknüpfungen; das Skript prüft anschließend deren Zuordnung und ergänzt nur die erlaubten Optionen.

Neue Alternativen bleiben zunächst **Entwurf, inaktiv und ohne Standardauswahl**. Anschließend die neue Alternative in Skill Kit / AI Control Tower prüfen, nativ veröffentlichen und bei Bedarf aktivieren beziehungsweise auswählen. Ein Add-Apply allein ändert das verwendete Modell nicht. Das Switch-Skript bearbeitet erst aktive veröffentlichte Prompt-Konfigurationen. Für eine neu durch Add angelegte und anschließend veröffentlichte eigene Definition deren geprüfte ID zusätzlich als `customerDefinitionIds` im Switch angeben, wenn keine Clone-Map-Herkunft existiert.

## Native Modell-Versionszuordnungen und Prompt-Abstammung

Hier sind zwei verschiedene Beziehungen zu unterscheiden. Die frühere Einordnung nur über Prompt-`parent`/`version` war für die vom Nutzer angesprochene Modellansicht nicht ausreichend. Eine konkrete moderne Registerkarte mit dem wörtlichen Titel „Model History“ ist weiterhin nicht bestätigt; daraus darf aber nicht geschlossen werden, dass keine native Modell-Versionsrelation existiert.

Am 3. November 2026 wurde im klassischen nativen Formular der Halogen-Modellregistrierung `ff74fcef93a70350e7f2b9fa6aba10ea` die Related List **Gen AI Model Version Mappings (7)** belegt. Ihre Beziehung ist `sys_gen_ai_model_version_mapping.target_model_name`. Alle sieben angezeigten Zuordnungen sind inaktiv (`active=false`), gehören zum Custom LLM Provider und tragen die Source-Anzeige ServiceNow. Als Quellmodelle erscheinen `code_assist_v1` einmal sowie `llm_generic`, `llm_generic_small` und `llm_generic_large` jeweils zweimal. Das ist eine native Quell-/Zielmodell-Zuordnung, keine Prompt-Versionskette und kein Nachweis einer Halogen-Trainings- oder Prompt-Historie. Ein aktiver Routing-Effekt dieser inaktiven Einträge wurde hier nicht nachgewiesen.

Die gespeicherte Provider-Copy-Ausgabe erklärt ihre Herkunft: Ein tatsächlicher Lauf (`dryRun:false`, Batch `656c498f937bcf14e7f2b9fa6aba1083`) meldete exakt diese sieben Ziel-IDs als Inserts in `sys_gen_ai_model_version_mapping`. Seine erhaltene Quelle führt diese Tabelle ausdrücklich als `template:true`, kopiert Quellfelder einschließlich Modell-/Source-Zuordnungen und setzt die neue Vorlage inaktiv. Eine zusätzliche gespeicherte Zielmodell-Korrektur ist darauf ausgelegt, `target_model_name` auf die Halogen-Registrierung zu setzen und den Quellalias zu behalten. Die heutigen passenden Ziel-IDs und der historische Ausführungsbericht sind ein konkreter Herkunftsbeleg; sie beweisen nicht, dass diese Zuordnungen für jeden zukünftigen Custom-Provider fachlich erforderlich sind.

Das neue **AddCapabilityModel.background.js** erstellt keine Modellregistrierung. Es ergänzt Capability-Definitionen, aktuelle Prompts, native Bindings und Validator-Verweise für ein bereits registriertes Modell und kopiert `sys_gen_ai_model_version_mapping` nicht. Auch das Switch-Skript verändert diese Relation nicht. Der historische Capability-Prompt-Copier und der heutige Prompt Mirror sind vom breiteren Provider-Copier zu unterscheiden; sie liefern keinen Anlass, beim Hinzufügen einer Modellalternative pauschal Now-LLM-Modellversionen zu kopieren. Eine spätere eigenständige Modellregistrierung muss ihre tatsächliche neue Modellidentität und gegebenenfalls ausdrücklich benötigte Versionsauflösung begründen; die sieben alten Vorlagen werden dafür weder kopiert noch automatisch aktiviert.

Unabhängig davon ist die **Prompt-Abstammung** über `sys_generative_ai_config.parent`/`version` und die zugehörigen `sys_generative_ai_prompt_config`-Bindings belegt. Der historische Capability-Copier und die vorhandene Mirror-Implementierung übernahmen Quellprompts einschließlich Zustand, Versionsnummer und Parent-Verknüpfungen. Die Prüfung vom 2. November belegte bei 228 gemappten Kopien identische Quellzustände und bei 227 identische Versionsnummern; außerdem fanden sich Quell- beziehungsweise kopierte Parent-Ketten. Ein kopierter, nichtleerer `provider_company`-Wert wurde dagegen nicht beobachtet. Dieser Befund ist von den sieben nativen Modell-Versionszuordnungen getrennt zu behandeln.

Das neue Add-Skript übernimmt nur ausgewählte aktuelle Promptinhalte. Jede neue Zielfamilie beginnt entsprechend dem geprüften nativen Clone-Verhalten mit `version: 1`, leerem `parent`, `state: 'draft'`, `active: false` und ohne Standardbindung. `provider_company` und `sys_overrides` werden nicht als Quellidentität übernommen. Spätere echte Zielrevisionen sollen durch native Veröffentlichung ihre eigene Prompt-Historie erhalten. Gemeinsame Validator-Skripte werden referenziert; neue Verweise zeigen auf die neue Definition oder den neuen Prompt.

Das Switch-Skript lehnt unvereinbare beziehungsweise nachweislich kopierte **Prompt-Abstammung** ab, statt sie umzuschreiben. Frühere echte Modellzuordnungen innerhalb einer gültigen Prompt-Zielhistorie bleiben erhalten. Diese Lieferung bereinigt oder löscht weder die sieben vorhandenen inaktiven Modell-Versionszuordnungen noch frühere fehlerhafte Prompt-Klone, Herstellerhistorien oder Auditdaten. Historische Copier, Mirror und die sealed 2.2-Lieferung bleiben unverändert und werden nicht erneut ausgeführt. Offen bleiben die genaue Darstellung unter dem modernen UI-Begriff „Model History“ sowie die fachliche Notwendigkeit jedes einzelnen vorhandenen nativen Version-Mappings; eine Korrektur des Add-Prompt-Verhaltens allein schließt diese Fragen nicht.

## Berechtigungen und Teilfehler

Standardmäßig erfolgen Schreibzugriffe über `GlideRecordSecure`. Wenn die Vorschau für eine konkret geprüfte eigene Konfiguration fehlende Schreibrechte zeigt, kann `allowAdminMaintenance: true` ausdrücklich den administrativen `GlideRecord`-Schreibweg erlauben. Dieser verlangt `admin`, behält sichere Vorprüfungen und normale Business Rules bei und ändert keine Rollen, ACLs oder Schutzregeln. Geschützte Herstellerziele bleiben ausgeschlossen.

Revisionen und Beziehungen werden vor Änderungen erneut geprüft; das ist keine Datenbanktransaktion. Insbesondere können Datensatzrechte nativ erzeugter Kinder erst nach deren Anlage vollständig geprüft werden. Deshalb sind `partial_or_uncertain` beim Switch beziehungsweise `Partial` beim Add keine Erfolgsmeldungen. Dann anhand von `attempted`/`writeAttempts`, abgeschlossenen Änderungen, Customer Updates und frischen Rücklesungen den tatsächlichen Stand ermitteln; keinen automatischen Wiederholungslauf starten. Auch eine fehlgeschlagene Wiederherstellung der Update-Set-Auswahl wird ausdrücklich gemeldet.

Switch-Ergebnisse sind `preview`, `applied`, `no_op`, `aborted` oder `partial_or_uncertain`; Add-Ergebnisse sind `Preview`, `Applied`, `NoOp`, `Refused` oder `Partial`. Native Prüfungen können nach Plattformänderungen bewusst mit einem nicht unterstützten Schema-/Generatorvertrag abbrechen. Dann die aktuelle native Implementierung neu prüfen, statt die Prüfung zu entfernen.

## Lieferumfang und geprüfte Grenze

Zu beiden Dateien gehören ausführbare lokale Tests: [Switch-Tests](../../servicenow/byollm/capability-model-management/switch-capability-models.test.cjs) und [Add-Tests](../../servicenow/byollm/capability-model-management/add-capability-model.test.cjs). Sie prüfen unter anderem Vorschau, Auswahl, Mehrdeutigkeit, Historie, Drift, Schreibrechte, native Kinder, Aufzeichnung und Teilfehler. Sie ersetzen keine Prüfung einer konkret ausgewählten Instanzkonfiguration.

Die Skripte wurden für wiederverwendbare Wartung erstellt; ein allgemeiner Add- oder Switch-Massenlauf wurde damit nicht ausgeführt. Eine native Switch-Vorschau für VA Input Response Generation mit Halogen wurde ohne Schreibzugriff geprüft. Sie meldete zwei aktive veröffentlichte Prompts: den bereits auf Halogen korrigierten Standardprompt und einen weiterhin Gemma zugeordneten Prompt ohne Standardbindung. Die separat freigegebene punktuelle Korrektur betraf nur den Standardprompt; die breitere Vorschau wurde nicht angewendet.

Auch Add wurde nativ ohne Schreibzugriff geprüft: Eine vorhandene VA-Input-Alternative blieb als `NoOp` erhalten; für AIA Unified Planner Quick lieferte der Global-Kontext eine vollständige `Preview` mit einem neuen Draft-Prompt und eigener Versionsfamilie. Der vorübergehend gewählte Anwendungskontext und das vorherige Update Set wurden danach wiederhergestellt. Der Live-Abgleich deckte zusätzlich die besondere Falschwertigkeit leerer nativer GlideElement-Objekte auf; die Skripte prüfen deren Existenz ausdrücklich, bevor sie weiterhin alle Leserechte und Schutzbedingungen prüfen. Ein Add-Apply und native Veröffentlichung sind dadurch noch nicht als ausgeführt belegt. Aus einer Metadatenkorrektur allein folgt keine vollständige Voice-Abnahme auf iPhone, Android oder Computer.
