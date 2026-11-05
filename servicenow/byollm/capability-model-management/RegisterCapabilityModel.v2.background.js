/* Registrar v2. Standalone ES5, Global / Scripts - Background. Preview is the default.
 * Registers a new model and its OWN transformer beneath an existing supported
 * Custom LLM implementation. Registration, Add and publication are separate.
 * Ordinary GlideRecordSecure insert follows classic Submit's primitive with
 * normal rules/capture. No administrative fallback, source writes or deletes.
 * Current dictionary / Submit / BR evidence: MODEL-REGISTRATION-NATIVE-EVIDENCE.md
 * (2026-11-03). Native metadata flags/search ingestion remain normal effects.
 */
(function () {
    var PARAMETERS = {
        apply: false,
        targetModel: '',
        displayName: '',
        sourceModelConfigId: '',
        sourceTransformerId: '',
        providerMappingId: '',
        providerId: '',
        connectionAliasId: '', // Exact existing source-model alias; mapping alias is retained separately.
        capabilityIds: [], // Only an Add handoff; registration never selects capabilities.
        maxTokens: null, // Explicit reviewed model contract, never inherited.
        outputTokenSize: null,
        active: false,
        thinkingEnabled: false,
        enableFunctionCalling: false,
        loggingEnabled: false,
        logSamplingPercentage: 100,
        expectedSourceGraphHash: '', // From the reviewed preview, including source revisions.
        expectedRequestHash: '', // SHA-256 of exact reviewed source content.
        expectedResponseHash: '',
        scriptCopyMode: 'exact', // Default legacy <=4000 exact copy; no newline changes.
        reviewedLongCopy: null, // Explicit source IDs/ownership/revisions/hashes/lengths manifest.
        expectedCopiedRequestHash: '', // Reviewed LF-derived copy hashes; required for LF Apply.
        expectedCopiedResponseHash: '',
        updateSetId: ''
    };
    var supplied =
            typeof CapabilityModelRegisterParameters !== 'undefined'
                ? CapabilityModelRegisterParameters
                : {},
        key;
    for (key in supplied) {
        if (Object.prototype.hasOwnProperty.call(supplied, key)) {
            PARAMETERS[key] = supplied[key];
        }
    }
    var P = PARAMETERS,
        M = 'sys_generative_ai_model_config',
        T = 'sys_generative_ai_custom_llm_transformer',
        V = 'sys_gen_ai_model_version_mapping',
        E = 'sys_es_latest_script';
    var result = {
        version: 2,
        operation: 'RegisterCapabilityModel',
        apply: P.apply === true,
        status: 'Refused',
        issues: [],
        writeAttempts: [],
        writes: [],
        captures: [],
        inventories: [],
        handoff: { readyForAdd: false },
        limitations: [
            'Query-before-insert is not atomic uniqueness; races require review, never retry/delete.',
            'Normal native metadata flags/search ingestion may occur; no model runtime is invoked.'
        ]
    };
    var guards = [],
        queryGuards = [],
        restoring = false,
        previousSet = '',
        updateSets,
        stage = 'preflight',
        source,
        transformer,
        mapping,
        provider,
        modelValues,
        transformerValues,
        modelPrototype,
        transformerPrototype,
        targetId = '',
        transformerId = '',
        registrationComplete = false,
        copiedScripts = {},
        reviewedScriptCopy = false;
    var modelContract = {
        model: ['string', 100],
        model_display_name: ['string', 100],
        provider: ['reference', 32, 'sys_generative_ai_provider_mapping', true],
        connection: ['reference', 32, 'sys_alias'],
        active: ['boolean', 40],
        lifecycle_state: ['choice', 40],
        model_type: ['choice', 40, '', false, 'LLM'],
        max_tokens: ['integer', 40, '', false, '500'],
        output_token_size: ['integer', 40],
        thinking_enabled: ['boolean', 40, '', false, 'false'],
        enable_function_calling: ['boolean', 40],
        availability_at_instance: ['boolean', 40, '', false, 'true'],
        external: ['boolean', 40, '', false, 'true'],
        logging_enabled: ['boolean', 40, '', false, 'true'],
        log_sampling_percentage: ['integer', 40, '', false, '100'],
        preceding_model_config: ['reference', 32, M],
        sys_overrides: ['reference', 32, M],
        model_source: ['string', 40, '', false, 'customer', true],
        usage_mode: ['string', 40, '', false, 'none', true]
    };
    var transformerContract = {
        model: ['reference', 32, M, true],
        request_transformer: ['script', 4000],
        response_transformer: ['script', 4000]
    };
    var schema = {};
    schema[M] = keys(modelContract);
    schema[T] = keys(transformerContract);
    schema[V] = ['target_model_name'];
    // Native read-only companion, never a registration write target.
    schema[E] = ['id','table','use_es_latest','sys_created_by','sys_created_on','sys_updated_by','sys_updated_on'];
    schema.sys_generative_ai_provider_mapping = [
        'provider',
        'provider_api',
        'provider_implementation',
        'provider_implementation_document',
        'gen_ai_provider',
        'connection',
        'active'
    ];
    schema.sys_gen_ai_provider = ['gen_ai_provider'];
    schema.sys_hub_flow = ['name', 'status'];
    schema.sys_alias = ['name', 'type'];
    schema.sys_one_extend_capability = ['name', 'active'];
    schema.sys_dictionary = [
        'name',
        'element',
        'internal_type',
        'reference',
        'mandatory',
        'read_only',
        'max_length',
        'default_value',
        'attributes'
    ];
    schema.sys_choice = ['name', 'element', 'value', 'inactive'];
    schema.sys_update_set = ['application', 'state', 'parent', 'name'];
    schema.sys_update_xml = ['name', 'update_set', 'action', 'payload', 'application'];
    // Registration rows are source-proven sys_metadata children. Infrastructure
    // and transport rows have their own contracts; application, not sys_scope,
    // identifies the transport's application. Do not invent metadata inheritance.
    var snapshotIdentity = {};
    snapshotIdentity[M] = ['sys_id', 'sys_mod_count', 'sys_scope', 'sys_package', 'sys_policy'];
    snapshotIdentity[T] = ['sys_id', 'sys_mod_count', 'sys_scope', 'sys_package', 'sys_policy'];
    snapshotIdentity[V] = ['sys_id', 'sys_mod_count'];
    snapshotIdentity[E] = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_generative_ai_provider_mapping = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_gen_ai_provider = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_hub_flow = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_alias = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_one_extend_capability = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_dictionary = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_choice = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_update_set = ['sys_id', 'sys_mod_count'];
    snapshotIdentity.sys_update_xml = ['sys_id', 'sys_mod_count'];

    function own(o, n) {
        return Object.prototype.hasOwnProperty.call(o, n);
    }
    function keys(o) {
        var out = [],
            n;
        for (n in o) {
            if (own(o, n)) {
                out.push(n);
            }
        }
        return out.sort();
    }
    function str(v) {
        return v === null || typeof v === 'undefined' ? '' : String(v);
    }
    function yes(v) {
        return v === true || v === 'true' || v === '1' || v === 1;
    }
    function validId(v) {
        return /^[0-9a-f]{32}$/.test(str(v));
    }
    function fail(message) {
        var e = new Error(message);
        e.registrarIssue = true;
        throw e;
    }
    function check(ok, message) {
        if (!ok) {
            fail(message);
        }
    }
    function canonical(v) {
        var out = [],
            names,
            i;
        if (v === null || typeof v !== 'object') {
            return JSON.stringify(v);
        }
        if (Object.prototype.toString.call(v) === '[object Array]') {
            for (i = 0; i < v.length; i++) {
                out.push(canonical(v[i]));
            }
            return '[' + out.join(',') + ']';
        }
        names = keys(v);
        for (i = 0; i < names.length; i++) {
            out.push(JSON.stringify(names[i]) + ':' + canonical(v[names[i]]));
        }
        return '{' + out.join(',') + '}';
    }
    function hash(v) {
        return str(
            new GlideDigest().getSHA256Hex(typeof v === 'string' ? v : canonical(v))
        ).toLowerCase();
    }
    function utf8Length(s) {
        var n=0,i,c,d;
        for(i=0;i<s.length;i++) {
            c=s.charCodeAt(i);
            if(c<128)n++;
            else if(c<2048)n+=2;
            else if(c>=55296&&c<=56319&&i+1<s.length&&(d=s.charCodeAt(i+1))>=56320&&d<=57343){n+=4;i++;}
            else n+=3;
        }
        return n;
    }
    function scriptFacts(s) {
        return {hash:hash(s),characters:s.length,utf8Bytes:utf8Length(s)};
    }
    function prepareScriptCopy() {
        var request=transformer.request_transformer,response=transformer.response_transformer;
        if(P.scriptCopyMode==='reviewed-lf-copy-v1') {
            var q=P.reviewedLongCopy,allowed=['sourceModelConfigId','sourceTransformerId','sourceModelScope','sourceModelPackage','sourceTransformerScope','sourceTransformerPackage','sourceModelRevision','sourceTransformerRevision','requestHash','responseHash','requestCharacters','requestUtf8Bytes','responseCharacters','responseUtf8Bytes'];
            check(q&&Object.prototype.toString.call(q)==='[object Object]'&&keys(q).length===allowed.length,'CompleteReviewedLongCopyManifestRequired');
            for(var i=0;i<allowed.length;i++)check(own(q,allowed[i]),'ReviewedLongCopyFieldRequired:'+allowed[i]);
            check(q.sourceModelConfigId===source.sys_id&&q.sourceTransformerId===transformer.sys_id&&
                q.sourceModelScope===source.sys_scope&&q.sourceModelPackage===source.sys_package&&
                q.sourceTransformerScope===transformer.sys_scope&&q.sourceTransformerPackage===transformer.sys_package&&
                q.sourceModelRevision===source.sys_mod_count&&q.sourceTransformerRevision===transformer.sys_mod_count,
                'ReviewedLongCopyIdentityOwnershipOrRevisionChanged');
            check(source.model_source==='customer'&&source.usage_mode==='none'&&!source.sys_policy&&
                !source.preceding_model_config&&!source.sys_overrides&&
                (source.sys_scope==='global'||validId(source.sys_scope))&&(source.sys_package==='global'||validId(source.sys_package))&&
                transformer.sys_scope==='global'&&transformer.sys_package==='global'&&!transformer.sys_policy,
                'ReviewedLongCopyOwnSourceRequired');
            check(q.requestHash===result.source.requestHash&&q.responseHash===result.source.responseHash&&
                P.expectedRequestHash===q.requestHash&&P.expectedResponseHash===q.responseHash&&
                q.requestCharacters===request.length&&q.requestUtf8Bytes===utf8Length(request)&&
                q.responseCharacters===response.length&&q.responseUtf8Bytes===utf8Length(response),
                'ReviewedLongCopyRawHashesOrLengthsChanged');
            check(request.length<=65536&&response.length<=65536&&utf8Length(request)<=65536&&utf8Length(response)<=65536,'ReviewedLongCopySourceBoundExceeded');
            // Explicit NEW-target derivation only: preserve bare-CR line terminators.
            copiedScripts.request_transformer=request.replace(/\r\n?/g,'\n');
            copiedScripts.response_transformer=response.replace(/\r\n?/g,'\n');
            reviewedScriptCopy=true;
        } else {
            check(P.reviewedLongCopy===null,'UnexpectedLongCopyManifestInExactMode');
            copiedScripts.request_transformer=request;copiedScripts.response_transformer=response;
        }
        var rq=scriptFacts(copiedScripts.request_transformer),rs=scriptFacts(copiedScripts.response_transformer);
        if(reviewedScriptCopy)check(rq.characters<=65536&&rs.characters<=65536&&rq.utf8Bytes<=65536&&rs.utf8Bytes<=65536,'ReviewedLongCopyDerivedBoundExceeded');
        result.copy={mode:P.scriptCopyMode,requestHash:rq.hash,responseHash:rs.hash,requestCharacters:rq.characters,responseCharacters:rs.characters,requestUtf8Bytes:rq.utf8Bytes,responseUtf8Bytes:rs.utf8Bytes};
        if(P.apply&&reviewedScriptCopy)check(P.expectedCopiedRequestHash===rq.hash&&P.expectedCopiedResponseHash===rs.hash,'ReviewedDerivedCopyHashesRequiredOrChanged');
    }
    function reviewedScannerException(field) {
        // Only the independently inspected deployed Halogen source contains these
        // words as native template data; a caller cannot approve arbitrary TODOs.
        // Revisions still match the fresh manifest/graph, rather than a stale
        // hard-coded metadata counter. The response gets no inherited exception.
        return field==='request_transformer'&&reviewedScriptCopy&&source.sys_id==='ff74fcef93a70350e7f2b9fa6aba10ea'&&
            transformer.sys_id==='bc126377936f8750e7f2b9fa6aba1012'&&
            result.source.requestHash==='99cb5d8733faca9955ec274f21dc4b5f46f0b2c4159cbb63b9c5954bf85c4e58';
    }
    function reviewedScriptField(r,f,v,type) {
        return reviewedScriptCopy&&type==='script'&&r.getTableName()===T&&
            (f==='request_transformer'||f==='response_transformer')&&v===copiedScripts[f]&&
            validId(targetId)&&targetId!==source.sys_id&&str(r.getValue('model'))===targetId&&
            str(r.getUniqueValue())!==transformer.sys_id&&v.length<=65536&&utf8Length(v)<=65536;
    }
    function gr(table) {
        check(own(schema, table), 'UnreviewedTable');
        var r = new GlideRecordSecure(table);
        check(r.isValid(), 'MissingTable:' + table);
        return r;
    }
    function value(r, field) {
        check(r.isValidField(field), 'MissingField:' + r.getTableName() + '.' + field);
        var e = r.getElement(field);
        check(
            e !== null && typeof e !== 'undefined' && e.canRead(),
            'FieldReadDenied:' + r.getTableName() + '.' + field
        );
        var v = str(r.getValue(field));
        return str(e.getED().getInternalType()) === 'boolean' && v !== ''
            ? yes(v)
                ? '1'
                : '0'
            : v;
    }
    function snapshot(r) {
        check(r.canRead(), 'RecordReadDenied:' + r.getTableName());
        var table = r.getTableName(),
            names = snapshotIdentity[table].concat(schema[table]),
            out = {},
            i;
        for (i = 0; i < names.length; i++) {
            out[names[i]] = value(r, names[i]);
        }
        return out;
    }
    function read(table, id) {
        var r = gr(table);
        return r.get(id) ? snapshot(r) : null;
    }
    function query(table, filters) {
        var r = gr(table),
            out = [],
            i;
        for (i = 0; i < filters.length; i++) {
            check(
                r.isValidField(filters[i][0]),
                'MissingQueryField:' + table + '.' + filters[i][0]
            );
            r.addQuery(filters[i][0], '=', filters[i][1]);
        }
        r.orderBy('sys_id');
        r.setLimit(501);
        r.query();
        while (r.next()) {
            out.push(snapshot(r));
            check(out.length <= 500, 'QueryLimitExceeded:' + table);
        }
        return out;
    }
    function one(rows, label) {
        check(rows.length === 1, 'ExpectedUnique:' + label + '; found=' + rows.length);
        return rows[0];
    }
    function watch(table, row) {
        check(row, 'DependencyMissing:' + table);
        guards.push({ table: table, id: row.sys_id, hash: hash(row) });
        return row;
    }
    function watchedQuery(table, filters) {
        var rows = query(table, filters);
        queryGuards.push({ table: table, filters: filters, hash: hash(rows) });
        return rows;
    }
    function fresh() {
        var i, g;
        check(str(gs.getCurrentApplicationId()) === 'global', 'GlobalApplicationContextChanged');
        if (restoring) {
            check(
                str(gs.getPreference('sys_update_set')) === P.updateSetId,
                'SelectedUpdateSetChanged'
            );
        }
        for (i = 0; i < guards.length; i++) {
            g = guards[i];
            check(
                hash(read(g.table, g.id)) === g.hash,
                'DependencyChanged:' + g.table + ':' + g.id
            );
        }
        for (i = 0; i < queryGuards.length; i++) {
            g = queryGuards[i];
            check(hash(query(g.table, g.filters)) === g.hash, 'RelationshipChanged:' + g.table);
        }
    }
    function checkDictionary(table, contract) {
        var names = keys(contract),
            i,
            f,
            c,
            d;
        for (i = 0; i < names.length; i++) {
            f = names[i];
            c = contract[f];
            d = watch(
                'sys_dictionary',
                one(
                    query('sys_dictionary', [
                        ['name', table],
                        ['element', f]
                    ]),
                    table + '.' + f
                )
            );
            check(
                d.internal_type === c[0] &&
                    Number(d.max_length) === c[1] &&
                    d.reference === (c[2] || '') &&
                    yes(d.mandatory) === (c[3] === true) &&
                    yes(d.read_only) === (c[5] === true),
                'UnsupportedDictionary:' + table + '.' + f
            );
            if (typeof c[4] !== 'undefined') {
                check(d.default_value === c[4], 'UnsupportedDefault:' + table + '.' + f);
            }
        }
        d = watch(
            'sys_dictionary',
            one(
                query('sys_dictionary', [
                    ['name', table],
                    ['element', '']
                ]),
                table + '.collection'
            )
        );
        check(
            d.internal_type === 'collection' &&
                /(?:^|,)update_synch=true(?:,|$)/.test(d.attributes),
            'NativeCaptureUnsupported:' + table
        );
    }
    function ownership(row, persisted) {
        check(
            row.sys_scope === 'global' &&
                (persisted
                    ? row.sys_package === 'global'
                    : !row.sys_package || row.sys_package === 'global') &&
                !row.sys_policy,
            'TargetOwnershipMismatch'
        );
    }
    function modelIdentity(row) {
        check(
            row.model_source === 'customer' &&
                row.usage_mode === 'none' &&
                row.model_type === 'LLM' &&
                !row.preceding_model_config &&
                !row.sys_overrides,
            'NewModelIdentityOrHistoryMismatch'
        );
    }
    function setValues(r, values) {
        var names = keys(values),
            i,
            f,
            e,
            type,
            limit;
        for (i = 0; i < names.length; i++) {
            f = names[i];
            check(
                own(r.getTableName() === M ? modelContract : transformerContract, f) &&
                    ['model_source', 'usage_mode'].indexOf(f) === -1,
                'UnreviewedWriteField'
            );
            e = r.getElement(f);
            check(
                e !== null && typeof e !== 'undefined' && e.canWrite(),
                'FieldWriteDenied:' + r.getTableName() + '.' + f
            );
            type = str(e.getED().getInternalType());
            limit = Number(e.getED().getLength());
            if (['boolean', 'integer', 'reference'].indexOf(type) === -1) {
                check(limit > 0 && (str(values[f]).length <= limit || reviewedScriptField(r,f,str(values[f]),type)), 'FieldLengthExceeded:' + f);
            }
            r.setValue(f, values[f]);
        }
    }
    function prototype(table, values) {
        var r = gr(table);
        r.newRecord();
        var before = snapshot(r);
        check(
            validId(before.sys_id) && !read(table, before.sys_id),
            'NewIdentityMissingOrCollision'
        );
        ownership(before, false);
        if (table === M) {
            modelIdentity(before);
            check(!before.lifecycle_state, 'UnsupportedLifecycleDefault');
        }
        check(r.canCreate(), 'RecordCreateDenied:' + table);
        setValues(r, values);
        return r;
    }
    function compare(table, id, values) {
        var row = read(table, id),
            r = gr(table),
            names = keys(values),
            i;
        check(row && r.get(id), 'TargetReadbackMissing:' + table);
        ownership(row, true);
        if (table === M) {
            modelIdentity(row);
        }
        for (i = 0; i < names.length; i++) {
            var f = names[i],
                expected = str(values[f]);
            if (str(r.getElement(f).getED().getInternalType()) === 'boolean') {
                expected = yes(expected) ? '1' : '0';
            }
            check(value(r, f) === expected, 'TargetCoercion:' + table + '.' + f);
        }
        return row;
    }
    function ids(rows) {
        var out = [],
            i;
        for (i = 0; i < rows.length; i++) {
            out.push(rows[i].sys_id);
        }
        return out;
    }
    function history(id, label) {
        var inventory = {
            stage: label,
            modelConfigId: id,
            versionMappingIds: ids(query(V, [['target_model_name', id]])),
            predecessorIds: ids(query(M, [['preceding_model_config', id]])),
            overrideIds: ids(query(M, [['sys_overrides', id]]))
        };
        result.inventories.push(inventory);
        check(
            !inventory.versionMappingIds.length &&
                !inventory.predecessorIds.length &&
                !inventory.overrideIds.length,
            'UnexpectedNativeHistoryRequiresReview'
        );
    }
    function targets() {
        var rows = query(M, [['model', P.targetModel]]),
            matches = [],
            i,
            m;
        for (i = 0; i < rows.length; i++) {
            m = read('sys_generative_ai_provider_mapping', rows[i].provider);
            check(m, 'PeerProviderMappingUnreadable');
            if (m.provider_implementation === mapping.provider_implementation) {
                matches.push(rows[i]);
            }
        }
        return matches;
    }
    function targetGraph(expectedModelId, expectedTransformerId, label) {
        var rows = targets();
        check(
            rows.length === (expectedModelId ? 1 : 0) &&
                (!expectedModelId || rows[0].sys_id === expectedModelId),
            'TargetDuplicateOrRace'
        );
        if (expectedModelId) {
            compare(M, expectedModelId, modelValues);
            history(expectedModelId, label);
            var transformers = query(T, [['model', expectedModelId]]);
            check(
                transformers.length === (expectedTransformerId ? 1 : 0) &&
                    (!expectedTransformerId || transformers[0].sys_id === expectedTransformerId),
                'TargetTransformerDuplicateOrRace'
            );
            if (expectedTransformerId) {
                compare(T, expectedTransformerId, transformerValues);
            }
        }
    }
    // Native transformer capture may carry its one exact ES metadata companion.
    // Both records retain direct-field grammar and independent complete equality.
    function safeMarkup(payload) {
        check(payload && payload.length<=524288 && utf8Length(payload)<=524288,
            'EmptyOrOversizedCapturePayload');
        var markup = payload
                .replace(/<!\[CDATA\[[\s\S]*?\]\]>/g, '')
                .replace(/<!--[\s\S]*?-->/g, ''),
            tokens = markup.match(/<[^>]+>/g) || [],
            i,
            actions;
        check(
            !/<!DOCTYPE|<!ENTITY|<\s*\/?\s*delete(?:_multiple)?\b/i.test(markup),
            'DestructiveOrUnsafeCaptureMarkup'
        );
        for (i = 0; i < tokens.length; i++) {
            actions = tokens[i].match(/\baction\s*=/gi) || [];
            if (actions.length) {
                check(
                    actions.length === 1 &&
                        (
                            tokens[i].match(
                                /\saction\s*=\s*(["'])INSERT_OR_UPDATE\1(?=\s|\/?>)/g
                            ) || []
                        ).length === 1,
                    'UnsafeCaptureAction'
                );
            }
        }
        return markup;
    }
    function verifyTransport(table, id, payload, row) {
        var markup = safeMarkup(payload),
            doc = new XMLDocument2();
        doc.parseXML(payload);
        var root = doc.getDocumentElement();
        check(root && str(root.getAttribute('table')) === table, 'CaptureRootMismatch');
        var tokens = markup.match(/<[^>]+>/g) || [],
            stack = [],
            rootSeen = false,
            records = {},
            currentRecord = '',
            i,
            token,
            m,
            closing,
            tag,
            selfClosing,
            depth;
        for (i = 0; i < tokens.length; i++) {
            token = tokens[i];
            if (/^<\?xml\s[^?]*\?>$/.test(token)) {
                continue;
            }
            m = /^<(\/?)([A-Za-z_][A-Za-z0-9_.:-]*)(?:\s[^<>]*?)?\s*(\/?)>$/.exec(token);
            check(m, 'InvalidCaptureMarkup');
            closing = m[1] === '/';
            tag = m[2];
            selfClosing = m[3] === '/';
            depth = stack.length;
            if (closing) {
                check(!selfClosing && stack.pop() === tag, 'InvalidCaptureNesting');
                if(stack.length===1)currentRecord='';
                continue;
            }
            if (depth === 0) {
                check(!rootSeen && tag === 'record_update', 'ExtraCaptureRoot');
                rootSeen = true;
            } else if (depth === 1) {
                check(
                    !own(records,tag) &&
                        (tag === table || (table === T && tag === E)) &&
                        /\saction\s*=\s*(["'])INSERT_OR_UPDATE\1(?=\s|\/?>)/.test(token),
                    'ExtraOrInvalidCaptureRecord'
                );
                records[tag]={};currentRecord=tag;
            } else if (depth === 2) {
                check(currentRecord && !own(records[currentRecord],tag) && !/\baction\s*=/.test(token), 'InvalidCaptureField');
                if(currentRecord===E)check(snapshotIdentity[E].concat(schema[E]).indexOf(tag)!==-1,'UnreviewedCompanionField');
                records[currentRecord][tag] = true;
            } else {
                fail('NestedCaptureField');
            }
            if (!selfClosing) {
                stack.push(tag);
            }
        }
        check(
            rootSeen &&
                own(records,table) &&
                !stack.length &&
                str(doc.getNodeText('//' + table + '/sys_id')) === id,
            'CaptureIdentityMismatch'
        );
        var r = gr(table),
            names = keys(row),
            f,
            actual,
            expected;
        check(r.get(id), 'CaptureSourceMissing');
        for (i = 0; i < names.length; i++) {
            f = names[i];
            check(records[table][f], 'CapturedFieldMissing:' + f);
            actual = str(doc.getNodeText('//' + table + '/' + f));
            expected = row[f];
            if (str(r.getElement(f).getED().getInternalType()) === 'boolean' && expected !== '') {
                check(['true', 'false', '1', '0'].indexOf(actual) !== -1, 'CapturedBooleanInvalid');
                actual = yes(actual) ? '1' : '0';
            }
            check(actual === expected, 'CapturedFieldMismatch:' + f);
        }
        if(own(records,E)) {
            var companions=query(E,[['id',id],['table',table]]);
            var companion=one(companions,'current native ES companion');
            check(validId(companion.sys_id)&&companion.id===id&&companion.table===table,'CompanionParentMismatch');
            var er=gr(E);check(er.get(companion.sys_id),'CompanionReadbackMissing');
            names=keys(companion);
            for(i=0;i<names.length;i++) {
                f=names[i];check(records[E][f],'CapturedCompanionFieldMissing:'+f);
                actual=str(doc.getNodeText('//'+E+'/'+f));expected=companion[f];
                if(str(er.getElement(f).getED().getInternalType())==='boolean'&&expected!=='') {
                    check(['true','false','1','0'].indexOf(actual)!==-1,'CapturedCompanionBooleanInvalid');
                    actual=yes(actual)?'1':'0';
                }
                check(actual===expected,'CapturedCompanionFieldMismatch:'+f);
            }
        }
    }
    function captured(table, id, row, setId) {
        var filters = [['name', table + '_' + id]],
            rows,
            valid = [],
            i;
        if (setId) {
            filters.push(['update_set', setId]);
        }
        rows = query('sys_update_xml', filters);
        for (i = 0; i < rows.length; i++) {
            check(
                rows[i].action === 'INSERT_OR_UPDATE' && rows[i].application === 'global',
                'UnsafeCaptureHeader'
            );
            verifyTransport(table, id, rows[i].payload, row);
            valid.push(rows[i]);
        }
        check(valid.length > 0 && (!setId || valid.length === 1), 'CaptureMissingOrAmbiguous');
        return valid[0];
    }
    function insert(r, values) {
        fresh();
        var table = r.getTableName(),
            id = str(r.getUniqueValue());
        check(table===M||table===T,'UnreviewedInsertTable');
        check(!read(table, id), 'NewIdentityCollision');
        ownership(snapshot(r), false);
        check(r.canCreate(), 'RecordCreateDenied:' + table);
        setValues(r, values);
        stage = 'insert:' + table;
        result.writeAttempts.push({ table: table, id: id, operation: 'insert' });
        check(str(r.insert()) === id, 'NativeInsertOutcomeUncertain:' + table);
        result.writes.push({ table: table, id: id, operation: 'insert' });
        fresh();
        var row = compare(table, id, values);
        targetGraph(targetId, table === T ? transformerId : '', 'after:' + table);
        stage = 'capture:' + table;
        var saved = gr(table);
        check(saved.get(id), 'CaptureTargetMissing');
        new GlideUpdateManager2().saveRecord(saved);
        fresh();
        row = compare(table, id, values);
        var cu = captured(table, id, row, P.updateSetId);
        result.captures.push({ table: table, id: id, customerUpdateId: cu.sys_id });
    }
    function handoff(id, ready) {
        result.handoff = {
            targetModel: P.targetModel,
            modelConfigId: id,
            providerMappingId: P.providerMappingId,
            providerId: P.providerId,
            capabilityIds: P.capabilityIds.slice(0),
            readyForAdd: P.apply === true && ready === true
        };
    }
    function verifyFinalCaptures() {
        // Verify both current target snapshots against the captured transport.
        // Never silently repair a stale earlier capture after another insert.
        var currentModel = compare(M, targetId, modelValues);
        var currentTransformer = compare(T, transformerId, transformerValues);
        captured(M, targetId, currentModel, P.updateSetId);
        captured(T, transformerId, currentTransformer, P.updateSetId);
    }
    function observeAttempts() {
        // A thrown/empty insert result can still mean a committed native row.
        // Observe only; never compensate, retry or infer success from existence.
        result.observedTargets = [];
        var i, attempt, row, observation;
        for (i = 0; i < result.writeAttempts.length; i++) {
            attempt = result.writeAttempts[i];
            row = read(attempt.table, attempt.id);
            observation = { table: attempt.table, id: attempt.id, exists: row !== null };
            if (row) {
                observation.scope = row.sys_scope;
                observation.packageId = row.sys_package;
                observation.revision = row.sys_mod_count;
                if (attempt.table === M) {
                    observation.modelSource = row.model_source;
                    observation.usageMode = row.usage_mode;
                    observation.precedingModelConfigId = row.preceding_model_config;
                    observation.overridesId = row.sys_overrides;
                } else {
                    observation.modelConfigId = row.model;
                    observation.requestHash = hash(row.request_transformer);
                    observation.responseHash = hash(row.response_transformer);
                }
            }
            result.observedTargets.push(observation);
        }
        // Inventory even when no record is readable: children can outlive an
        // uncertain parent insert. IDs remain in the report if validation fails.
        result.observedTargetModelIds = ids(targets());
        result.observedTransformerIds = ids(query(T, [['model', targetId]]));
        history(targetId, 'final observed');
    }
    try {
        check(P.apply === true || P.apply === false, 'BooleanApplyRequired');
        check(P.scriptCopyMode==='exact'||P.scriptCopyMode==='reviewed-lf-copy-v1','UnsupportedScriptCopyMode');
        check(
            typeof P.targetModel === 'string' &&
                P.targetModel.length > 0 &&
                P.targetModel.length <= 100 &&
                P.targetModel.replace(/^\s+|\s+$/g, '') === P.targetModel,
            'ExactTargetModelRequired'
        );
        check(
            typeof P.displayName === 'string' &&
                P.displayName.length > 0 &&
                P.displayName.length <= 100,
            'DisplayNameRequired'
        );
        var selections = [
                'sourceModelConfigId',
                'sourceTransformerId',
                'providerMappingId',
                'providerId',
                'connectionAliasId'
            ],
            i,
            unique = {};
        for (i = 0; i < selections.length; i++) {
            check(validId(P[selections[i]]), 'ExplicitSelectionRequired:' + selections[i]);
        }
        check(
            Object.prototype.toString.call(P.capabilityIds) === '[object Array]' &&
                P.capabilityIds.length > 0 &&
                P.capabilityIds.length <= 100,
            'ExplicitCapabilitySelectionRequired'
        );
        for (i = 0; i < P.capabilityIds.length; i++) {
            check(
                validId(P.capabilityIds[i]) && !unique[P.capabilityIds[i]],
                'InvalidOrDuplicateCapabilityId'
            );
            unique[P.capabilityIds[i]] = true;
            watch(
                'sys_one_extend_capability',
                read('sys_one_extend_capability', P.capabilityIds[i])
            );
        }
        check(
            typeof P.maxTokens === 'number' &&
                P.maxTokens > 0 &&
                P.maxTokens <= 2147483647 &&
                Math.floor(P.maxTokens) === P.maxTokens,
            'ExplicitMaxTokensRequired'
        );
        check(
            P.outputTokenSize === null ||
                (typeof P.outputTokenSize === 'number' &&
                    P.outputTokenSize > 0 &&
                    P.outputTokenSize <= P.maxTokens &&
                    Math.floor(P.outputTokenSize) === P.outputTokenSize),
            'InvalidOutputTokenSize'
        );
        var booleans = ['active', 'thinkingEnabled', 'enableFunctionCalling', 'loggingEnabled'];
        for (i = 0; i < booleans.length; i++) {
            check(typeof P[booleans[i]] === 'boolean', 'BooleanContractRequired:' + booleans[i]);
        }
        check(
            typeof P.logSamplingPercentage === 'number' &&
                P.logSamplingPercentage > 0 &&
                P.logSamplingPercentage <= 100 &&
                Math.floor(P.logSamplingPercentage) === P.logSamplingPercentage,
            'LogSamplingMustBeInNativeRange'
        );
        checkDictionary(M, modelContract);
        checkDictionary(T, transformerContract);
        source = watch(M, read(M, P.sourceModelConfigId));
        check(
            yes(source.active) &&
                source.lifecycle_state === 'active' &&
                source.model_type === 'LLM' &&
                source.usage_mode !== 'restricted',
            'SourceModelNotEligible'
        );
        check(
            source.provider === P.providerMappingId && source.connection === P.connectionAliasId,
            'SourceSelectionMismatch'
        );
        mapping = watch(
            'sys_generative_ai_provider_mapping',
            read('sys_generative_ai_provider_mapping', P.providerMappingId)
        );
        check(
            yes(mapping.active) &&
                mapping.provider === 'Custom LLM' &&
                mapping.provider_api === 'custom_api' &&
                mapping.provider_implementation_document === 'sys_hub_flow' &&
                mapping.gen_ai_provider === P.providerId,
            'UnsupportedCustomProviderMapping'
        );
        provider = watch('sys_gen_ai_provider', read('sys_gen_ai_provider', P.providerId));
        check(provider.gen_ai_provider === 'Custom LLM Provider', 'UnexpectedProviderIdentity');
        watch('sys_hub_flow', read('sys_hub_flow', mapping.provider_implementation));
        check(validId(mapping.connection), 'MappingAliasRequired');
        watch('sys_alias', read('sys_alias', mapping.connection));
        watch('sys_alias', read('sys_alias', P.connectionAliasId));
        transformer = one(watchedQuery(T, [['model', source.sys_id]]), 'source transformer');
        check(
            transformer.sys_id === P.sourceTransformerId && transformer.model === source.sys_id,
            'SourceTransformerIdentityMismatch'
        );
        var sourceCompanions=watchedQuery(E,[['id',transformer.sys_id],['table',T]]);
        check(sourceCompanions.length<=1,'SourceCompanionAmbiguous');
        if(sourceCompanions.length)check(validId(sourceCompanions[0].sys_id)&&sourceCompanions[0].id===transformer.sys_id&&sourceCompanions[0].table===T,'SourceCompanionIdentityMismatch');
        // Raw scalar facts are visible even when a source/policy is unreviewed.
        result.source = {
            modelConfigId: source.sys_id, transformerId: transformer.sys_id,
            modelScope:source.sys_scope,modelPackage:source.sys_package,modelRevision:source.sys_mod_count,
            transformerScope:transformer.sys_scope,transformerPackage:transformer.sys_package,transformerRevision:transformer.sys_mod_count,
            providerMappingId:mapping.sys_id,providerId:provider.sys_id,implementationId:mapping.provider_implementation,
            mappingAliasId:mapping.connection,modelAliasId:source.connection,
            requestHash:hash(transformer.request_transformer),responseHash:hash(transformer.response_transformer),
            requestCharacters:transformer.request_transformer.length,responseCharacters:transformer.response_transformer.length,
            requestUtf8Bytes:utf8Length(transformer.request_transformer),responseUtf8Bytes:utf8Length(transformer.response_transformer),
            graphHash:hash({records:guards,relationships:queryGuards})
        };
        prepareScriptCopy();
        var scripts = ['request_transformer', 'response_transformer'];
        for (i = 0; i < scripts.length; i++) {
            var content = transformer[scripts[i]],
                d = one(
                    query('sys_dictionary', [
                        ['name', T],
                        ['element', scripts[i]]
                    ]),
                    'transformer dictionary'
                );
            check(
                content &&
                    content.replace(/\s/g, '').length > 0 &&
                    content.length <= (reviewedScriptCopy?65536:4000) &&
                    content !== d.default_value &&
                    (!/write code here|\bTODO\b|\bPLACEHOLDER\b/i.test(content)||reviewedScannerException(scripts[i])),
                'ReviewedUsableTransformerRequired:' + scripts[i]
            );
        }
        if (P.apply) {
            check(
                P.expectedSourceGraphHash === result.source.graphHash &&
                    P.expectedRequestHash === result.source.requestHash &&
                    P.expectedResponseHash === result.source.responseHash,
                'ReviewedSourceHashesRequiredOrChanged'
            );
        }
        modelValues = {
            model: P.targetModel,
            model_display_name: P.displayName,
            provider: mapping.sys_id,
            connection: source.connection,
            active: P.active ? '1' : '0',
            lifecycle_state: P.active ? 'active' : '',
            model_type: 'LLM',
            max_tokens: str(P.maxTokens),
            thinking_enabled: P.thinkingEnabled ? '1' : '0',
            enable_function_calling: P.enableFunctionCalling ? '1' : '0',
            logging_enabled: P.loggingEnabled ? '1' : '0',
            log_sampling_percentage: str(P.logSamplingPercentage),
            availability_at_instance: '1',
            external: '1',
            preceding_model_config: '',
            sys_overrides: ''
        };
        if (P.outputTokenSize !== null) {
            modelValues.output_token_size = str(P.outputTokenSize);
        }
        if (P.active) {
            one(
                watchedQuery('sys_choice', [
                    ['name', M],
                    ['element', 'lifecycle_state'],
                    ['value', 'active'],
                    ['inactive', '0']
                ]),
                'native active lifecycle'
            );
        }
        result.plan = {
            model: modelValues,
            transformer: {
                requestHash: result.copy.requestHash,
                responseHash: result.copy.responseHash,
                sourceRequestHash:result.source.requestHash,sourceResponseHash:result.source.responseHash,
                copyMode:result.copy.mode,
                newOwnTransformer: true
            },
            requiredScope: 'global',
            defaultsToVerify: { model_source: 'customer', usage_mode: 'none' },
            prerequisites: [
                'Actual Global application picker',
                'Secure table create and every allowlisted field write right',
                'Apply: existing Global root In-progress update set and exact reviewed source hashes'
            ]
        };
        var existing = targets();
        check(existing.length <= 1, 'AmbiguousNativeModelStringWithinImplementation');
        if (existing.length) {
            targetId = existing[0].sys_id;
            check(targetId !== source.sys_id, 'SourceCannotBeRegistrationTarget');
            var ownTransformer = one(
                query(T, [['model', targetId]]),
                'existing target transformer'
            );
            transformerId = ownTransformer.sys_id;
            check(transformerId !== transformer.sys_id, 'ExistingTransformerMustBeOwn');
            transformerValues = {
                model: targetId,
                request_transformer: copiedScripts.request_transformer,
                response_transformer: copiedScripts.response_transformer
            };
            targetGraph(targetId, transformerId, 'existing');
            captured(M, targetId, compare(M, targetId, modelValues));
            captured(T, transformerId, compare(T, transformerId, transformerValues));
            result.status = 'NoOp';
            handoff(targetId, P.active);
        } else {
            check(
                str(gs.getCurrentApplicationId()) === 'global',
                'SelectActualGlobalApplicationBeforePreviewOrApply'
            );
            modelPrototype = prototype(M, modelValues);
            targetId = str(modelPrototype.getUniqueValue());
            transformerValues = {
                model: targetId,
                request_transformer: copiedScripts.request_transformer,
                response_transformer: copiedScripts.response_transformer
            };
            transformerPrototype = prototype(T, transformerValues);
            transformerId = str(transformerPrototype.getUniqueValue());
            history(targetId, 'before');
            result.plan.modelConfigId = targetId;
            result.plan.transformer.id = transformerId;
            result.plan.transformer.model = targetId;
            handoff(targetId, false);
            if (!P.apply) {
                result.status = 'Preview';
            } else {
                check(validId(P.updateSetId), 'ReviewedUpdateSetRequired');
                var set = watch('sys_update_set', read('sys_update_set', P.updateSetId));
                check(
                    set.application === 'global' && set.state === 'in progress' && !set.parent,
                    'UpdateSetMustBeGlobalRootInProgress'
                );
                var existingCaptures = query('sys_update_xml', [['update_set', P.updateSetId]]);
                for (i = 0; i < existingCaptures.length; i++) {
                    check(
                        existingCaptures[i].action === 'INSERT_OR_UPDATE' &&
                            existingCaptures[i].application === 'global',
                        'UnsafeExistingUpdateSetEntry'
                    );
                    safeMarkup(existingCaptures[i].payload);
                }
                previousSet = str(gs.getPreference('sys_update_set'));
                check(validId(previousSet), 'PreviousUpdateSetMustBeRestorable');
                updateSets = new GlideUpdateSet();
                restoring = true;
                updateSets.set(P.updateSetId);
                fresh();
                targetGraph('', '', 'before insert');
                insert(modelPrototype, modelValues);
                fresh();
                targetGraph(targetId, '', 'before transformer');
                insert(transformerPrototype, transformerValues);
                fresh();
                targetGraph(targetId, transformerId, 'complete');
                registrationComplete = true;
            }
        }
    } catch (e) {
        result.status = result.writeAttempts.length ? 'Partial' : 'Refused';
        result.issues.push(
            e.registrarIssue ? str(e.message) : 'NativeExceptionRequiresReview:' + stage
        );
    } finally {
        if (result.writeAttempts.length) {
            try {
                observeAttempts();
                fresh();
                if (registrationComplete) {
                    targetGraph(targetId, transformerId, 'final verified');
                    verifyFinalCaptures();
                    result.status = 'Applied';
                    handoff(targetId, P.active);
                }
            } catch (observationError) {
                result.status = 'Partial';
                result.issues.push(
                    observationError.registrarIssue
                        ? str(observationError.message)
                        : 'FinalObservationUncertain'
                );
            }
        }
        if (restoring) {
            try {
                updateSets.set(previousSet);
                check(
                    str(gs.getPreference('sys_update_set')) === previousSet,
                    'PreviousUpdateSetRestoreFailed'
                );
            } catch (restoreError) {
                result.status = 'Partial';
                result.issues.push('PreviousUpdateSetRestoreFailed');
            }
        }
        if (result.status !== 'Applied' && result.status !== 'NoOp') {
            result.handoff.readyForAdd = false;
        }
    }
    // No transformer bodies, credential/endpoint contents or native exception text.
    gs.info('[CAPABILITY_MODEL_REGISTER] ' + JSON.stringify(result));
})();
