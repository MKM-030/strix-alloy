/* Narrow authenticated owned REST facade. No arbitrary table/class/URL input. */
var LocalLLMVoiceResource = Class.create();
LocalLLMVoiceResource.prototype = {
    initialize:function() {},
    run:function(kind,request,response) {
        try {
            var platform=new LocalLLMVoicePlatform(), result;
            if(kind==='registry') result=platform.registry();
            else {
                // Deny before any input/table work until real platform binding exists.
                platform.authorize(kind==='command');
                var control=platform.control(), body;
                if(kind==='create'||kind==='command') body=this._body(request);
                if(kind==='create') result=control.create(body);
                else if(kind==='status') result=control.status(String(request.pathParams.id||''));
                else if(kind==='command') result=control.command(String(request.pathParams.id||''),body);
                else if(kind==='operation') result=control.operation(String(request.pathParams.id||''));
                else throw new Error('invalid_route');
            }
            response.setStatus(200);response.setBody(result);
        } catch(error) {
            var code=String(error.message||error);
            var allowed=['denied','live_authority_unqualified','revision_conflict','command_conflict','operation_conflict',
                'confirmation_conflict','proposal_conflict','correction_deferred','task_cancelled','invalid_schema',
                'invalid_command','invalid_identifier','invalid_proposal','invalid_task','create_conflict'];
            if(allowed.indexOf(code)<0) code='authority_unavailable';
            response.setStatus(code==='denied'?403:(code==='live_authority_unqualified'||code==='authority_unavailable'?503:409));
            response.setBody({error:code,retry_automatically:false});
        }
    },
    _body:function(request) {
        var text=String(request.body.dataString||'');
        if(!text||text.length>8192) throw new Error('invalid_schema');
        // Reject duplicate member names including escaped equivalents BEFORE parse.
        // A tiny bounded JSON scanner tracks object keys, not regex on raw names.
        var p=0;
        function ws(){while(/\s/.test(text.charAt(p))&&p<text.length)p++;}
        function string(){var start=p++;while(p<text.length){var c=text.charAt(p++);if(c==='\\')p++;else if(c==='"')return JSON.parse(text.substring(start,p));}throw new Error('invalid_schema');}
        function value(depth){
            if(depth>8)throw new Error('invalid_schema');ws();var c=text.charAt(p);
            if(c==='"'){string();return;}
            if(c==='{'){p++;var keys={};ws();if(text.charAt(p)==='}'){p++;return;}
                while(p<text.length){ws();if(text.charAt(p)!=='"')throw new Error('invalid_schema');var k=string();
                    if(Object.prototype.hasOwnProperty.call(keys,'$'+k))throw new Error('invalid_schema');keys['$'+k]=true;
                    ws();if(text.charAt(p++)!==':')throw new Error('invalid_schema');value(depth+1);ws();c=text.charAt(p++);if(c==='}')return;if(c!==',')throw new Error('invalid_schema');}}
            else if(c==='[')throw new Error('invalid_schema');
            else {var start=p;while(p<text.length&&!/[\s,}]/.test(text.charAt(p)))p++;if(start===p)throw new Error('invalid_schema');JSON.parse(text.substring(start,p));return;}
            throw new Error('invalid_schema');
        }
        value(0);ws();if(p!==text.length)throw new Error('invalid_schema');return JSON.parse(text);
    },
    type:'LocalLLMVoiceResource'
};
