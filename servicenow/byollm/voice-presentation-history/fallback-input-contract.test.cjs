'use strict';
// One offline boundary regression: no model, ServiceNow or speech call.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {test}=require('node:test');
const fixture=require('../halogen-agents-20261101/scc-rendered.fixture.json');
const source=fs.readFileSync(process.env.HALOGEN_SOURCE||path.join(__dirname,'Halogen-Request-Transformer.fallback-contract.js'),'utf8');
function transform(config){
 const input={prompt_data:JSON.parse(JSON.stringify(fixture.promptData))};
 input.prompt_data.aiConfig=config;
 const context={inputs:input,global:{LocalLLMReActExecutionLedger:function(){this.transformJSON=value=>value;}},gs:{info(){}}};
 const output=vm.runInNewContext(source,context,{timeout:1000});
 return JSON.parse(JSON.stringify(output));
}
test('SCC producer contract requires the action input object while preserving native input rules and foreign prompts',()=>{
 const own=transform('4780c7e193f747d0e7f2b9fa6aba1030');
 const content=own.body.messages[0].content;
 const rendered=content.match(/<output_structure>\s*(\{"name":"ReactEngineResponse"[\s\S]*?)\s*<\/output_structure>/);
 assert.ok(rendered,'native producer schema retained');
 const schema=JSON.parse(rendered[1]).schema;
 assert.ok(schema.properties.Action.items.required.includes('Action Inputs'),'FALLBACK must carry its mode in the required Action Inputs object');
 const inputs=fixture.promptData.prompt.slice(fixture.promptData.prompt.indexOf('<inputs>'));
 assert.equal(content.slice(content.indexOf('<inputs>')),inputs,'mission,tools,memory,datatypes and approvals remain intact');
 assert.equal(content.includes('<scc_name_confirmation_text_input_20261024>'),false,'transport no longer adds blanket name confirmation');
 assert.equal(content.includes('a supplied/corrected employee name remains unconfirmed'),false,'transport does not override current name-clarification policy');
 assert.deepEqual(own.body.response_format,fixture.responseFormat,'native transport schema is not rewritten');
 const foreign=transform('different-config');
 assert.equal(foreign.body.messages[0].content,fixture.promptData.prompt,'foreign capability prompts remain untouched');
});
