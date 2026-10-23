/* Fixed owned tables only. Direct table ACLs deny callers; server code owns writes. */
var LocalLLMVoiceRepository = Class.create();
LocalLLMVoiceRepository.prototype = {
    initialize:function() {
        this.tables={task:'u_scc_voice_task',transition:'u_scc_voice_transition',operation:'u_scc_voice_operation',
            claim:'u_scc_voice_dispatch_claim',event:'u_scc_voice_event'};
        this.columns={id:'u_key',command_id:'u_command_key',predecessor_slot:'u_predecessor_slot',
            operation_key:'u_operation_key',task_id:'u_task_key',event_id:'u_source_event_key',task_sequence:'u_task_sequence',
            service:'u_service',agent:'u_agent',tool:'u_tool',registry_revision:'u_registry_revision',
            payload_hash:'u_payload_hash',proposal_id:'u_proposal_key',confirmation_id:'u_confirmation_key'};
    },
    id:function() {return String(gs.generateGUID());},
    now:function() {return new GlideDateTime().getNumericValue()*1;},
    hash:function(text) {return String(new GlideDigest().getSHA256Hex(text));},
    _record:function(table) {
        if(!Object.prototype.hasOwnProperty.call(this.tables,table)) throw new Error('invalid_table');
        var record=new GlideRecord(this.tables[table]);
        if(!record.isValid()) throw new Error('schema_unavailable');
        return record;
    },
    _find:function(table,field,value) {
        if(!Object.prototype.hasOwnProperty.call(this.columns,field)) throw new Error('invalid_field');
        var gr=this._record(table), column=this.columns[field];
        if(!gr.isValidField(column)) throw new Error('schema_unavailable');
        gr.addQuery(column,value);gr.setLimit(2);gr.query();return gr;
    },
    get:function(table,field,value) {
        var gr=this._find(table,field,value);
        if(!gr.next()) return null;
        var data=JSON.parse(String(gr.getValue('u_data')));
        if(gr.next()) throw new Error('unique_index_unavailable');
        if(table==='operation') {
            var receipt=this.get('event','event_id','receipt:'+data.operation_key);
            if(receipt) {data.receipt=receipt.receipt;data.state=receipt.receipt.state;}
        }
        return data;
    },
    insert:function(table,row) {
        var gr=this._record(table);gr.initialize();
        var fields=Object.keys(this.columns);
        for(var i=0;i<fields.length;i++) if(row[fields[i]]!==undefined && gr.isValidField(this.columns[fields[i]])) gr.setValue(this.columns[fields[i]],row[fields[i]]);
        gr.setValue('u_data',JSON.stringify(row));
        if(row.principal) gr.setValue('u_owner',row.principal);
        if(row.task_id) {
            var task=this._find('task','id',row.task_id);
            if(!task.next()) throw new Error('task_reference_unavailable');
            gr.setValue('u_task',task.getUniqueValue());
        }
        if(table==='claim') {
            var operation=this._find('operation','id',row.operation_id);
            if(!operation.next()) throw new Error('operation_reference_unavailable');
            gr.setValue('u_operation',operation.getUniqueValue());
        }
        try {if(!gr.insert()) return null;} catch(ignored) {return null;}
        return row;
    },
    receipt:function(key,receipt) {
        // Receipt is an append-only event, avoiding concurrent mutable result updates.
        var op=this.get('operation','operation_key',key);
        if(!op) throw new Error('operation_unavailable');
        var eventKey='receipt:'+key, existing=this.get('event','event_id',eventKey);
        if(existing && JSON.stringify(existing.receipt)!==JSON.stringify(receipt)) throw new Error('receipt_conflict');
        if(!existing) {
            var row={id:this.id(),event_id:eventKey,task_id:op.task_id,task_sequence:op.task_id+':receipt:'+key,
                operation_key:key,receipt:receipt};
            if(!this.insert('event',row)) {
                existing=this.get('event','event_id',eventKey);
                if(!existing || JSON.stringify(existing.receipt)!==JSON.stringify(receipt)) throw new Error('receipt_conflict');
            }
        }
        op.receipt=receipt;op.state=receipt.state;return op;
    },
    type:'LocalLLMVoiceRepository'
};
