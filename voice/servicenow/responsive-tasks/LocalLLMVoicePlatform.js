/* Deployment boundary: no property, manifest hash, or Boolean enables authority. */
var LocalLLMVoicePlatform = Class.create();
LocalLLMVoicePlatform.prototype = {
    initialize:function() {},
    registry:function() {
        if(!gs.getUserID() || gs.getUserName()==='guest') throw new Error('denied');
        return {protocol_version:2,package_revision:'responsive-tasks-v2-candidate-1',capability_revision:null,
            principal:null,service_id:null,agents:[],capabilities:{safe_write:false,independent_context:false,
                checkpoints:false,status_lookup:false,durable_execution:false,authoritative_idempotency:false,version_fence:false},
            evidence:{source:'owned_package',qualification:'unqualified',missing:[
                'platform_principal_service_agent_tool_binding','responsive_unguarded_tool_removal',
                'unique_index_and_transaction_qualification','claim_durable_before_side_effect',
                'operation_to_request_receipt_reconciliation','static_scc_facade_migration']}};
    },
    authorize:function(write) {
        if(!gs.getUserID() || gs.getUserName()==='guest') throw new Error('denied');
        // gs authentication alone does not attest native service/agent/tool rights
        // or the original requester behind the fixed integration account.
        // Replace only after source+wire review of that exact platform policy;
        // no SDK alias, body principal, credential parsing or role grant fallback.
        throw new Error('live_authority_unqualified');
    },
    control:function() {
        return new LocalLLMVoiceTaskControl(new LocalLLMVoiceRepository(),this,
            {submit:function(input) {return new LocalLLMSCCOrderBusiness().submit(input);}});
    },
    type:'LocalLLMVoicePlatform'
};
