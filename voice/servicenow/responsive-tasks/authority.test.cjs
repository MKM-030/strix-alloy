'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const path = require('node:path');
function fixture() {
    let n = 0, calls = 0, hook = null;
    const data = {task:[], transition:[], operation:[], claim:[], event:[]};
    const keys = {task:['id'], transition:['predecessor_slot','command_id'], operation:['operation_key'], claim:['operation_key'], event:['event_id','task_sequence']};
    const copy = x => JSON.parse(JSON.stringify(x));
    const repo = {
        id: () => 'id-' + (++n), now: () => 1000,
        hash: s => crypto.createHash('sha256').update(s).digest('hex'),
        get: (table, field, value) => copy(data[table].find(x => x[field] === value) || null),
        insert(table, row) {
            if (hook) { const run = hook; hook = null; run(table, row); }
            if (keys[table].some(key => data[table].some(x => x[key] === row[key]))) return null;
            data[table].push(copy(row)); return copy(row);
        },
        receipt(key, receipt) {
            const row = data.operation.find(x => x.operation_key === key);
            if (row.receipt && JSON.stringify(row.receipt) !== JSON.stringify(receipt)) throw Error('receipt_conflict');
            row.receipt = copy(receipt); row.state = receipt.state; return copy(row);
        }
    };
    const sandbox = {Class:{create:()=>function(){this.initialize.apply(this,arguments);}}};
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'LocalLLMVoiceTaskControl.js'),'utf8'), sandbox);
    vm.runInNewContext(fs.readFileSync(path.join(__dirname,'LocalLLMVoiceOrderGuard.js'),'utf8'), sandbox);
    const actor = {principal:'user-1', service:'service-1', agent:'agent-1', tool:'tool-1', registry_revision:'registry-1', expires_at:2000, execute:true, write:true};
    const policy = {authorize: () => copy(actor)};
    const business = {submit: () => {calls++; return {ok:true, request_id:'req-1', requested_item_id:'ritm-1'};}};
    const engine = new sandbox.LocalLLMVoiceTaskControl(repo, policy, business);
    const task = engine.create({command_id:'create-1', objective:'Laptop', context_version:1});
    const proposal = {employee_name:'A',start_date:'2026-12-01',delivery_location:'B',manager_name:'C'};
    function cmd(kind, revision, extra={}) {
        return {command_id:'command-' + (++n),expected_revision:revision,kind,context_version:1,...extra};
    }
    const prepared = engine.command(task.task_id, cmd('prepare','root',{proposal}));
    const confirmed = engine.command(task.task_id, cmd('confirm',prepared.revision,{proposal_id:prepared.revision,utterance_ref:'utterance-1'}));
    const commit = cmd('commit',confirmed.revision,{proposal_id:prepared.revision,confirmation_id:confirmed.revision,operation_key:'operation-1'});
    return {engine,actor,repo,data,task,prepared,confirmed,commit,cmd,proposal,business,
        calls:()=>calls, interleave:fn=>{hook=fn;}};
}
test('duplicateCommitOnce', () => {
    const f=fixture();
    f.interleave((table)=> { if(table==='transition') f.engine.command(f.task.task_id, f.commit); });
    const one=f.engine.command(f.task.task_id,f.commit), two=f.engine.command(f.task.task_id,f.commit);
    assert.equal(f.calls(),1); assert.deepEqual(one,two); assert.equal(one.operation.receipt.request_ref,'req-1');
});
test('sameKeyChangedPayloadConflict',()=>{
    const f=fixture(); f.engine.command(f.task.task_id,f.commit);
    assert.throws(()=>f.engine.command(f.task.task_id,{...f.commit,proposal_id:'other'}),/conflict/);
    assert.equal(f.calls(),1);
});
test('amendWinsInvalidatesConfirmation',()=>{
    const f=fixture();
    f.interleave(table=>{if(table==='transition')f.engine.command(f.task.task_id,f.cmd('amend',f.confirmed.revision,{proposal:{...f.proposal,delivery_location:'D'}}));});
    assert.throws(()=>f.engine.command(f.task.task_id,f.commit),/revision_conflict/); assert.equal(f.calls(),0);
});
test('commitWinsCorrectionDeferred',()=>{
    const f=fixture(), committed=f.engine.command(f.task.task_id,f.commit);
    assert.throws(()=>f.engine.command(f.task.task_id,f.cmd('amend',committed.revision,{proposal:f.proposal})),/correction_deferred/);
    assert.equal(f.calls(),1);
});
test('wrongOwnerAgentToolDenied',()=>{
    for (const field of ['principal','agent','tool','service']) {
        const f=fixture(); f.actor[field]='wrong';
        assert.throws(()=>f.engine.command(f.task.task_id,f.commit),/denied/); assert.equal(f.calls(),0);
    }
    for(const field of ['execute','write']) {
        const f=fixture();f.actor[field]=false;
        assert.throws(()=>f.engine.command(f.task.task_id,f.commit),/denied/);assert.equal(f.calls(),0);
    }
});
test('expiredAuthDenied',()=>{
    const f=fixture();f.actor.expires_at=999;
    assert.throws(()=>f.engine.command(f.task.task_id,f.commit),/denied/);assert.equal(f.calls(),0);
});
test('uncertainNoReclaim',()=>{
    const f=fixture();let attempts=0;
    f.business.submit=()=>{attempts++;throw Error('lost result');};
    assert.equal(f.engine.command(f.task.task_id,f.commit).operation.state,'outcome_unknown');
    assert.equal(f.engine.command(f.task.task_id,f.commit).operation.state,'outcome_unknown');
    assert.equal(attempts,1);assert.equal(f.data.claim.length,1);
});
test('nullInsertNeverDispatchesAndWrongRevisionCannotFork',()=>{
    const f=fixture(); const insert=f.repo.insert;
    f.repo.insert=(table,row)=>table==='transition'?null:insert(table,row);
    assert.throws(()=>f.engine.command(f.task.task_id,f.commit),/conflict/);assert.equal(f.calls(),0);
    assert.throws(()=>f.engine.command(f.task.task_id,{...f.commit,expected_revision:'invented'}),/revision_conflict/);
});
test('cancelCompetesInSameSlotAndConfirmationCannotSkipPreparation',()=>{
    const f=fixture();
    f.engine.command(f.task.task_id,f.cmd('cancel',f.confirmed.revision));
    assert.throws(()=>f.engine.command(f.task.task_id,f.commit),/revision_conflict/);assert.equal(f.calls(),0);
    const g=fixture();
    const amended=g.engine.command(g.task.task_id,g.cmd('amend',g.confirmed.revision,{proposal:g.proposal}));
    assert.throws(()=>g.engine.command(g.task.task_id,g.cmd('confirm',amended.revision,{proposal_id:g.prepared.revision,utterance_ref:'u2'})),/proposal_conflict/);
});
test('rightRevokedAtDispatchAndClaimFailureCannotExecute',()=>{
    const f=fixture();
    f.interleave(table=>{if(table==='transition')f.actor.write=false;});
    assert.throws(()=>f.engine.command(f.task.task_id,f.commit),/denied/);assert.equal(f.calls(),0);
    const g=fixture(),insert=g.repo.insert;
    g.repo.insert=(table,row)=>table==='claim'?null:insert(table,row);
    assert.equal(g.engine.command(g.task.task_id,g.commit).operation.state,'outcome_unknown');assert.equal(g.calls(),0);
});
test('operationKeyCannotMoveToAnotherTaskAndStatusOwnershipChecked',()=>{
    const f=fixture();f.engine.command(f.task.task_id,f.commit);
    assert.throws(()=>f.engine.command(f.task.task_id,{...f.commit,command_id:'different'}),/revision_conflict/);
    f.actor.principal='other';assert.throws(()=>f.engine.status(f.task.task_id),/denied/);
    assert.throws(()=>f.engine.operation('operation-1'),/denied/);
});
test('partialRequestReferenceRetainedWithoutReplayOrSuccessClaim',()=>{
    const f=fixture();let calls=0;
    f.business.submit=()=>{calls++;return {ok:false,request_id:'req-partial'};};
    const result=f.engine.command(f.task.task_id,f.commit);
    assert.equal(result.operation.receipt.request_ref,'req-partial');
    assert.equal(result.operation.state,'outcome_unknown');
    f.engine.command(f.task.task_id,f.commit);assert.equal(calls,1);
});
