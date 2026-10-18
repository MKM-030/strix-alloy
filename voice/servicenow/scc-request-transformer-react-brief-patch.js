/* Reusable dry run. Append concise Thought guidance only for owned SCC ReAct prompts.
 * Normal Global Background UI, Record for rollback enabled. Protected configs are
 * read/verified only. Default APPLY=false. No inference or order occurs.
 */
(function () {
    var APPLY = false;
    var ID = 'bc126377936f8750e7f2b9fa6aba1012';
    var BEFORE = '7462cb47ff804bfd72fb89c2ab08c9d4cb4d68255e47e4a744a8e3aea2997c02';
    var AFTER = '3ba9fc442bd5cc0d24468e868d0ea302af480df262d5cbd5bed00f157083faf0';
    var RESPONSE = '581e8e127c45435aefe541bad277cc8249d1ac809065aa0e4fc2bef57783e2d2';
    var PROMPT = '4c91a66ccf7aa580ed8737278fb5b2554cf0070c13b7a82994b562838f32da55';
    var ANCHOR = '    var model = p.model ? String(p.model) : "halogen-v2";';
    var ADDITION = "    if (String(p.aiConfig) === \"4780c7e193f747d0e7f2b9fa6aba1030\" &&\r\n            prompt.indexOf(\"SCC Laptop Onboarding\") !== -1) {\r\n        prompt += \"\\n\\n<scc_react_brief_20261013>\\nFuer den SCC-Laptop-Onboarding-Agenten enthaelt jedes Thought-Feld nur einen kurzen Satz mit hoechstens 25 Woertern als knappe Entscheidungsbegruendung. Wiederhole darin weder die Aufgabe noch bekannte Gespraechsdaten oder Werkzeugbeschreibungen. Alle vorgeschriebenen JSON-Felder, Aktionsnamen, Berechtigungen und Referenzen sowie alle vollstaendigen Action-Eingaben bleiben unveraendert. Die bestehenden Regeln zur Aktionsauswahl, ausdruecklichen Bestellbestaetigung und Vermeidung automatischer Wiederholungen bleiben verbindlich.\\n</scc_react_brief_20261013>\";\r\n    }\r\n";
    var receipt = {status:'preflight',target:ID,field:'request_transformer',before:BEFORE,
        after:AFTER,attempted:false,verified:false,protected_config_written:false};
    var stage='authorization';
    function need(ok, why) { if (!ok) throw new Error(why); }
    function hash(s) { return String(new GlideDigest().getSHA256Hex(String(s))).toLowerCase(); }
    function value(g,f) {
        need(g.isValidField(f), 'missing_field:'+f);
        var e=g.getElement(f);
        need(e!==null&&typeof e!=='undefined'&&e.canRead(), 'read_access:'+f);
        var v=g.getValue(f); return v===null?'':String(v);
    }
    function load(t,id) {
        var g=new GlideRecordSecure(t);need(g.get(id)&&g.canRead(),'record_read:'+t+':'+id);return g;
    }
    function fields(g, expected) {
        for(var f in expected)if(expected.hasOwnProperty(f))
            need(value(g,f)===expected[f],'drift:'+g.getUniqueValue()+':'+f);
    }
    function preflight() {
        var c=load('sys_generative_ai_config','8380c7e193f747d0e7f2b9fa6aba10b6');
        fields(c,{name:'AIA Unified Planner (Custom LLM Provider V2)',active:'1',state:'published',
            model:'halogen-v2',definition:'8f80c7e193f747d0e7f2b9fa6aba109a',
            definition_table:'sys_one_extend_capability_definition',sys_scope:'32808450431302106c3603295bb8f245',
            sys_mod_count:'3',sys_updated_on:'2026-10-13 16:13:15',prompt_template_role:'user',
            max_tokens:'4096',temperature:'0',additional_configurations:'{"json_format_supported":"true"}'});
        need(hash(value(c,'prompt'))===PROMPT,'protected_prompt_source_drift');
        var b=load('sys_generative_ai_prompt_config','c780c7e193f747d0e7f2b9fa6aba10b9');
        fields(b,{definition:'8f80c7e193f747d0e7f2b9fa6aba109a',ai_config:'8380c7e193f747d0e7f2b9fa6aba10b6',
            filter_properties:'',filter_type:'default',order:'100',sys_scope:'32808450431302106c3603295bb8f245',
            sys_mod_count:'0',sys_updated_on:'2026-10-08 05:01:43'});
        var r=load('sys_generative_ai_config','4780c7e193f747d0e7f2b9fa6aba1030');
        fields(r,{name:'AIA ReAct-V3 Engine (Custom LLM Provider V2)',active:'1',state:'published',
            model:'halogen-v2',definition:'4f80c7e193f747d0e7f2b9fa6aba1027',
            definition_table:'sys_one_extend_capability_definition',sys_scope:'32808450431302106c3603295bb8f245',
            sys_mod_count:'1',sys_updated_on:'2026-10-12 22:41:42',max_tokens:'4096',temperature:'0',
            additional_configurations:''});
        need(hash(value(r,'prompt'))==='1b7df1c35a5f4db8709b87b7327f581f3300228897c60e19de877d11d4a84b42','protected_react_prompt_drift');
        var chat=load('sn_aia_agent','a4a9438393738354e7f2b9fa6aba101d');
        fields(chat,{name:'SCC Laptop Onboarding'});
        var voice=load('sn_aia_agent','a6337ddf93f787105c8132d47aba1058');
        fields(voice,{name:'SCC Laptop Onboarding Voice'});
        var g=load('sys_generative_ai_custom_llm_transformer',ID);
        fields(g,{model:'ff74fcef93a70350e7f2b9fa6aba10ea',sys_scope:'global'});
        need(hash(value(g,'response_transformer'))===RESPONSE,'response_source_drift');
        var source=value(g,'request_transformer'),h=hash(source);
        need(h===BEFORE||h===AFTER,'request_source_drift');
        if(h===BEFORE)fields(g,{sys_mod_count:'10',sys_updated_on:'2026-10-13 18:15:01'});
        need(g.canWrite()&&g.getElement('request_transformer').canWrite(),'request_write_access');
        return g;
    }
    try {
        receipt.execution_scope=String(gs.getCurrentScopeName());
        need(gs.hasRole('admin'),'admin_required');
        need(receipt.execution_scope==='global'||receipt.execution_scope==='rhino.global','global_scope_required');
        stage='preflight';var g=preflight(),source=value(g,'request_transformer');
        if(hash(source)===AFTER){receipt.status='already_applied';receipt.verified=true;}
        else {
            need(source.split(ANCHOR).length===2,'replacement_count');
            var desired=source.replace(ANCHOR,ADDITION+ANCHOR);
            need(hash(desired)===AFTER,'desired_source_hash');
            if(!APPLY)receipt.status='dry_run';
            else {
                stage='immediate_recheck';g=preflight();
                need(hash(value(g,'request_transformer'))===BEFORE,'concurrent_source_change');
                stage='update';g.setValue('request_transformer',desired);receipt.attempted=true;
                need(String(g.update()||'')===ID,'update_failed');
                stage='fresh_readback';g=preflight();
                need(hash(value(g,'request_transformer'))===AFTER,'readback_failed');
                receipt.verified=true;receipt.status='applied';
            }
        }
    }catch(e){receipt.status=receipt.attempted?'partial_or_uncertain':'aborted';receipt.stage=stage;
        receipt.error=String(e.message||e).substring(0,240);}
    gs.info('[SCC REACT BRIEF PATCH] '+JSON.stringify(receipt));
})();
