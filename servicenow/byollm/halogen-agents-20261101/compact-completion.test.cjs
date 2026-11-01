'use strict';
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const crypto=require('node:crypto');
const {createRequire}=require('node:module');
const compact=require('./build-compact-completion.cjs');
const directory=path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101');
const sha=x=>crypto.createHash('sha256').update(x).digest('hex');
const prepared=compact.prepare(directory);

test('compact representation exactly reconstructs immutable frozen JSON text, plan, and approved execution prefix/suffix',()=>{
  const p=prepared,decoded=compact.expand(p.tokens,p.text.length);
  assert.equal(decoded,p.frozen.text);assert.equal(sha(decoded),p.review.expanded_json_sha256);
  const sandbox={};vm.runInNewContext('decoded = '+p.expression,sandbox,{timeout:10000});
  assert.equal(JSON.stringify(sandbox.decoded),p.text);
  assert.equal(p.script.slice(0,p.frozen.prefix.length),p.frozen.prefix);
  assert.equal(p.script.slice(-p.frozen.suffix.length),p.frozen.suffix);
  assert.equal(p.frozen.prefix+p.text+p.frozen.suffix,p.frozen.script);
  assert.equal(sha(p.frozen.script),compact.SCRIPT_SHA);
  assert.equal(p.plan.targets.length,68);assert.equal(p.plan.guards.length,21);assert.equal(p.plan.companions.length,2);assert.equal(p.plan.headers.length,3);assert.equal(p.plan.cus.length,68);
  new vm.Script(p.script);
});
test('compact form is below the actually successful prior full-form size without omitting frozen text',()=>{
  assert.equal(prepared.review.script_form_encoded_bytes,Buffer.byteLength(new URLSearchParams({script:prepared.script}).toString()));
  const conservativeFullForm=prepared.review.script_form_encoded_bytes+1024;
  assert.ok(conservativeFullForm<900000);assert.ok(conservativeFullForm<1009379);
  assert.equal(prepared.text.length,2365222);assert.equal(Buffer.byteLength(prepared.text),2368084);
});
test('preparation leaves approved frozen inputs byte-identical and reports a separate approval requirement',()=>{
  const files=['complete-halogen-agent-configuration.js','frozen-plan.completion.private.json','deployment-review.completion.json'];
  const before=files.map(f=>sha(fs.readFileSync(path.join(directory,f))));
  const again=compact.prepare(directory);assert.deepEqual(files.map(f=>sha(fs.readFileSync(path.join(directory,f)))),before);
  assert.equal(again.script,prepared.script);assert.equal(again.review.requires_separate_user_approval,true);assert.equal(again.review.instance_executed,false);assert.notEqual(again.review.script_sha256,compact.SCRIPT_SHA);
});
test('literal token text cannot collide with reference tokens or object keys',()=>{
  const text=JSON.stringify({tokens:['[100,14]','literal [0,14]','__proto__','constructor','prototype'],object:JSON.parse('{"__proto__":{"polluted":true}}')});
  const expression=compact.expressionForText(text),context={};vm.runInNewContext('decoded = '+expression,context);
  assert.equal(JSON.stringify(context.decoded),text);assert.equal({}.polluted,undefined);assert.equal(vm.runInNewContext('({}).polluted',context),undefined);
  assert.ok(Object.hasOwn(context.decoded.object,'__proto__'));
});
test('Unicode, lone surrogates, CRLF, XML strings and JavaScript line separators roundtrip by UTF16 units',()=>{
  const value='A'.repeat(8191)+'🚀'+'\r\n<![CDATA[<script>\u2028\u2029\ud800\udfff'+('literal text\r\n'.repeat(1200));
  const text=JSON.stringify({value,again:value}),tokens=compact.encode(text),expression=compact.expressionForText(text,tokens);
  assert.equal(compact.expand(tokens,text.length),text);
  assert.ok(!expression.includes('\u2028')&&!expression.includes('\u2029'),'ES5 literal line separators must be escaped');
  const context={};vm.runInNewContext('decoded = '+expression,context);assert.equal(JSON.stringify(context.decoded),text);assert.equal(context.decoded.value,value);
});
test('references can cross completed8KiB chunks and a surrogate boundary without overlapping destination',()=>{
  const seed='A'.repeat(8191)+'🚀'+'B'.repeat(24),copied=seed.slice(8191),text=seed+copied;
  assert.equal(compact.expand([seed,[copied.length,copied.length]],text.length),text);
  const longSeed='abc123'.repeat(6000),copy=longSeed.slice(5000,30000),longText=longSeed+copy;
  assert.equal(compact.expand([longSeed,[longSeed.length-5000,copy.length]],longText.length),longText);
});
test('empty input and exact final chunk boundary are lossless',()=>{
  assert.equal(compact.expand([],0),'');
  const text='abcdef1234567890'.repeat(1024);assert.equal(compact.expand(compact.encode(text),text.length),text);
});
test('malformed, corrupted, overlapping, future and oversized references are rejected',()=>{
  const prefix='abcdefghijklmnop';
  const cases=[[[[1,14]],14],[[prefix,[17,14]],30],[[prefix,[1,14]],30],[[prefix,[0,14]],30],[[prefix,[-1,14]],30],[[prefix,[16,0]],16],[[prefix,[16,13]],29],[[prefix,[16,65536]],65552],[[prefix,[16.5,14]],30],[[prefix,[16,14.5]],30],[[prefix,[Infinity,14]],30],[[prefix,[16,NaN]],30],[[prefix,[16,14,0]],30],[[prefix,{distance:16,length:14}],30],[[prefix,null],30],[[prefix,16],30],[[prefix,['16',14]],30],[[prefix,[16,'14']],30],[[prefix,[]],30]];
  for(const [tokens,expected]of cases)assert.throws(()=>compact.expand(tokens,expected),/compact_plan_data_invalid/);
});
test('truncated and overflowing token streams and invalid immutable output lengths are rejected',()=>{
  const tokens=compact.encode(prepared.text);
  assert.throws(()=>compact.expand(tokens.slice(0,-1),prepared.text.length),/compact_plan_data_invalid/);
  assert.throws(()=>compact.expand(tokens,prepared.text.length-1),/compact_plan_data_invalid/);
  assert.throws(()=>compact.expand([...tokens,'x'],prepared.text.length),/compact_plan_data_invalid/);
  for(const expected of [-1,1.5,NaN,Infinity,8000001,'0'])assert.throws(()=>compact.expand([],expected),/compact_plan_data_invalid/);
  assert.throws(()=>compact.expand({},0),/compact_plan_data_invalid/);assert.throws(()=>compact.expand([''],0),/compact_plan_data_invalid/);
});
test('runtime decoder is ES5-only static string substitution without external or executable-code APIs',()=>{
  const decoder=compact.expand.toString();
  assert.doesNotMatch(decoder,/\b(?:eval|Function|Java|require|fetch|GlideRecord|GlideRecordSecure|gs|setPrototypeOf|defineProperty)\b/);
  assert.doesNotMatch(decoder,/=>|\b(?:let|const|class)\b|`/);
  assert.doesNotMatch(decoder,/\[[^\]]+\]\s*=/,'decoder must not assign arbitrary object keys');
  const sandbox={};vm.runInNewContext('value = ('+decoder+')(["abcdefghijklmnop",[16,14]],30)',sandbox);assert.equal(sandbox.value,'abcdefghijklmnopabcdefghijklmn');
});

// Run all22 unchanged frozen native-boundary tests through the new renderer.
// Only their template read is substituted in memory; no existing file is edited.
// Tests still retain their original fault injection and assertions verbatim.
const originalTestPath=path.join(__dirname,'completion.test.cjs');
const originalTests=fs.readFileSync(originalTestPath,'utf8');
const originalTemplatePath=path.join(__dirname,'complete-halogen-agent-configuration.template.js');
const realRequire=createRequire(originalTestPath),cached=new Map([[prepared.text,prepared.script]]);
const interceptedFS=Object.create(fs);
interceptedFS.readFileSync=(file,...args)=>{
  if(path.resolve(String(file))===originalTemplatePath)return {replace(marker,text){assert.equal(marker,'/*__COMPLETION_PLAN__*/');if(!cached.has(text))cached.set(text,compact.renderText(text,prepared.frozen));return cached.get(text);}};
  return fs.readFileSync(file,...args);
};
function parityRequire(name){
  if(name==='node:fs')return interceptedFS;
  if(name==='node:test')return {test:(name,...args)=>test('compact parity: '+name,...args)};
  return realRequire(name);
}
vm.runInNewContext(originalTests,{require:parityRequire,__dirname,Buffer,process},{filename:originalTestPath+'.compact-parity',timeout:10000});
