'use strict';
// Cross-language boundary fixture: emit real controller.status() responses.
// Only persistence, platform authorization and clock are synthetic.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const rows={task:[],transition:[],event:[]};let sequence=0;
const repo={id:()=> 'fixture-'+(++sequence),now:()=>1000,
    hash:value=>crypto.createHash('sha256').update(value).digest('hex'),
    get:(table,field,value)=>rows[table].find(row=>row[field]===value)||null,
    insert:(table,row)=>{rows[table].push(row);return row;}};
const policy={authorize:()=>({principal:'fixture-user',service:'fixture-service',agent:'fixture-agent',
    tool:'fixture-tool',registry_revision:'fixture-registry',expires_at:100000,execute:true,write:false})};
const env={Class:{create:()=>function(){this.initialize.apply(this,arguments);}}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'LocalLLMVoiceTaskControl.js'),'utf8'),env);
const control=new env.LocalLLMVoiceTaskControl(repo,policy,{submit:()=>{throw Error('no business calls');}});
const task=control.create({command_id:'fixture-create',objective:'Laptop',context_version:1});
let revision='root';const statuses=[];
for(const [index,operation] of input.operations.entries()) {
    revision=control.command(task.task_id,{command_id:operation.operation_id,context_version:operation.context_version,
        kind:index?'amend':'prepare',expected_revision:revision,
        proposal:{employee_name:'A',start_date:'2026-12-01',delivery_location:'B',manager_name:'C'}}).revision;
    statuses.push(control.status(task.task_id));
}
process.stdout.write(JSON.stringify(statuses));
