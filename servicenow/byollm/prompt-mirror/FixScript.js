/* Run as an administrator. No skill/capability is created or activated.
 * Keep APPLY=false to inspect the complete per-variant permission/closure plan.
 * CAPABILITY_IDS=[] selects every qualified installed Now LLM Generic capability.
 * To select skills, enter their sys_one_extend_capability sys_ids in the array.
 * Source-instance skill IDs and model names are deliberately not seeded here.
 */
(function () {
    var APPLY = false;
    var CAPABILITY_IDS = [];
    var result = new global.CustomLLMPromptMirror().run({capabilityIds: CAPABILITY_IDS, apply: APPLY});
    gs.print('CUSTOM_LLM_PROMPT_MIRROR ' + JSON.stringify(result));
})();
