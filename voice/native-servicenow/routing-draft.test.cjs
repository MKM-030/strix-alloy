const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const test = require('node:test');
const path = require('node:path');
const target = process.argv[2] || 'Fetch-voice-assistant-details.draft.js';
const source = fs.readFileSync(path.join(__dirname, target), 'utf8');
const demo = '11111111111111111111111111111111';
const native = 'https://native.example.com';
const adapter = 'https://strix-alloy.tail7f425a.ts.net/scc-native';
const prefix = 'sn_nowassist_va.scc_native_voice.';
function run(properties = {}, assistant = demo, admin = true) {
  const context = {
    gs: {
      nil: value => !value,
      getProperty: (key, fallback) => key === 'glide.servlet.uri' ? 'https://demo.service-now.com/' : properties[key] ?? fallback,
      hasRole: role => admin && role === 'admin',
      error() {}, getMessage: text => text
    },
    sn_nowassist_va: { NowAssistVoiceTestingUtil: function () { this.getOrchestratorBaseUrl = () => native; } },
    sn_voice_aia: { VoiceAgentConstants: { TABLES: {} } },
    global: { NowAssistDeployment: { getBySysId: () => ({name:'Demo',deploymentConfigList:[{attributeNameValueMap:{language:'en'},contextProfile:{sysId:'profile'}}]}) } },
    GlideRecord: function () { for (const method of ['addQuery','addActiveQuery','addNotNullQuery','orderBy','query','setLimit']) this[method] = () => {}; this.next = () => false; }
  };
  vm.createContext(context);
  vm.runInContext(source, context);
  return context.transform({voiceAssistantSysId:assistant}).orchestratorUrl;
}
const enabled = { [prefix+'enabled']:'true', [prefix+'assistant_id']:demo, [prefix+'orchestrator_url']:adapter };
test('default keeps native routing', () => assert.equal(run(), native));
test('explicit enabled dedicated assistant routes to adapter', () => assert.equal(run(enabled), adapter));
test('other assistants keep native routing', () => assert.equal(run(enabled, '22222222222222222222222222222222'), native));
test('non-admin test cannot route token to adapter', () => assert.equal(run(enabled, demo, false), native));
test('unapproved endpoints keep native routing', () => {
  for (const url of ['http://strix-alloy.tail7f425a.ts.net/scc-native','https://user:pass@strix-alloy.tail7f425a.ts.net/scc-native','https://adapter.example.com/path',adapter+'/wrong',adapter+'?x=1',adapter+'#fragment']) {
    assert.equal(run({...enabled,[prefix+'orchestrator_url']:url}),native,url);
  }
});
test('optional trailing slash is stripped for native path joining', () => assert.equal(run({...enabled,[prefix+'orchestrator_url']:adapter+'/'}),adapter));
