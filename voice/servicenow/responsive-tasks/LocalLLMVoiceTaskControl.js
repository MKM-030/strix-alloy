/* ES5; prospective owned Global Script Include. No ambient/model authority. */
var LocalLLMVoiceTaskControl = Class.create();
LocalLLMVoiceTaskControl.prototype = {
    initialize: function(repository, policy, business) {
        this.repo = repository;
        this.policy = policy;
        this.business = business;
    },
    _fail: function(code) { throw new Error(code); },
    _id: function(value) {
        if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value)) this._fail('invalid_identifier');
        return value;
    },
    _schema: function(value, required) {
        if (!value || Object.prototype.toString.call(value) !== '[object Object]') this._fail('invalid_schema');
        var keys = Object.keys(value).sort();
        if (keys.join('|') !== required.slice().sort().join('|')) this._fail('invalid_schema');
    },
    _canonical: function(value) {
        if (value === null || typeof value !== 'object') return JSON.stringify(value);
        var self = this;
        return '{' + Object.keys(value).sort().map(function(key) { return JSON.stringify(key) + ':' + self._canonical(value[key]); }).join(',') + '}';
    },
    _actor: function(task, write) {
        var a = this.policy.authorize(write);
        if (!a || a.execute!==true || (write && a.write!==true) || typeof a.expires_at!=='number' || !(a.expires_at > this.repo.now())) this._fail('denied');
        var fields = ['principal', 'service', 'agent', 'tool', 'registry_revision'];
        for (var i=0;i<fields.length;i++) {
            this._id(a[fields[i]]);
            if (task && task[fields[i]] !== a[fields[i]]) this._fail('denied');
        }
        if (task && task.expires_at <= this.repo.now()) this._fail('denied');
        return a;
    },
    _binding: function(a) {
        return {principal:a.principal,service:a.service,agent:a.agent,tool:a.tool,registry_revision:a.registry_revision};
    },
    _proposal: function(input) {
        this._schema(input, ['employee_name','start_date','delivery_location','manager_name']);
        var out = {}, names = Object.keys(input);
        for(var i=0;i<names.length;i++) {
            var name=names[i], value=input[name];
            if(typeof value !== 'string' || !value.replace(/^\s+|\s+$/g,'') || value.length>100 || /[\x00-\x1f\x7f]/.test(value)) this._fail('invalid_proposal');
            out[name]=value.replace(/^\s+|\s+$/g,'');
        }
        if(!/^\d{4}-\d{2}-\d{2}$/.test(out.start_date)) this._fail('invalid_proposal');
        // Calendar, requester, manager, catalog and cart remain SCC business validation.
        return out;
    },
    create: function(input) {
        this._schema(input,['command_id','objective','context_version']);
        this._id(input.command_id);
        if(typeof input.objective!=='string'||!input.objective||input.objective.length>4000||input.context_version!==1) this._fail('invalid_task');
        var actor=this._actor(null,false), binding=this._binding(actor), hash=this.repo.hash(this._canonical({binding:binding,input:input}));
        var prior=this.repo.get('task','command_id',input.command_id);
        if(prior) {
            this._actor(prior,false);
            if(prior.command_hash!==hash) this._fail('command_conflict');
            return {task_id:prior.id,revision:'root',registry_revision:prior.registry_revision};
        }
        var row=binding;
        row.id=this.repo.id(); row.command_id=input.command_id; row.command_hash=hash;
        row.objective=input.objective;row.context_version=1;row.expires_at=Math.min(actor.expires_at,this.repo.now()+3600000);
        if(!this.repo.insert('task',row)) this._fail('create_conflict');
        return {task_id:row.id,revision:'root',registry_revision:row.registry_revision};
    },
    _task: function(id, write) {
        this._id(id);
        var task=this.repo.get('task','id',id);
        if(!task) this._fail('denied');
        this._actor(task,write);return task;
    },
    _head: function(task) {
        var head={id:'root',kind:'create',version:1,task_id:task.id}, next, count=0;
        while((next=this.repo.get('transition','predecessor_slot',task.id+':'+head.id))) {
            if(next.task_id!==task.id||next.version!==head.version+1||++count>128) this._fail('invalid_chain');
            head=next;
        }
        return head;
    },
    status: function(id) {
        var task=this._task(id,false), head=this._head(task);
        var event=head.id==='root'?null:this.repo.get('event','event_id','transition:'+head.id);
        return {task_id:task.id,revision:head.id,kind:head.kind,version:head.version,registry_revision:task.registry_revision,
            operation:head.kind==='commit'?this.repo.get('operation','operation_key',head.operation_key):null,events:event?[event]:[]};
    },
    operation: function(key) {
        this._id(key);var op=this.repo.get('operation','operation_key',key);
        if(!op) this._fail('denied');this._task(op.task_id,false);return op;
    },
    command: function(id, input) {
        var kinds={amend:['proposal'],prepare:['proposal'],confirm:['proposal_id','utterance_ref'],
            cancel:[],commit:['proposal_id','confirmation_id','operation_key']};
        if(!input || !Object.prototype.hasOwnProperty.call(kinds,input.kind)) this._fail('invalid_command');
        this._schema(input,['command_id','expected_revision','kind','context_version'].concat(kinds[input.kind]));
        this._id(input.command_id);this._id(input.expected_revision);
        if(typeof input.context_version!=='number'||input.context_version%1||input.context_version<1||input.context_version>2147483647) this._fail('invalid_command');
        var task=this._task(id,input.kind==='commit'), actor=this._binding(task);
        var fingerprint=this.repo.hash(this._canonical({task_id:id,binding:actor,input:input}));
        var prior=this.repo.get('transition','command_id',input.command_id);
        if(prior) {
            if(prior.task_id!==id||prior.command_hash!==fingerprint) this._fail('command_conflict');
            return this._result(task,prior);
        }
        var head=this._head(task);
        if(head.id!==input.expected_revision) this._fail('revision_conflict');
        if(head.kind==='commit') this._fail('correction_deferred');
        if(head.kind==='cancel') this._fail('task_cancelled');
        if(head.context_version && input.context_version<head.context_version) this._fail('revision_conflict');
        var row={id:this.repo.id(),task_id:id,predecessor_slot:id+':'+head.id,predecessor:head.id,
            command_id:input.command_id,command_hash:fingerprint,kind:input.kind,version:head.version+1,context_version:input.context_version,
            principal:task.principal,service:task.service,agent:task.agent,tool:task.tool,registry_revision:task.registry_revision};
        if(input.kind==='prepare'||input.kind==='amend') {
            row.proposal=this._proposal(input.proposal);row.payload_hash=this.repo.hash(this._canonical(row.proposal));
            row.expires_at=Math.min(task.expires_at,this.repo.now()+300000);
        } else if(input.kind==='confirm') {
            this._id(input.proposal_id);this._id(input.utterance_ref);
            if(head.kind!=='prepare'||head.id!==input.proposal_id||head.expires_at<=this.repo.now()) this._fail('proposal_conflict');
            row.proposal_id=head.id;row.proposal=head.proposal;row.payload_hash=head.payload_hash;
            row.expires_at=head.expires_at;row.utterance_ref=input.utterance_ref;
        } else if(input.kind==='commit') {
            this._id(input.proposal_id);this._id(input.confirmation_id);this._id(input.operation_key);
            if(head.kind!=='confirm'||head.id!==input.confirmation_id||head.proposal_id!==input.proposal_id||head.expires_at<=this.repo.now()) this._fail('confirmation_conflict');
            if(this.repo.get('operation','operation_key',input.operation_key)) this._fail('operation_conflict');
            row.operation_key=input.operation_key;row.proposal_id=head.proposal_id;row.confirmation_id=head.id;
            row.proposal=head.proposal;row.payload_hash=head.payload_hash;row.expires_at=head.expires_at;
        }
        var inserted=this.repo.insert('transition',row);
        if(!inserted) {
            var winner=this.repo.get('transition','predecessor_slot',row.predecessor_slot);
            if(!winner||winner.command_id!==row.command_id||winner.command_hash!==row.command_hash) this._fail('revision_conflict');
            row=winner;
        }
        return this._result(task,row);
    },
    _result: function(task,row) {
        var result={task_id:task.id,command_id:row.command_id,revision:row.id,kind:row.kind,version:row.version};
        if(row.proposal) {result.proposal=row.proposal;result.payload_hash=row.payload_hash;result.expires_at=row.expires_at;}
        if(row.kind==='commit') result.operation=new LocalLLMVoiceOrderGuard(this.repo,this.policy,this.business).dispatch(task,row);
        var eventId='transition:'+row.id;
        if(!this.repo.get('event','event_id',eventId)) {
            var event={id:this.repo.id(),event_id:eventId,sequence:row.version,task_sequence:task.id+':'+row.version,
                task_id:task.id,operation_id:row.operation_key||row.command_id,context_version:row.context_version,
                status:row.kind==='commit'?'submitted':(row.kind==='cancel'?'cancelled':'awaiting_input'),text:''};
            if(!this.repo.insert('event',event) && !this.repo.get('event','event_id',eventId)) this._fail('event_unavailable');
        }
        return result;
    },
    type:'LocalLLMVoiceTaskControl'
};
