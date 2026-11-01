'use strict';
// OFFLINE ONLY. New transport representation of the immutable approved 6ec
// script. It neither contacts ServiceNow nor changes its execution body/plan.
const fs=require('node:fs');
const path=require('node:path');
const crypto=require('node:crypto');
const vm=require('node:vm');
const sha=s=>crypto.createHash('sha256').update(s).digest('hex');
const need=(ok,message)=>{if(!ok)throw Error(message);};
const SCRIPT_SHA='6ec46a1827df35ff6e4deb6c2ccf961a70dfc8b969aafefb681debeabb1fe3b1';
const PLAN_SHA='ff7c31b07645bd4438becde3b5595b37074c56d6f397cdf638676305341abcd8';
const TEMPLATE_SHA='dbfd79b552c9737aec1b7aea2ce336d01a7df554a0a06968ddf3039e83f53e0b';
const MIN_MATCH=14,MAX_MATCH=65535,CANDIDATES=128;
// Static literal strings and [back-distance, length] substitutions. A reference
// never overlaps its destination. Positions/lengths count UTF-16 code units.
function encode(text){
  need(typeof text==='string','compact_input_must_be_string');
  const chains=new Map(),tokens=[];let i=0,literal='';
  const remember=position=>{if(position+4>text.length)return;const key=text.slice(position,position+4);let chain=chains.get(key);if(!chain){chain=[];chains.set(key,chain);}chain.push(position);if(chain.length>CANDIDATES)chain.shift();};
  while(i<text.length){
    let best=0,bestPosition=0;const chain=chains.get(text.slice(i,i+4))||[];
    for(let c=chain.length-1;c>=0;c--){const position=chain[c],maximum=Math.min(MAX_MATCH,i-position,text.length-i);if(maximum<MIN_MATCH||maximum<=best)continue;let n=4;while(n<maximum&&text.charCodeAt(position+n)===text.charCodeAt(i+n))n++;if(n>best){best=n;bestPosition=position;if(best===MAX_MATCH)break;}}
    if(best>=MIN_MATCH){if(literal){tokens.push(literal);literal='';}tokens.push([i-bestPosition,best]);for(let n=0;n<best;n++)remember(i+n);i+=best;}
    else{literal+=text.charAt(i);remember(i);i++;}
  }
  if(literal)tokens.push(literal);
  return tokens;
}
// This function is copied verbatim into the PLAN expression. Keep ES5 syntax.
// Completed 8KiB chunks stay immutable; references read only earlier text.
// It never slices or repeatedly concatenates the whole expanded JSON string.
function expand(tokens, expected) {
    var chunks = [], tail = '', total = 0, blockSize = 8192, i, token, distance, length;
    function valid(ok) { if (!ok) throw new Error('compact_plan_data_invalid'); }
    function integer(n) { return typeof n === 'number' && isFinite(n) && Math.floor(n) === n; }
    function append(piece) {
        valid(total + piece.length <= expected);
        while (piece.length) {
            var n = Math.min(blockSize - tail.length,piece.length);
            tail += piece.substring(0,n); piece = piece.substring(n); total += n;
            if (tail.length === blockSize) { chunks.push(tail); tail = ''; }
        }
    }
    function previous(start, count) {
        var parts = [], index, offset, chunk, n;
        while (count) {
            index = Math.floor(start / blockSize); offset = start % blockSize;
            chunk = index < chunks.length ? chunks[index] : tail;
            n = Math.min(count,chunk.length - offset); valid(n > 0);
            parts.push(chunk.substring(offset,offset + n)); start += n; count -= n;
        }
        return parts.join('');
    }
    valid(integer(expected) && expected >= 0 && expected <= 8000000 && Array.isArray(tokens) && tokens.length <= expected + 1);
    for (i = 0; i < tokens.length; i++) {
        token = tokens[i];
        if (typeof token === 'string') { valid(token.length > 0); append(token); }
        else {
            valid(Array.isArray(token) && token.length === 2); distance = token[0]; length = token[1];
            valid(integer(distance) && integer(length) && distance > 0 && distance <= total && length >= 14 && length <= 65535 && length <= distance && total + length <= expected);
            append(previous(total - distance,length));
        }
    }
    valid(total === expected); chunks.push(tail); return chunks.join('');
}
const literal=x=>JSON.stringify(x).replace(/\u2028/g,'\\u2028').replace(/\u2029/g,'\\u2029');
function expressionForText(text,tokens=encode(text)){
  need(expand(tokens,text.length)===text,'compact_roundtrip_text_mismatch');
  return 'JSON.parse(('+expand.toString()+')('+literal(tokens)+','+text.length+'))';
}
function loadFrozen(directory,candidateDirectory=__dirname){
  const scriptBytes=fs.readFileSync(path.join(directory,'complete-halogen-agent-configuration.js'));
  const planBytes=fs.readFileSync(path.join(directory,'frozen-plan.completion.private.json'));
  const templateBytes=fs.readFileSync(path.join(candidateDirectory,'complete-halogen-agent-configuration.template.js'));
  need(sha(scriptBytes)===SCRIPT_SHA,'immutable_6ec_script_hash_changed');
  need(sha(planBytes)===PLAN_SHA,'immutable_completion_plan_hash_changed');
  need(sha(templateBytes)===TEMPLATE_SHA,'immutable_completion_template_hash_changed');
  const script=scriptBytes.toString('utf8'),plan=JSON.parse(planBytes.toString('utf8')),text=JSON.stringify(plan),assignment='    var PLAN = ',start=script.indexOf(assignment)+assignment.length;
  need(start>=assignment.length&&script.indexOf(assignment,start)===-1,'immutable_plan_assignment_not_unique');
  need(script.slice(start,start+text.length)===text&&script.slice(start+text.length,start+text.length+1)===';','immutable_plan_assignment_text_mismatch');
  const prefix=script.slice(0,start),suffix=script.slice(start+text.length);
  need(templateBytes.toString('utf8').replace('/*__COMPLETION_PLAN__*/',text)===script,'immutable_template_render_mismatch');
  return {plan,text,prefix,suffix,script};
}
function renderText(text,frozen){return frozen.prefix+expressionForText(text)+frozen.suffix;}
function prepare(directory,candidateDirectory=__dirname){
  const frozen=loadFrozen(directory,candidateDirectory),tokens=encode(frozen.text),expression=expressionForText(frozen.text,tokens),script=frozen.prefix+expression+frozen.suffix;
  const sandbox={};vm.runInNewContext('decoded = '+expression,sandbox,{timeout:10000});
  need(JSON.stringify(sandbox.decoded)===frozen.text,'compact_vm_decoded_plan_mismatch');
  need(script.slice(0,frozen.prefix.length)===frozen.prefix&&script.slice(-frozen.suffix.length)===frozen.suffix,'compact_execution_prefix_or_suffix_changed');
  new vm.Script(script);
  const review={offline_only:true,instance_executed:false,requires_separate_user_approval:true,script:'complete-halogen-agent-configuration.compact.js',script_sha256:sha(script),script_bytes:Buffer.byteLength(script),script_form_encoded_bytes:Buffer.byteLength(new URLSearchParams({script}).toString()),approved_6ec_script_sha256:SCRIPT_SHA,frozen_plan_file_sha256:PLAN_SHA,frozen_template_sha256:TEMPLATE_SHA,expanded_json_sha256:sha(frozen.text),expanded_json_utf16_units:frozen.text.length,expanded_json_utf8_bytes:Buffer.byteLength(frozen.text),execution_prefix_sha256:sha(frozen.prefix),execution_suffix_sha256:sha(frozen.suffix),literal_reference_tokens:tokens.length,encoded_token_json_bytes:Buffer.byteLength(literal(tokens)),exact_expanded_json_text:true,exact_execution_prefix_suffix:true,codec:'Static string literals or [prior-distance,length] references over exact JSON text; bounded ES5 decoder with immutable completed8KiB chunks; JSON.parse once. All text, guards, identities, payloads and revisions retained. No eval, generated-code evaluation, Java, gzip, runtime network, hashing/truncation of guard text, or dynamic object-key assignment.',execution_authority:'Unchanged approved6ec execution body and frozen plan; compact transport script has a NEW hash and requires separate review/approval. The prior response failure did not authorize retry.',limitation:'The actual instance request-size limit and the cause of the prior empty response remain unconfirmed. Offline size reduction is not evidence of instance execution or success.'};
  need(review.script_form_encoded_bytes<900000,'compact_form_size_target_not_met');
  return {plan:frozen.plan,text:frozen.text,tokens,expression,script,review,frozen};
}
function writeVariant(directory,candidateDirectory=__dirname){
  const p=prepare(directory,candidateDirectory),outputs=[[p.review.script,p.script],['deployment-review.completion.compact.json',JSON.stringify(p.review,null,2)+'\n']];
  for(const [name]of outputs)need(!fs.existsSync(path.join(directory,name)),'compact_output_already_exists:'+name);
  for(const [name,value]of outputs)fs.writeFileSync(path.join(directory,name),value,{encoding:'utf8',flag:'wx'});
  return p.review;
}
if(require.main===module)console.log(JSON.stringify(writeVariant(path.resolve(__dirname,'../../../server/.local/voice-goal-halogen-agents-20261101')),null,2));
module.exports={encode,expand,expressionForText,loadFrozen,renderText,prepare,writeVariant,SCRIPT_SHA,PLAN_SHA,TEMPLATE_SHA};
