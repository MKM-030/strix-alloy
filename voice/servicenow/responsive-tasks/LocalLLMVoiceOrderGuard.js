/* Separate durable claim; no lease expiry, reclaim, or arbitrary tool lookup. */
var LocalLLMVoiceOrderGuard = Class.create();
LocalLLMVoiceOrderGuard.prototype = {
    initialize:function(repository,policy,business) {this.repo=repository;this.policy=policy;this.business=business;},
    dispatch:function(task,fence) {
        var control=new LocalLLMVoiceTaskControl(this.repo,this.policy,this.business);
        task=control._task(task.id,true);
        var stored=this.repo.get('transition','id',fence.id);
        if(!stored||stored.kind!=='commit'||stored.task_id!==task.id||stored.command_hash!==fence.command_hash) throw new Error('fence_denied');
        fence=stored;
        var key=fence.operation_key, op=this.repo.get('operation','operation_key',key);
        if(!op) {
            op={id:this.repo.id(),operation_key:key,task_id:task.id,principal:task.principal,
                service:task.service,agent:task.agent,tool:task.tool,registry_revision:task.registry_revision,
                fence_id:fence.id,proposal_id:fence.proposal_id,confirmation_id:fence.confirmation_id,
                payload_hash:fence.payload_hash,proposal:fence.proposal,context_version:fence.context_version,state:'outcome_unknown'};
            if(!this.repo.insert('operation',op)) op=this.repo.get('operation','operation_key',key);
        }
        if(!op||op.task_id!==task.id||op.fence_id!==fence.id||op.payload_hash!==fence.payload_hash) throw new Error('operation_conflict');
        if(op.receipt) return op;
        // The production policy remains hard denied until a separate transaction
        // durably commits this claim BEFORE CartJS. Source tests cannot prove that.
        var claim={id:this.repo.id(),operation_key:key,operation_id:op.id,task_id:task.id,claimed_at:this.repo.now()};
        if(!this.repo.insert('claim',claim)) return this.repo.get('operation','operation_key',key);
        control._actor(task,true);
        try {
            var input={confirmed:'true',employee_name:op.proposal.employee_name,start_date:op.proposal.start_date,
                delivery_location:op.proposal.delivery_location,manager_name:op.proposal.manager_name};
            var result=this.business.submit(input);
            if(result&&result.ok===true&&result.request_id&&result.requested_item_id) {
                control._id(String(result.request_id));control._id(String(result.requested_item_id));
                return this.repo.receipt(key,{state:'succeeded',request_ref:String(result.request_id),execution_ref:String(result.requested_item_id)});
            }
            if(result&&result.request_id) {
                control._id(String(result.request_id));
                return this.repo.receipt(key,{state:'outcome_unknown',request_ref:String(result.request_id)});
            }
            // A business failure message can follow an actual side effect. Do not
            // infer no order or retry permission from ok:false or missing RITM.
        } catch(ignored) {}
        return this.repo.get('operation','operation_key',key);
    },
    type:'LocalLLMVoiceOrderGuard'
};
