const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const original=fs.readFileSync(path.join(__dirname,'transformer-original-20261013.js'),'utf8');
const patched=fs.readFileSync(path.join(__dirname,'transformer-metadata-temporary-20261013.js'),'utf8');
function run(source,inputs,logger,expired=false){return JSON.parse(JSON.stringify(vm.runInNewContext(source,{inputs,gs:{info:logger},Date:class extends Date{getTime(){return expired?1791887387563:1791886487562;}}},{timeout:1000})));}
const secret='DO_NOT_LOG_SECRET_OR_PROMPT',agent='a4a9438393738354e7f2b9fa6aba101d',channel='a40a3a0f93fb4354e7f2b9fa6aba1001';
const input={prompt_data:{prompt:secret,model:'halogen-v2',aiConfig:'4780c7e193f747d0e7f2b9fa6aba1030',max_tokens:2048},request_data:JSON.stringify({metadata:{agent_id:agent,deploymentChannel:channel,password:secret},prompt:secret,headers:{Authorization:secret}})};
const lines=[];
assert.deepEqual(run(patched,input,x=>lines.push(x)),run(original,input,()=>{}));
assert.equal(lines.length,1);assert.equal(lines[0].includes(secret),false);assert.equal(lines[0].includes(agent),false);assert.equal(lines[0].includes(channel),false);assert.equal(lines[0].includes('password'),false);assert.equal(lines[0].includes('Authorization'),false);
const record=JSON.parse(lines[0].substring(lines[0].indexOf('{')));
assert.ok(record.rows.some(x=>x.path==='inputs.request_data.metadata.agent_id'&&x.sccAgent));
assert.ok(record.rows.some(x=>x.path==='inputs.request_data.metadata.deploymentChannel'&&x.sccChannel));
assert.deepEqual(run(patched,input,()=>{throw Error(secret)}),run(original,input,()=>{}));
const unrelated={prompt_data:{...input.prompt_data,aiConfig:'another-config'}};
assert.deepEqual(run(patched,unrelated,()=>{throw Error('unexpectedlogging')}),run(original,unrelated,()=>{}));
const expired=[];run(patched,input,x=>expired.push(x),true);assert.equal(expired.length,0);
assert.equal(original.length,1110);
console.log('PASS: unchanged output, no values or secrets logged, exact bool matches, errors contained, unrelated config unchanged, expiry enforced.');
