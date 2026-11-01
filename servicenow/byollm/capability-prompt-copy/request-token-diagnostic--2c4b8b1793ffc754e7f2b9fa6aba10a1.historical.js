/*
 * Scripts - Background, Global.
 * Custom LLM Provider fuer die konfigurierten Capabilities anlegen oder aktualisieren.
 * Wiederholte Ausfuehrung speichert nur neue oder geaenderte Datensaetze.
 * Fehlende Request-/Response-Validator-Verknuepfungen werden ergaenzt.
 * Bestehende Validator-Verknuepfungen werden unveraendert uebersprungen.
 * Validator-Skripte werden referenziert, nicht kopiert oder veraendert.
 * Alle direkten Inserts/Updates mit setWorkflow(false).
 * Ein Batch mit einem Child-Update-Set pro gespeichertem Scope.
 */
(function () {
    var capabilityIds = [
"5f25e5d6eb121210a6b1f38acad0cdf0",
"88f0856eff1b02102284ffffffffff13",
"a9dc14d6431782104eaff03a5ab8f20d",
"ba543b97ff56d2102284ffffffffff0c",
"15fc377c4328311006650464dbb8f2d7",
"d23a7696434531106aa964746ab8f242",
"aca5634f4312121038520464dbb8f236",
"46e72819b71a42107880b25bee11a931",
"ed8111a6ffc82a10810bffffffffff9a",
"b3cc0c813732221034ccad3464924b58",
"1857ce78ff322210022dffffffffffa1",
"2073a1aeff5fe2101657ffffffffff97",
"d82ff09efffc311063f5ffffffffffc5",
"08243d277fb88b10893f19bec2794232"
    ];

    var settings = {
        nowFlow: "936e514a53b3b110f028ddeeff7b128c",
        customFlow: "af9702d0c3110210b0939bc8a840dd2c",
        alias: "a7b19ad193ff43d05c8132d47aba10c7",
        model: "halogen-v2",
        provider: "Custom LLM Provider",
        providerFilter: "Custom LLMcustom_api",
        mappingPrefix: "custom_llm.clone.map.",
        // Eindeutige Quelle aus deiner Diagnose; weitere Overrides sind optional.
        sourceDefinitions: {
            "a9dc14d6431782104eaff03a5ab8f20d": "dab21cb2ffc71210810bffffffffffef"
        },

        // Bereits angelegte Kopien: Zuordnung aus deinem ersten Ausfuehrungslog.
        existingCopies: {
            "826b5d3787e8c210fa6ecbfc0ebb3589": "ac77cc2d93f383d0e7f2b9fa6aba1008",
            "dd6221bf87a0c210f357646d0ebb357d": "6077cc2d93f383d0e7f2b9fa6aba1009",
            "458ccb69eb8a021053acf94fbad0cd25": "a0778c6d93f383d0e7f2b9fa6aba10e0",
            "fa60653b87e8c210fa6ecbfc0ebb3581": "e4778c6d93f383d0e7f2b9fa6aba10e0",
            "179ccb69eb8a021053acf94fbad0cd73": "2c778c6d93f383d0e7f2b9fa6aba10e0"
        }
    };

    var tables = {
        definition: "sys_one_extend_capability_definition",
        config: "sys_one_extend_definition_config",
        prompt: "sys_generative_ai_config",
        promptConfig: "sys_generative_ai_prompt_config",
        attribute: "sys_one_extend_definition_attribute",
        validator: "sys_generative_ai_validator",
        requestValidator: "sys_generative_ai_request_validator",
        responseValidator: "sys_generative_ai_response_validator"
    };

    var skip = {
        sys_id: true, sys_created_on: true, sys_created_by: true,
        sys_updated_on: true, sys_updated_by: true, sys_mod_count: true,
        sys_update_name: true, sys_name: true, sys_policy: true
    };

    var plans = [], idMap = {}, usedTargets = {}, seen = {};
    var batch = "", scopeSets = {}, defaultChanges = [], writes = 0;
    var unchanged = 0, plannedValidatorLinks = {};
    var validatorSchemas = {};
    var validatorStats = { inserted: 0, skipped: 0 };
    var batchName = "Custom LLM - " + gs.nowDateTime();
    var result;
    var diagFields = {};

    try {
        if (!gs.hasRole("admin"))
            throw new Error("Ausfuehrung erfordert admin.");

        getRecord("sys_hub_flow", settings.customFlow);
        getRecord("sys_alias", settings.alias);

        var model = openTable("sys_generative_ai_model_config");
        if (!model.get("model", settings.model))
            throw new Error("Modell zuerst konfigurieren: " + settings.model);

        validateValidatorTables();

        // 1. Quellen und bestehende Kopien zuordnen, noch ohne Datenbank-Aenderungen.
        for (var i = 0; i < capabilityIds.length; i++) {
            var capabilityId = String(capabilityIds[i])
                .replace(/^\s+|\s+$/g, "")
                .toLowerCase();

            if (!capabilityId || seen[capabilityId]) continue;
            seen[capabilityId] = true;

            gs.info("[Custom LLM] Pruefe " + (i + 1) + "/" +
                capabilityIds.length + ": " + capabilityId);

            plans.push(planCapability(capabilityId));
        }

        // Alle Ziel-IDs stehen jetzt fest; auch Verknuepfungen vor Writes pruefen.
        for (i = 0; i < plans.length; i++) {
            planValidatorLinks(plans[i]);
        }

        // 2. Nur Deltas speichern. Der Batch entsteht erst beim ersten Write.

        for (i = 0; i < plans.length; i++) {
            var plan = plans[i];

            gs.info("[Custom LLM] Verarbeite " + (i + 1) + "/" +
                plans.length + ": " + plan.capability);

            for (var j = 0; j < plan.records.length; j++) {
                copyRecord(plan.records[j]);
                saveMapping(plan.records[j], plan);
            }

            for (j = 0; j < plan.validatorLinks.length; j++) {
                var link = plan.validatorLinks[j];

                // Erneute Pruefung direkt vor Insert, auch bei Wiederholungen.
                if (findValidatorLink(link.source, link.bindings)) {
                    validatorStats.skipped++;
                    continue;
                }

                copyRecord(link);
                validatorStats.inserted++;
            }
        }

        // 3. Erst nach allen erfolgreichen Kopien den Custom-Provider als Default setzen.
        for (i = 0; i < plans.length; i++) {
            var selectedDomains = {};

            // Wie bisher gewinnt pro Domain die letzte Konfiguration im Plan.
            // Rueckwaerts abgleichen verhindert zwischenzeitliches Umschalten.
            for (j = plans[i].configs.length - 1; j >= 0; j--) {
                var desired = getRecord(tables.config, plans[i].configs[j]);
                var domainKey = "domain:" + (desired.isValidField("sys_domain") ?
                    desired.getValue("sys_domain") || "" : "");

                if (selectedDomains[domainKey]) {
                    setDefault(desired, false, true);
                    continue;
                }

                selectedDomains[domainKey] = true;
                var old = openTable(tables.config);

                old.addQuery("capability", plans[i].capability);
                old.addQuery("default", true);
                old.addQuery("sys_id", "!=", desired.getUniqueValue());
                sameDomain(old, desired);
                old.query();

                while (old.next()) {
                    setDefault(
                        getRecord(tables.config, old.getUniqueValue()),
                        false
                    );
                }

                setDefault(desired, true);
            }
        }

        result = {
            ok: true,
            capabilities: plans.length,
            batch: batch,
            writes: writes,
            unchanged: unchanged,
            validatorLinksInserted: validatorStats.inserted,
            validatorLinksSkipped: validatorStats.skipped
        };
    } catch (e) {
        // Nur bereits umgeschaltete Defaults zuruecksetzen; kein Rollback der Kopien.
        for (var r = defaultChanges.length - 1; r >= 0; r--) {
            try {
                var previous = defaultChanges[r];
                var record = getRecord(tables.config, previous.id);

                record.setValue("default", previous.value);

                if (record.isValidField("active"))
                    record.setValue("active", previous.active || "");

                save(record);
            } catch (restoreError) {
                gs.error("[Custom LLM] Default-Restore: " + restoreError);
            }
        }

        result = {
            ok: false,
            error: String(e),
            batch: batch,
            writes: writes,
            unchanged: unchanged,
            validatorLinksInserted: validatorStats.inserted,
            validatorLinksSkipped: validatorStats.skipped
        };

        gs.error("[Custom LLM] " + JSON.stringify(result));
    }

    gs.info("[Delta DIAG] Field counts: " + JSON.stringify(diagFields));
    gs.info("[Custom LLM] Ergebnis: " + JSON.stringify(result));

    function openTable(table) {
        var gr = new GlideRecord(table);
        gr.setWorkflow(false);
        return gr;
    }

    function getRecord(table, id) {
        var gr = openTable(table);

        if (!gr.get("sys_id", id))
            throw new Error("Record fehlt: " + table + "/" + id);

        return gr;
    }

    function oneRecord(gr, context) {
        gr.query();

        if (!gr.next()) return null;

        if (gr.hasNext())
            throw new Error("Mehrdeutige Zuordnung in " + gr.getTableName() +
                (context ? "; " + context : ""));

        return gr;
    }

    function sameDomain(query, source) {
        if (source.isValidField("sys_domain"))
            query.addQuery("sys_domain", source.getValue("sys_domain") || "");
    }

    function validateValidatorTables() {
        var validator = openTable(tables.validator);

        if (!validator.isValid())
            throw new Error("Tabelle fehlt: " + tables.validator);

        var linkTables = [tables.requestValidator, tables.responseValidator];
        var required = ["validator", "order"];
        var ownerTables = {};
        ownerTables[tables.definition] = true;
        ownerTables[tables.config] = true;
        ownerTables[tables.attribute] = true;
        ownerTables[tables.prompt] = true;
        ownerTables[tables.promptConfig] = true;
        ownerTables.sys_one_extend_capability = true;

        for (var i = 0; i < linkTables.length; i++) {
            var link = openTable(linkTables[i]);

            if (!link.isValid())
                throw new Error("Tabelle fehlt: " + linkTables[i]);

            for (var j = 0; j < required.length; j++) {
                if (!link.isValidField(required[j])) {
                    throw new Error(
                        "Validator-Feld fehlt: " + linkTables[i] + "." + required[j]
                    );
                }
            }

            // Request und Response koennen unterschiedliche Dictionaries haben.
            // initialize() liefert die Feldbeschreibungen, ohne etwas zu speichern.
            link.initialize();
            var fields = link.getFields();
            var fieldNames = [];
            var schema = {
                documentTableField: link.isValidField("document_table") ?
                    "document_table" : "",
                hasDocument: false,
                owners: []
            };

            for (j = 0; j < fields.size(); j++) {
                var element = fields.get(j);
                var field = String(element.getName());
                var type = String(element.getED().getInternalType());
                fieldNames.push(field);

                if (field === "document_id" || type === "document_id") {
                    schema.owners.push({ field: field, document: true, table: "" });
                    schema.hasDocument = true;
                } else if (type === "reference" && field !== "validator") {
                    // Dokumentierte GlideElement-API; funktioniert auch bei leerer Reference.
                    var referencedTable = String(element.getRefRecord().getTableName());

                    if (ownerTables[referencedTable]) {
                        schema.owners.push({
                            field: field, document: false, table: referencedTable
                        });
                    }
                }
            }

            if (!schema.owners.length) {
                throw new Error(
                    "Keine Validator-Zuordnung erkannt: " + linkTables[i] +
                    "; vorhandene Felder: " + fieldNames.join(", ")
                );
            }

            validatorSchemas[linkTables[i]] = schema;
            gs.info("[Custom LLM] Validator-Schema " + linkTables[i] + ": " +
                JSON.stringify(schema));
        }
    }

    function validatorBindings(source, schema) {
        var bindings = {};

        for (var i = 0; i < schema.owners.length; i++) {
            var field = schema.owners[i].field;
            var value = source.getValue(field) || "";
            bindings[field] = idMap[value] || value;
        }

        if (schema.hasDocument && schema.documentTableField) {
            bindings[schema.documentTableField] =
                source.getValue(schema.documentTableField) || "";
        }

        return bindings;
    }

    function findValidatorLink(source, bindings) {
        var existing = openTable(source.getTableName());

        for (var field in bindings) {
            if (Object.prototype.hasOwnProperty.call(bindings, field))
                existing.addQuery(field, bindings[field]);
        }

        existing.addQuery("validator", source.getValue("validator"));
        sameDomain(existing, source);
        existing.setLimit(1);
        existing.query();

        // Bereits eine passende Zuordnung reicht: kein Update, kein Duplikat.
        return existing.next();
    }

    function planValidatorLinks(plan) {
        plan.validatorLinks = [];
        var linkTables = [tables.requestValidator, tables.responseValidator];
        var parents = plan.records.slice(0);
        var seenSources = {};
        var capability = getRecord("sys_one_extend_capability", plan.capability);

        // Capability-weite Validatoren sind beim Providerwechsel bereits vorhanden.
        parents.push({ source: capability, target: capability });

        // Provider-Definition und ihre kopierten Konfigurationen/Prompts abgleichen.
        for (var i = 0; i < parents.length; i++) {
            var parent = parents[i];
            var documentTable = parent.source.getTableName();

            for (var j = 0; j < linkTables.length; j++) {
                var schema = validatorSchemas[linkTables[j]];

                for (var k = 0; k < schema.owners.length; k++) {
                    var owner = schema.owners[k];

                    if (!owner.document && owner.table !== documentTable)
                        continue;

                    var links = openTable(linkTables[j]);
                    links.addQuery(owner.field, parent.source.getUniqueValue());

                    if (owner.document && schema.documentTableField) {
                        links.addQuery(schema.documentTableField, documentTable)
                            .addOrCondition(schema.documentTableField, "");
                    }

                    links.orderBy("order");
                    links.orderBy("sys_id");
                    links.query();

                    while (links.next()) {
                        var sourceKey = linkTables[j] + "/" + links.getUniqueValue();

                        if (seenSources[sourceKey]) continue;
                        seenSources[sourceKey] = true;

                        var source = getRecord(linkTables[j], links.getUniqueValue());
                        var validatorId = source.getValue("validator");

                        if (!validatorId) {
                            throw new Error("Validator-Referenz fehlt: " + sourceKey);
                        }

                        getRecord(tables.validator, validatorId);

                        var bindings = validatorBindings(source, schema);
                        var key = [
                            linkTables[j], validatorId, JSON.stringify(bindings),
                            source.getValue("sys_domain") || ""
                        ].join("|");

                        if (plannedValidatorLinks[key] ||
                            findValidatorLink(source, bindings)) {
                            validatorStats.skipped++;
                            continue;
                        }

                        var target = openTable(linkTables[j]);
                        target.initialize();
                        target.setNewGuid();

                        plan.validatorLinks.push({
                            source: source,
                            target: target,
                            bindings: bindings
                        });

                        plannedValidatorLinks[key] = true;
                    }
                }
            }
        }
    }

    function providerName(name) {
        return String(name || "").replace(
            /\(\s*(?:Now[\s_]*LLM|llm_generic|Custom[\s_]+LLM)(?=[\s_)])([^()]*)\)/gi,
            function (match, suffix) {
                var version = suffix.match(
                    /(?:^|[\s_])V(\d+(?:\.\d+)*)(?=$|[\s_])/i
                );

                return "(" + settings.provider +
                    (version ? " V" + version[1] : "") + ")";
            }
        );
    }

    function description(text, name) {
        var value = providerName(text).replace(
            /\b(?:Now[\s_]*LLM(?:[\s_]+(?:Generic|Large|Small|Medium|LTS|V\d+(?:\.\d+)*))*|llm_generic(?:_[a-z0-9]+)*|Custom[\s_]+LLM(?:[\s_]+Provider)?)\b/gi,
            settings.provider
        ).replace(
            /\([^()\r\n]*\)(?=\s+using\s+Custom\s+LLM\s+Provider\b)/gi,
            "(" + settings.model + ")"
        );

        return /\S/.test(value) ? value :
            name.replace(/\s*\([^()]*\)\s*$/, "") +
            " (" + settings.model + ") using " + settings.provider;
    }

    function filter(raw, forceProvider) {
        var value = raw ? JSON.parse(String(raw)) : {};

        if (forceProvider ||
            Object.prototype.hasOwnProperty.call(value, "provider")) {
            value.provider = settings.providerFilter;
            return JSON.stringify(value);
        }

        return raw || "";
    }

    function filterKey(raw) {
        var value = raw ? JSON.parse(String(raw)) : {};
        var keys = [], parts = [];

        for (var key in value) {
            if (Object.prototype.hasOwnProperty.call(value, key) &&
                key !== "provider") {
                keys.push(key);
            }
        }

        keys.sort();

        for (var i = 0; i < keys.length; i++) {
            parts.push(
                JSON.stringify(keys[i]) + ":" +
                JSON.stringify(value[keys[i]])
            );
        }

        return parts.join(",");
    }

    // Bestehende Kopien ueber gespeichertes Mapping oder passende Datensaetze finden.
    function findTarget(source, definitionId) {
        var table = source.getTableName();
        var sourceId = source.getUniqueValue();
        var property = openTable("sys_properties");
        var mapping;

        if (property.get("name", settings.mappingPrefix + sourceId)) {
            mapping = JSON.parse(property.getValue("value"));
        } else if (settings.existingCopies[sourceId]) {
            mapping = {
                table: table,
                source: sourceId,
                target: settings.existingCopies[sourceId],
                providerFlow: settings.customFlow
            };
        }

        if (mapping) {
            if (mapping.table !== table ||
                mapping.source !== sourceId ||
                mapping.target === sourceId) {
                throw new Error("Mapping passt nicht zur Quelle: " + sourceId);
            }

            var mapped = getRecord(table, mapping.target);
            var wrongTarget;

            if (table === tables.promptConfig) {
                wrongTarget =
                    mapped.getValue("ai_config") !==
                    idMap[source.getValue("ai_config")];
            } else if (definitionId) {
                wrongTarget =
                    mapped.getValue("definition") !== definitionId;
            } else {
                wrongTarget =
                    mapped.getValue("capability") !== source.getValue("capability") ||
                    (mapped.getValue("api") !== settings.customFlow &&
                        mapped.getValue("api") !== mapping.providerFlow);
            }

            if (wrongTarget) {
                throw new Error(
                    "Mapping zeigt auf einen anderen Provider/Skill: " + sourceId
                );
            }

            return mapped;
        }

        var target = openTable(table);
        sameDomain(target, source);

        if (!definitionId) {
            target.addQuery("capability", source.getValue("capability"));
            target.addQuery("api", settings.customFlow);
        } else {
            if (table !== tables.promptConfig)
                target.addQuery("definition", definitionId);

            var fields = table === tables.prompt ?
                ["version", "prompt_template_role"] :
                table === tables.attribute ?
                    ["attribute", "name", "input", "direction"] : [];

            for (var i = 0; i < fields.length; i++) {
                if (source.isValidField(fields[i])) {
                    target.addQuery(
                        fields[i],
                        source.getValue(fields[i]) || ""
                    );
                }
            }

            if (table === tables.prompt) {
                var renamed = providerName(source.getValue("name"));

                target.addQuery("name", source.getValue("name"))
                    .addOrCondition("name", renamed)
                    .addOrCondition(
                        "name",
                        renamed.replace(/\(Custom LLM Provider\b/gi, "(Custom LLM")
                    );
            }

            if (table === tables.promptConfig) {
                target.addQuery(
                    "ai_config",
                    idMap[source.getValue("ai_config")]
                );
                target.addQuery("is_default", source.getValue("is_default"));
                target.query();

                var found = "";

                while (target.next()) {
                    if (filterKey(target.getValue("filter_properties")) !==
                        filterKey(source.getValue("filter_properties"))) {
                        continue;
                    }

                    if (found)
                        throw new Error("Mehrere passende Prompt Configs: " + sourceId);

                    found = target.getUniqueValue();
                }

                return found ? getRecord(table, found) : null;
            }
        }

        return oneRecord(target, "Custom-LLM-Ziel fuer Quelle " + sourceId);
    }

    function planRecord(source, definitionId, plan) {
        source = getRecord(source.getTableName(), source.getUniqueValue());

        var target = findTarget(source, definitionId);
        var created = !target;

        if (!target) {
            target = openTable(source.getTableName());
            target.initialize();
            target.setNewGuid();
        }

        var id = target.getUniqueValue();

        if (usedTargets[id])
            throw new Error("Ziel mehreren Quellen zugeordnet: " + id);

        usedTargets[id] = source.getUniqueValue();
        idMap[source.getUniqueValue()] = id;

        plan.records.push({
            source: source,
            target: target,
            created: created,
            definition: definitionId
        });

        if (source.getTableName() === tables.config)
            plan.configs.push(id);

        return id;
    }

    function sourceDefinition(capabilityId) {
        var source = openTable(tables.definition);

        source.addQuery("capability", capabilityId);
        source.addQuery("api", settings.nowFlow);

        if (settings.sourceDefinitions[capabilityId]) {
            source.addQuery(
                "sys_id",
                settings.sourceDefinitions[capabilityId]
            );

            return oneRecord(source, "NowLLM-Quelle fuer Capability " + capabilityId);
        }

        source.orderBy("sys_id");
        source.query();
        var candidates = [], activeIds = [];

        while (source.next()) {
            var sourceId = source.getUniqueValue();
            var configs = openTable(tables.config);
            var active = false;

            if (configs.isValidField("active")) {
                configs.addQuery("capability", capabilityId);
                configs.addQuery("definition", sourceId);
                configs.addQuery("active", true);
                sameDomain(configs, source);
                configs.setLimit(1);
                configs.query();
                active = configs.next();
            }

            candidates.push({
                id: sourceId,
                name: source.getValue("name"),
                scope: source.getValue("sys_scope"),
                domain: source.getValue("sys_domain"),
                active: active
            });

            if (active) activeIds.push(sourceId);
        }

        if (!candidates.length) return null;

        if (candidates.length === 1)
            return getRecord(tables.definition, candidates[0].id);

        if (activeIds.length === 1) {
            gs.info("[Custom LLM] Eindeutig aktive NowLLM-Quelle fuer " +
                capabilityId + ": " + activeIds[0]);
            return getRecord(tables.definition, activeIds[0]);
        }

        throw new Error(
            "Mehrdeutige NowLLM-Quelle fuer Capability " + capabilityId +
            "; sourceDefinitions explizit setzen. Kandidaten: " +
            JSON.stringify(candidates)
        );
    }

    function planCapability(capabilityId) {
        var capability = getRecord("sys_one_extend_capability", capabilityId);
        var source = sourceDefinition(capabilityId);

        if (!source) {
            throw new Error(
                "Keine NowLLM-Definition fuer " + capability.getDisplayValue()
            );
        }

        var plan = {
            capability: capabilityId,
            records: [],
            configs: []
        };

        plan.definition = planRecord(source, "", plan);

        var sourceId = source.getUniqueValue();
        var children = [
            tables.config,
            tables.attribute,
            tables.prompt,
            tables.promptConfig
        ];

        var promptIds = [], targetPromptIds = [], promptConfigCount = 0;

        for (var i = 0; i < children.length; i++) {
            var child = openTable(children[i]);

            if (children[i] === tables.attribute && !child.isValid())
                continue;

            // Prompt Configs werden ueber ai_config ausgewaehlt.
            if (children[i] === tables.promptConfig) {
                child.addQuery("ai_config", "IN", promptIds.join(","));
            } else {
                child.addQuery("definition", sourceId);
            }

            child.orderBy("sys_id");
            child.query();

            while (child.next()) {
                if (children[i] === tables.prompt) {
                    if (child.getValue("definition_table") !== tables.definition) {
                        throw new Error(
                            "Falsche Prompt-Definition: " + child.getUniqueValue()
                        );
                    }

                    promptIds.push(child.getUniqueValue());
                }

                if (children[i] === tables.promptConfig)
                    promptConfigCount++;

                var targetId = planRecord(child, plan.definition, plan);

                if (children[i] === tables.prompt)
                    targetPromptIds.push(targetId);
            }

            // Nicht zugeordnete alte Kopien vor weiteren Inserts melden.
            var existing = openTable(children[i]);

            if (children[i] === tables.promptConfig) {
                existing.addQuery("ai_config", "IN", targetPromptIds.join(","));
            } else {
                existing.addQuery("definition", plan.definition);
            }

            existing.query();

            while (existing.next()) {
                if (!usedTargets[existing.getUniqueValue()]) {
                    throw new Error(
                        "Bestehende Kopie nicht eindeutig zugeordnet: " +
                        children[i] + "/" + existing.getUniqueValue()
                    );
                }
            }
        }

        if (!plan.configs.length || !promptIds.length || !promptConfigCount)
            throw new Error("Unvollstaendige Quelle: " + sourceId);

        return plan;
    }

    // Alle direkten Inserts und Updates verwenden setWorkflow(false).
    function save(gr, captureRecord) {
        var recordId = String(gr.getUniqueValue() || "");
        var saved = openTable(gr.getTableName());
        if (!recordId || !saved.get("sys_id", recordId)) {
            gs.info("[Delta DIAG] Would insert: " + gr.getTableName() + "/" + recordId);
            return recordId;
        }
        var fields = gr.getFields(), changed = false;
        for (var i = 0; i < fields.size(); i++) {
            var element = fields.get(i), field = String(element.getName());
            if (skip[field]) continue;
            var expected = String(gr.getValue(field) || "");
            var actual = String(saved.getValue(field) || "");
            if (expected === actual) continue;
            changed = true;
            var key = gr.getTableName() + "." + field;
            diagFields[key] = (diagFields[key] || 0) + 1;
            if (diagFields[key] === 1) {
                var privateField = /password|secret|token|credential|prompt|script/i.test(field);
                gs.info("[Delta DIAG] " + JSON.stringify({table:gr.getTableName(), id:recordId, field:field, type:String(element.getED().getInternalType()), expected:privateField || expected.length > 240 ? "[length " + expected.length + "]" : expected, actual:privateField || actual.length > 240 ? "[length " + actual.length + "]" : actual}));
            }
        }
        if (!changed) unchanged++;
        return recordId;
    }

    function hasChanges(gr, saved) {
        var fields = gr.getFields();

        // Endzustand vergleichen, erst nach allen Provider-Anpassungen.
        for (var i = 0; i < fields.size(); i++) {
            var field = String(fields.get(i).getName());

            if (skip[field]) continue;

            if (String(gr.getValue(field) || "") !==
                String(saved.getValue(field) || "")) {
                return true;
            }
        }

        return false;
    }

    function newUpdateSet(scope, parent) {
        var set = openTable("sys_update_set");
        set.initialize();
        set.setNewGuid();

        set.setValue("name", batchName + (parent ? " / " + scope : ""));
        set.setValue("application", scope);
        set.setValue("state", "in progress");

        if (parent) set.setValue("parent", parent);

        if (set.isValidField("base_update_set"))
            set.setValue("base_update_set", parent || set.getUniqueValue());

        return save(set, false);
    }

    function capture(gr) {
        var scope = gr.getValue("sys_scope") || "global";

        if (!scopeSets[scope])
            scopeSets[scope] = newUpdateSet(scope, batch);

        var previous = gs.getPreference("sys_update_set");

        try {
            // Dokumentierter Fallback ohne UpdateManager2(string).
            new GlideUpdateSet().set(scopeSets[scope]);
            new GlideUpdateManager2().saveRecord(gr);

            var update = openTable("sys_update_xml");
            update.addQuery("update_set", scopeSets[scope]);
            update.addQuery(
                "name",
                gr.getValue("sys_update_name") ||
                    gr.getTableName() + "_" + gr.getUniqueValue()
            );
            update.query();

            if (!update.next()) {
                throw new Error(
                    "Nicht im Update Set erfasst: " +
                    gr.getTableName() + "/" + gr.getUniqueValue()
                );
            }
        } finally {
            new GlideUpdateSet().set(previous);
        }
    }

    function copyRecord(item) {
        var source = item.source;
        var target = item.target;
        var table = source.getTableName();
        var fields = source.getFields();

        for (var i = 0; i < fields.size(); i++) {
            var element = fields.get(i);
            var field = String(element.getName());

            if (skip[field]) continue;

            if (table === tables.config &&
                (field === "default" || field === "active")) {
                continue;
            }

            var value = source.getValue(field) || "";

            if ((field === "sys_scope" || field === "sys_package") && !value)
                continue;

            var type = String(element.getED().getInternalType());

            if (type === "reference" ||
                field === "definition" ||
                field === "ai_config") {
                value = idMap[value] || value;
            }

            if (type === "glide_list") {
                var ids = value.split(",");

                for (var j = 0; j < ids.length; j++)
                    ids[j] = idMap[ids[j]] || ids[j];

                value = ids.join(",");
            }

            target.setValue(field, value);
        }

        if (table === tables.definition) {
            var name = providerName(source.getValue("name"));

            if (name.indexOf("(" + settings.provider) < 0)
                name += " (" + settings.provider + ")";

            target.setValue("name", name);

            if (target.isValidField("description")) {
                target.setValue(
                    "description",
                    description(source.getValue("description"), name)
                );
            }

            target.setValue("api", settings.customFlow);
            target.setValue("api_type", "sys_hub_flow");
            target.setValue("connection", settings.alias);
            target.setValue(
                "filter_properties",
                filter(source.getValue("filter_properties"), true)
            );
        }

        if (table === tables.prompt) {
            target.setValue("name", providerName(source.getValue("name")));
            target.setValue("model", settings.model);
        }

        if (table === tables.promptConfig) {
            if (target.isValidField("definition"))
                target.setValue("definition", item.definition);

            target.setValue(
                "filter_properties",
                filter(source.getValue("filter_properties"), false)
            );
        }

        if (table === tables.requestValidator || table === tables.responseValidator) {
            // Nur die tatsaechlich vorhandenen Zuordnungsfelder schreiben.
            for (var binding in item.bindings) {
                if (Object.prototype.hasOwnProperty.call(item.bindings, binding))
                    target.setValue(binding, item.bindings[binding]);
            }

            target.setValue("validator", source.getValue("validator"));
        }

        if (table === tables.config && item.created) {
            target.setValue("default", false);

            if (target.isValidField("active"))
                target.setValue("active", false);
        }

        save(target);
    }

    function saveMapping(item, plan) {
        var source = item.source;
        var property = openTable("sys_properties");
        var name = settings.mappingPrefix + source.getUniqueValue();

        if (!property.get("name", name)) {
            property.initialize();
            property.setValue("name", name);
            property.setValue("type", "string");
            property.setValue("ignore_cache", true);
            property.setValue("sys_scope", "global");
            property.setValue("sys_package", "global");
        }

        property.setValue("value", JSON.stringify({
            table: source.getTableName(),
            source: source.getUniqueValue(),
            target: item.target.getUniqueValue(),
            capability: plan.capability,
            definition: plan.definition,
            providerFlow: settings.customFlow
        }));

        save(property);
    }

    function setDefault(gr, selected, forceActive) {
        var currentDefault = gr.getValue("default");
        var currentActive = gr.getValue("active");
        var defaultSelected = currentDefault === "1" || currentDefault === "true";
        var activeSelected = currentActive === "1" || currentActive === "true";
        var activate = selected || forceActive === true;

        if (defaultSelected === selected &&
            (!activate || !gr.isValidField("active") || activeSelected)) {
            return;
        }

        defaultChanges.push({
            id: gr.getUniqueValue(),
            value: gr.getValue("default"),
            active: gr.getValue("active")
        });

        gr.setValue("default", selected);

        if (activate && gr.isValidField("active"))
            gr.setValue("active", true);

        save(gr);
    }
})();
