'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const file = path.join(__dirname, 'RegisterCapabilityModel.background.js');
const id = (n) => n.toString(16).padStart(32, '0');
const M = 'sys_generative_ai_model_config',
    T = 'sys_generative_ai_custom_llm_transformer',
    V = 'sys_gen_ai_model_version_mapping';
const SOURCE = id(1),
    TRANS = id(2),
    MAP = id(3),
    PROVIDER = id(4),
    FLOW = id(5),
    ALIAS = id(6),
    CAP = id(7),
    SET = id(8),
    OLD = id(9);
const request =
    '(function(inputs) { return {body: {model: inputs.prompt_data.model, prompt: inputs.prompt_data.prompt}, headers: {}}; })(inputs);';
const response = '(function(inputs) { return [JSON.parse(inputs.response_body).text]; })(inputs);';
const hash = (v) => crypto.createHash('sha256').update(v).digest('hex');
const modelFields = {
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
const transformFields = {
    model: ['reference', 32, M, true],
    request_transformer: ['script', 4000, '', false, 'write code here'],
    response_transformer: ['script', 4000, '', false, 'write code here']
};
const schemas = {
    [M]: Object.keys(modelFields),
    [T]: Object.keys(transformFields),
    [V]: ['target_model_name'],
    sys_generative_ai_provider_mapping: [
        'provider',
        'provider_api',
        'provider_implementation',
        'provider_implementation_document',
        'gen_ai_provider',
        'connection',
        'active'
    ],
    sys_gen_ai_provider: ['gen_ai_provider'],
    sys_hub_flow: ['name', 'status'],
    sys_alias: ['name', 'type'],
    sys_one_extend_capability: ['name', 'active'],
    sys_dictionary: [
        'name',
        'element',
        'internal_type',
        'reference',
        'mandatory',
        'read_only',
        'max_length',
        'default_value',
        'attributes'
    ],
    sys_choice: ['name', 'element', 'value', 'inactive'],
    sys_update_set: ['application', 'state', 'parent', 'name'],
    sys_update_xml: ['name', 'update_set', 'action', 'payload', 'application']
};
function fixture(options = {}) {
    let next = 100,
        currentSet = OLD,
        selections = 0;
    const db = {},
        writes = [],
        captures = [];
    for (const table of Object.keys(schemas)) db[table] = [];
    function row(table, values) {
        const r = {
            sys_id: id(next++),
            sys_mod_count: '0',
            ...([M, T].includes(table)
                ? { sys_scope: 'global', sys_package: 'global', sys_policy: '' }
                : {}),
            ...values
        };
        db[table].push(r);
        return r;
    }
    for (const [table, fields] of [
        [M, modelFields],
        [T, transformFields]
    ]) {
        for (const [
            element,
            [type, length, reference = '', mandatory = false, def = '', readonly = false]
        ] of Object.entries(fields))
            row('sys_dictionary', {
                name: table,
                element,
                internal_type: type,
                max_length: String(length),
                reference,
                mandatory: String(mandatory),
                default_value: def,
                read_only: String(readonly),
                attributes: ''
            });
        row('sys_dictionary', {
            name: table,
            element: '',
            internal_type: 'collection',
            attributes: 'update_synch=true'
        });
    }
    row('sys_choice', { name: M, element: 'lifecycle_state', value: 'active', inactive: '0' });
    row(M, {
        sys_id: SOURCE,
        model: 'source-model',
        provider: MAP,
        connection: ALIAS,
        active: '1',
        lifecycle_state: 'active',
        model_type: 'LLM',
        model_source: 'customer',
        usage_mode: 'none',
        preceding_model_config: '',
        sys_overrides: ''
    });
    row(T, {
        sys_id: TRANS,
        model: SOURCE,
        request_transformer: request,
        response_transformer: response
    });
    row('sys_generative_ai_provider_mapping', {
        sys_id: MAP,
        provider: 'Custom LLM',
        provider_api: 'custom_api',
        provider_implementation: FLOW,
        provider_implementation_document: 'sys_hub_flow',
        gen_ai_provider: PROVIDER,
        connection: ALIAS,
        active: '1'
    });
    row('sys_gen_ai_provider', { sys_id: PROVIDER, gen_ai_provider: 'Custom LLM Provider' });
    row('sys_hub_flow', { sys_id: FLOW, name: 'Custom LLM', status: 'published' });
    row('sys_alias', { sys_id: ALIAS, name: 'Selected alias', type: 'connection' });
    row('sys_one_extend_capability', { sys_id: CAP, name: 'Summary', active: '1' });
    row('sys_update_set', {
        sys_id: SET,
        application: 'global',
        state: 'in progress',
        parent: '',
        name: 'Registration'
    });
    function payload(g) {
        let values = { ...g.record };
        if (options.badCapturedValue) values.model = 'wrong';
        if (options.badCaptureScope) values.sys_scope = id(999);
        if (options.omitCapturedDefault) delete values.model_source;
        const enc = (v) =>
            String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return (
            '<record_update table="' +
            g.table +
            '"><' +
            g.table +
            ' action="INSERT_OR_UPDATE">' +
            Object.entries(values)
                .map(([k, v]) => '<' + k + '>' + enc(v) + '</' + k + '>')
                .join('') +
            '</' +
            g.table +
            '>' +
            (options.extraCaptureRecord ? '<other action="INSERT_OR_UPDATE"/>' : '') +
            (options.deleteCapture ? '<delete action="DELETE"/>' : '') +
            '</record_update>'
        );
    }
    function GR(table) {
        this.table = table;
        this.record = {};
        this.filters = [];
    }
    GR.prototype.isValid = function () {
        return !!schemas[this.table];
    };
    GR.prototype.getTableName = function () {
        return this.table;
    };
    GR.prototype.getUniqueValue = function () {
        return this.record.sys_id;
    };
    GR.prototype.isValidField = function (f) {
        if (options.missingOwnedField === f && [M, T].includes(this.table)) return false;
        return (
            ['sys_id', 'sys_mod_count'].includes(f) ||
            ([M, T].includes(this.table) &&
                ['sys_scope', 'sys_package', 'sys_policy'].includes(f)) ||
            schemas[this.table]?.includes(f)
        );
    };
    GR.prototype.getValue = function (f) {
        return this.record[f] ?? null;
    };
    GR.prototype.getElement = function (f) {
        if (!this.isValidField(f)) return null;
        const def = (this.table === M ? modelFields : this.table === T ? transformFields : {})[
            f
        ] || ['string', 100000];
        return {
            canRead: () => options.unreadable !== f,
            canWrite: () =>
                ![
                    'sys_scope',
                    'sys_package',
                    'sys_policy',
                    'sys_mod_count',
                    'model_source',
                    'usage_mode'
                ].includes(f) && options.deniedField !== f,
            getED: () => ({ getInternalType: () => def[0], getLength: () => def[1] })
        };
    };
    GR.prototype.canRead = function () {
        return true;
    };
    GR.prototype.canCreate = function () {
        return options.denyCreate !== this.table;
    };
    GR.prototype.get = function (value) {
        const r = db[this.table].find((r) => r.sys_id === value);
        if (!r) return false;
        this.record = structuredClone(r);
        return true;
    };
    GR.prototype.addQuery = function (f, op, v) {
        if (v === undefined) {
            v = op;
            op = '=';
        }
        this.filters.push([f, op, String(v)]);
    };
    GR.prototype.orderBy = function () {};
    GR.prototype.setLimit = function (n) {
        this.limit = n;
    };
    GR.prototype.query = function () {
        if (
            options.lateCaptureDriftTable &&
            captures.length === 2 &&
            this.table === M &&
            this.filters.some(([f]) => f === 'model')
        ) {
            const changed = db.sys_update_xml.find((r) =>
                r.name.startsWith(options.lateCaptureDriftTable + '_')
            );
            changed.payload = changed.payload.replace(
                '<sys_mod_count>0</sys_mod_count>',
                '<sys_mod_count>1</sys_mod_count>'
            );
            options.lateCaptureDriftTable = null;
        }
        this.rows = db[this.table]
            .filter((r) =>
                this.filters.every(([f, op, v]) =>
                    op === '='
                        ? String(r[f] ?? '') === v
                        : op === 'IN'
                          ? v.split(',').includes(String(r[f]))
                          : false
                )
            )
            .slice(0, this.limit);
        this.index = -1;
    };
    GR.prototype.next = function () {
        if (++this.index >= this.rows.length) return false;
        this.record = structuredClone(this.rows[this.index]);
        return true;
    };
    GR.prototype.newRecord = function () {
        this.record = {
            sys_id: id(next++),
            sys_scope: options.application || 'global',
            sys_package: options.prototypePackage || 'global',
            sys_policy: '',
            sys_mod_count: '0'
        };
        for (const [f, d] of Object.entries(this.table === M ? modelFields : transformFields))
            this.record[f] = d[4] || '';
        if (this.table === M && options.badDefault) this.record.model_source = 'vendor';
    };
    GR.prototype.setValue = function (f, v) {
        assert.ok(this.getElement(f)?.canWrite(), 'forbidden direct field ' + f);
        this.record[f] = String(v);
    };
    GR.prototype.insert = function () {
        if (options.failInsert === this.table) return '';
        const value = { ...this.record };
        if (options.truncate && this.table === T)
            value.request_transformer = value.request_transformer.slice(0, -1);
        if (options.wrongModel && this.table === T) value.model = SOURCE;
        if (options.wrongOwner) value.sys_scope = id(999);
        const r = row(this.table, value);
        writes.push({ table: this.table, row: structuredClone(r) });
        if (options.nativeHistory && this.table === M) row(V, { target_model_name: r.sys_id });
        if (options.uncertainInsert === this.table) throw Error('insert outcome unavailable');
        if (options.nativePredecessor && this.table === M)
            row(M, {
                model: 'native-child',
                provider: MAP,
                preceding_model_config: r.sys_id,
                sys_overrides: ''
            });
        if (options.race && this.table === M) row(M, { ...r, sys_id: id(next++) });
        if (options.raceTransformer && this.table === T) row(T, { ...r, sys_id: id(next++) });
        if (options.driftAfterInsert) db[T][0].sys_mod_count = '9';
        if (options.targetModelRevisionDrift && this.table === T)
            db[M].find((r) => r.model === 'new-model').sys_mod_count = '1';
        return r.sys_id;
    };
    GR.prototype.update =
        GR.prototype.deleteRecord =
        GR.prototype.setWorkflow =
            function () {
                throw Error('unauthorized mutation');
            };
    function XML() {
        this.parseXML = (p) => (this.p = p);
        this.getDocumentElement = () => ({
            getAttribute: (n) =>
                (new RegExp('<record_update ' + n + '="([^"]+)"').exec(this.p) || [])[1]
        });
        this.getNodeText = (x) => {
            const f = x.split('/').pop(),
                m = new RegExp('<' + f + '>([\\s\\S]*?)</' + f + '>').exec(this.p);
            return m ? m[1].replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&') : '';
        };
    }
    const params = {
        targetModel: 'new-model',
        displayName: 'New model',
        sourceModelConfigId: SOURCE,
        sourceTransformerId: TRANS,
        providerMappingId: MAP,
        providerId: PROVIDER,
        connectionAliasId: ALIAS,
        capabilityIds: [CAP],
        maxTokens: 8192,
        updateSetId: SET,
        ...options.params
    };
    function run(overrides = {}) {
        // Every run, including failures, protects the original model/provider graph.
        // Only the explicit platform-source-drift fixtures may change the source row.
        const sourceIds = [
            [M, SOURCE],
            [T, TRANS],
            ['sys_generative_ai_provider_mapping', MAP],
            ['sys_gen_ai_provider', PROVIDER],
            ['sys_hub_flow', FLOW],
            ['sys_alias', ALIAS],
            ['sys_one_extend_capability', CAP]
        ];
        const before = sourceIds.map(([t, k]) =>
            structuredClone(db[t].find((r) => r.sys_id === k))
        );
        let result;
        const context = {
            CapabilityModelRegisterParameters: { ...params, ...overrides },
            GlideRecordSecure: GR,
            GlideDigest: function () {
                this.getSHA256Hex = hash;
            },
            XMLDocument2: XML,
            GlideUpdateSet: function () {
                this.set = (v) => {
                    selections++;
                    if (options.restoreFailure && v === OLD) throw Error('restore failed');
                    currentSet = v;
                    if (v === SET && options.driftOnSet) db[T][0].sys_mod_count = '8';
                    if (v === SET && options.headerDrift) db.sys_update_set[0].state = 'complete';
                };
            },
            GlideUpdateManager2: function () {
                this.saveRecord = (g) => {
                    captures.push(g.record.sys_id);
                    if (options.captureFailure) throw Error('capture failed');
                    row('sys_update_xml', {
                        name: g.table + '_' + g.record.sys_id,
                        update_set: currentSet,
                        action: 'INSERT_OR_UPDATE',
                        application: options.captureApplication ? id(999) : 'global',
                        payload: payload(g)
                    });
                };
            },
            gs: {
                getCurrentApplicationId: () => options.application || 'global',
                getPreference: () => currentSet,
                info: (s) => {
                    if (s.startsWith('[CAPABILITY_MODEL_REGISTER] '))
                        result = JSON.parse(s.slice(28));
                }
            }
        };
        vm.runInNewContext(fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : '', context);
        sourceIds.forEach(([t, k], i) => {
            if (t !== T || (!options.driftOnSet && !options.driftAfterInsert))
                assert.deepEqual(
                    db[t].find((r) => r.sys_id === k),
                    before[i],
                    'source graph changed: ' + t
                );
        });
        return result;
    }
    function apply(extra = {}) {
        const p = run();
        return run({
            apply: true,
            expectedSourceGraphHash: p?.source?.graphHash,
            expectedRequestHash: hash(request),
            expectedResponseHash: hash(response),
            ...extra
        });
    }
    return {
        db,
        row,
        writes,
        captures,
        run,
        apply,
        current: () => currentSet,
        selections: () => selections
    };
}
test('default preview checks the exact graph and prototypes without writes or update-set selection', () => {
    const f = fixture(),
        before = structuredClone(f.db),
        r = f.run();
    assert.equal(r?.status, 'Preview');
    assert.equal(f.writes.length, 0);
    assert.equal(f.captures.length, 0);
    assert.equal(f.selections(), 0);
    assert.deepEqual(f.db, before);
    assert.equal(r.handoff.readyForAdd, false);
    assert.equal(r.plan.model.active, '0');
    assert.equal(r.source.requestHash, hash(request));
    assert.ok(!JSON.stringify(r).includes(request));
});
test('secure apply creates exactly its model and own transformer, preserves inactive defaults and source graph', () => {
    const f = fixture(),
        before = structuredClone(f.db),
        r = f.apply();
    assert.equal(r?.status, 'Applied');
    assert.equal(f.writes.length, 2);
    assert.equal(f.captures.length, 2);
    assert.equal(f.current(), OLD);
    assert.deepEqual(f.db[M][0], before[M][0]);
    assert.deepEqual(f.db[T][0], before[T][0]);
    const target = f.db[M][1],
        adapter = f.db[T][1];
    assert.equal(target.active, '0');
    assert.equal(target.lifecycle_state, '');
    assert.equal(target.model_source, 'customer');
    assert.equal(target.usage_mode, 'none');
    assert.equal(target.preceding_model_config, '');
    assert.equal(target.sys_overrides, '');
    assert.equal(adapter.model, target.sys_id);
    assert.equal(adapter.request_transformer, request);
    assert.equal(adapter.response_transformer, response);
    assert.equal(f.db[V].length, 0);
    assert.equal(r.handoff.modelConfigId, target.sys_id);
    assert.equal(r.handoff.readyForAdd, false);
});
test('an exact repeated registration is NoOp with checked handoff and no second insert', () => {
    const f = fixture();
    assert.equal(f.apply()?.status, 'Applied');
    const r = f.apply();
    assert.equal(r?.status, 'NoOp');
    assert.equal(f.writes.length, 2);
    assert.equal(f.captures.length, 2);
});
test('explicit availability creates active lifecycle only and a ready Add handoff', () => {
    const f = fixture({ params: { active: true } }),
        r = f.apply();
    assert.equal(r?.status, 'Applied');
    assert.equal(f.db[M][1].lifecycle_state, 'active');
    assert.equal(r.handoff.readyForAdd, true);
    assert.deepEqual(r.handoff.capabilityIds, [CAP]);
});
for (const [label, options] of Object.entries({
    application: { application: id(900) },
    scope: { prototypePackage: id(900) },
    readonlyDefault: { badDefault: true },
    create: { denyCreate: M },
    transformCreate: { denyCreate: T },
    field: { deniedField: 'request_transformer' },
    unreadable: { unreadable: 'model_source' },
    emptySelection: { params: { capabilityIds: [] } },
    missingMaxTokens: { params: { maxTokens: null } },
    logging: { params: { logSamplingPercentage: 0 } },
    wrongAlias: { params: { connectionAliasId: id(900) } }
}))
    test('whole preflight refuses ' + label + ' before any insert', () => {
        const f = fixture(options);
        assert.equal(f.apply()?.status, 'Refused');
        assert.equal(f.writes.length, 0);
    });
test('apply refuses missing reviewed graph/content hashes', () => {
    const f = fixture(),
        r = f.run({ apply: true });
    assert.equal(r?.status, 'Refused');
    assert.equal(f.writes.length, 0);
});
for (const change of [
    'dictionary',
    'readonly',
    'limit',
    'mandatory',
    'mapping',
    'transformerOwner',
    'placeholder',
    'overlong',
    'duplicateSourceTransformer'
])
    test('source/schema contract refuses ' + change, () => {
        const f = fixture();
        if (change === 'dictionary')
            f.db.sys_dictionary.find((x) => x.name === M && x.element === 'provider').reference =
                'sys_gen_ai_provider';
        if (change === 'readonly')
            f.db.sys_dictionary.find(
                (x) => x.name === M && x.element === 'model_source'
            ).read_only = 'false';
        if (change === 'limit')
            f.db.sys_dictionary.find(
                (x) => x.name === T && x.element === 'request_transformer'
            ).max_length = '8000';
        if (change === 'mandatory')
            f.db.sys_dictionary.find((x) => x.name === M && x.element === 'provider').mandatory =
                'false';
        if (change === 'mapping')
            f.db.sys_generative_ai_provider_mapping[0].provider_api = 'unsupported';
        if (change === 'transformerOwner') f.db[T][0].model = id(900);
        if (change === 'placeholder') f.db[T][0].request_transformer = 'write code here';
        if (change === 'overlong') f.db[T][0].request_transformer = 'x'.repeat(4001);
        if (change === 'duplicateSourceTransformer')
            f.row(T, {
                model: SOURCE,
                request_transformer: request,
                response_transformer: response
            });
        assert.equal(f.apply()?.status, 'Refused');
        assert.equal(f.writes.length, 0);
    });
for (const option of ['driftOnSet', 'headerDrift'])
    test('reviewed dependency drift before insert refuses: ' + option, () => {
        const f = fixture({ [option]: true });
        assert.equal(f.apply()?.status, 'Refused');
        assert.equal(f.writes.length, 0);
        assert.equal(f.current(), OLD);
    });
for (const option of [
    'truncate',
    'wrongModel',
    'wrongOwner',
    'nativeHistory',
    'nativePredecessor',
    'race',
    'raceTransformer',
    'driftAfterInsert',
    'captureFailure',
    'deleteCapture',
    'extraCaptureRecord',
    'badCaptureScope',
    'badCapturedValue',
    'omitCapturedDefault',
    'captureApplication',
    'restoreFailure'
])
    test('uncertain outcome is Partial without cleanup or retries: ' + option, () => {
        const f = fixture({ [option]: true }),
            before = structuredClone(f.db[T][0]),
            r = f.apply();
        assert.equal(r?.status, 'Partial');
        assert.ok(r.writeAttempts.length > 0);
        assert.ok(f.writes.length <= 2);
        if (option !== 'driftAfterInsert') assert.deepEqual(f.db[T][0], before);
        if (option !== 'restoreFailure') assert.equal(f.current(), OLD);
        assert.equal(r.handoff.readyForAdd, false);
    });
for (const table of [M, T])
    for (const mode of ['failInsert', 'uncertainInsert'])
        test(
            mode + ' in ' + table + ' retains attempted ID and refuses automatic continuation',
            () => {
                const f = fixture({ [mode]: table }),
                    r = f.apply();
                assert.equal(r?.status, 'Partial');
                assert.equal(r.writeAttempts.length, table === M ? 1 : 2);
                assert.equal(f.current(), OLD);
                const count = f.writes.length;
                if (count) assert.equal(f.apply()?.status, 'Refused');
                assert.equal(f.writes.length, count);
            }
        );
test('same implementation duplicate or incomplete target refuses rather than hiding behind an explicit mapping', () => {
    for (const duplicate of [false, true]) {
        const f = fixture();
        f.row(M, { model: 'new-model', provider: MAP, connection: ALIAS });
        if (duplicate) f.row(M, { model: 'new-model', provider: MAP, connection: ALIAS });
        assert.equal(f.apply()?.status, 'Refused');
        assert.equal(f.writes.length, 0);
    }
});
test('source review hashes must describe this exact content and revision', () => {
    const f = fixture(),
        p = f.run();
    f.db[T][0].request_transformer += ' ';
    const r = f.run({
        apply: true,
        expectedSourceGraphHash: p.source.graphHash,
        expectedRequestHash: hash(request),
        expectedResponseHash: hash(response)
    });
    assert.equal(r?.status, 'Refused');
    assert.equal(f.writes.length, 0);
});
test('an uncertain first insert still inventories generated native history and reports observed identities', () => {
    const f = fixture({ uncertainInsert: M, nativeHistory: true }),
        r = f.apply();
    assert.equal(r.status, 'Partial');
    assert.ok(
        r.inventories.some((x) => x.stage === 'final observed' && x.versionMappingIds.length === 1)
    );
    assert.equal(r.observedTargets[0].id, f.db[M][1].sys_id);
    assert.equal(r.observedTargets[0].modelSource, 'customer');
    assert.equal(r.handoff.readyForAdd, false);
});
test('an uncertain second insert reports the observed wrong-model transformer without its contents', () => {
    const f = fixture({ uncertainInsert: T, wrongModel: true }),
        r = f.apply();
    assert.equal(r.status, 'Partial');
    const observed = r.observedTargets.find((x) => x.table === T);
    assert.equal(observed.modelConfigId, SOURCE);
    assert.equal(observed.requestHash, hash(request));
    assert.ok(!JSON.stringify(r).includes(request));
});
test('bounded queries refuse truncation rather than treating a limited result as complete', () => {
    const f = fixture();
    for (let n = 0; n < 501; n++) f.row(M, { model: 'new-model', provider: MAP });
    const r = f.run();
    assert.equal(r.status, 'Refused');
    assert.match(r.issues[0], /QueryLimitExceeded/);
    assert.equal(f.writes.length, 0);
});
test('racing model and transformer identities remain visible for manual investigation', () => {
    for (const option of ['race', 'raceTransformer']) {
        const f = fixture({ [option]: true }),
            r = f.apply();
        assert.equal(r.status, 'Partial');
        assert.equal(
            option === 'race' ? r.observedTargetModelIds.length : r.observedTransformerIds.length,
            2
        );
    }
});
test('a second mapping cannot hide a duplicate identifier under the same implementation', () => {
    const f = fixture(),
        peer = id(900);
    f.row('sys_generative_ai_provider_mapping', {
        ...f.db.sys_generative_ai_provider_mapping[0],
        sys_id: peer
    });
    f.row(M, { model: 'new-model', provider: peer, connection: ALIAS });
    assert.equal(f.apply().status, 'Refused');
    assert.equal(f.writes.length, 0);
});
test('selection-restoration failure is Partial even when source drift prevented every insert', () => {
    const f = fixture({ driftOnSet: true, restoreFailure: true }),
        r = f.apply();
    assert.equal(r.status, 'Partial');
    assert.equal(f.writes.length, 0);
    assert.match(r.issues.join(','), /PreviousUpdateSetRestoreFailed/);
});
test('R1 preview of an exact active registration keeps NoOp but never marks Add ready', () => {
    const f = fixture({ params: { active: true } });
    assert.equal(f.apply().status, 'Applied');
    const r = f.run();
    assert.equal(r.status, 'NoOp');
    assert.equal(r.apply, false);
    assert.equal(r.handoff.readyForAdd, false);
    assert.equal(f.writes.length, 2);
    assert.equal(f.captures.length, 2);
    assert.equal(f.apply().handoff.readyForAdd, true);
});
test('R2 model revision drift during transformer insertion cannot reuse the earlier model capture', () => {
    const f = fixture({ targetModelRevisionDrift: true, params: { active: true } }),
        r = f.apply();
    assert.equal(r.status, 'Partial');
    assert.equal(r.handoff.readyForAdd, false);
    assert.equal(r.writeAttempts.length, 2);
    assert.equal(f.writes.length, 2);
    assert.equal(f.captures.length, 2);
    assert.equal(r.observedTargets.find((x) => x.table === M).revision, '1');
    assert.match(r.issues.join(','), /CapturedFieldMismatch:sys_mod_count/);
    assert.equal(f.current(), OLD);
});
for (const table of [M, T])
    test('R2 final snapshot rejects late capture drift for ' + table, () => {
        const f = fixture({ lateCaptureDriftTable: table, params: { active: true } }),
            r = f.apply();
        assert.equal(r.status, 'Partial');
        assert.equal(r.handoff.readyForAdd, false);
        assert.equal(r.writeAttempts.length, 2);
        assert.equal(f.writes.length, 2);
        assert.equal(f.captures.length, 2);
        assert.match(r.issues.join(','), /CapturedFieldMismatch:sys_mod_count/);
        assert.equal(f.current(), OLD);
    });
test('R3 transport records use application without requiring metadata ownership fields', () => {
    const f = fixture();
    assert.equal(Object.hasOwn(f.db.sys_update_set[0], 'sys_scope'), false);
    assert.equal(f.run().status, 'Preview');
    const r = f.apply();
    assert.equal(r.status, 'Applied');
    assert.equal(f.writes.length, 2);
    assert.equal(f.captures.length, 2);
    assert.equal(f.current(), OLD);
});
test('R3 missing mandatory model ownership is still refused before insertion', () => {
    const f = fixture({ missingOwnedField: 'sys_scope' }),
        r = f.apply();
    assert.equal(r.status, 'Refused');
    assert.match(r.issues.join(','), /MissingField:sys_generative_ai_model_config.sys_scope/);
    assert.equal(f.writes.length, 0);
});
