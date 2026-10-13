import asyncio
import json
from pathlib import Path
import shutil
import subprocess
import unittest
from aiohttp import web, CookieJar
from aiohttp.test_utils import TestServer, TestClient
from voice.bridge import Bridge, Settings


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []
        async def bot(request):
            self.assertEqual(request.headers.get('token'), 'sn-secret')
            self.requests.append(await request.json())
            return web.json_response(getattr(self, 'bot_ack', {'status': 'success'}))
        app = web.Application()
        app.router.add_post('/api/sn_va_as_service/bot/integration', bot)
        self.bot = TestServer(app)
        await self.bot.start_server()
        self.bridge = Bridge(Settings(user_id='demo', email='demo@example.test'),
                             'sn-secret', 'audio-secret', 'callback-secret')
        self.bridge.bot_url = str(self.bot.make_url('/api/sn_va_as_service/bot/integration'))
        self.ui = TestClient(TestServer(self.bridge.ui_app()), cookie_jar=CookieJar(unsafe=True))
        await self.ui.start_server()
        self.bridge.origin = str(self.ui.make_url('/')).rstrip('/')
        self.cb = TestClient(TestServer(self.bridge.callback_app()))
        await self.cb.start_server()
        result = await self.ui.get('/api/session')
        self.assertEqual(result.status, 200)
        self.session = await result.json()
        self.headers = {'X-CSRF-Token': self.session['csrf'], 'Origin': self.bridge.origin}

    async def asyncTearDown(self):
        await self.cb.close()
        await self.ui.close()
        await self.bot.close()

    async def post(self, path, data):
        return await self.ui.post(path, json=data, headers=self.headers)

    async def callback(self, **changes):
        request = self.requests[-1]
        data = {'clientSessionId': request['clientSessionId'],
                'requestId': request['requestId'], 'userId': 'demo',
                'message': {'text': 'NEVER SPEAK USER ECHO'}, 'body': []}
        data.update(changes)
        return await self.cb.post('/callback', json=data,
                                  headers={'Authorization': 'Bearer callback-secret'})

    async def test_ack_is_not_a_bot_answer_and_start_is_fixed_identity(self):
        response = await self.post('/api/start', {})
        self.assertEqual(response.status, 202)
        self.assertEqual(self.requests[0]['action'], 'START_CONVERSATION')
        self.assertEqual(self.requests[0]['appInboundId'], 'scc-local-voice')
        self.assertEqual(self.requests[0]['userId'], 'demo')
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertTrue(state['busy'])
        self.assertFalse(state['ended'])
        self.assertEqual(state['events'], [])

    async def test_initial_start_control_allows_first_user_message(self):
        await self.post('/api/start', {})
        await self.callback(body=[{'uiType': 'ActionMsg', 'actionType': 'StartConversation',
                                   'conversationId': 'conversation-id', 'messageId': 'message-id'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertFalse(state['busy'])
        self.assertTrue(state['started'])
        self.assertEqual(state['events'], [])
        self.assertEqual((await self.post('/api/message', {'text': 'Laptop bestellen'})).status, 202)

    async def test_start_control_cannot_unlock_a_regular_turn(self):
        await self.post('/api/start', {})
        await self.callback(body=[{'uiType': 'InputText'}])
        await self.post('/api/message', {'text': 'Laptop bestellen'})
        await self.callback(body=[{'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertTrue(state['busy'])

    async def test_unrelated_start_control_cannot_unlock_start(self):
        await self.post('/api/start', {})
        await self.callback(requestId='unrelated', body=[
            {'uiType': 'ActionMsg', 'actionType': 'StartConversation'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertTrue(state['busy'])

    async def test_http_200_failure_ack_does_not_accept_delivery(self):
        self.bot_ack = {'status': 'failure'}
        response = await self.post('/api/start', {})
        self.assertEqual(response.status, 502)
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertTrue(state['failed'])
        self.assertFalse(state['busy'])
        self.assertEqual(len(self.requests), 1)

    async def test_callback_output_input_and_duplicate_handling(self):
        await self.post('/api/start', {})
        body = [{'uiType': 'OutputText', 'value': 'Wie kann ich helfen?'},
                {'uiType': 'InputText', 'label': 'Ihre Antwort'}]
        self.assertEqual((await self.callback(body=body)).status, 200)
        self.assertEqual((await self.callback(body=body)).status, 200)
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertEqual(len(state['events']), 1)
        self.assertEqual(state['events'][0]['text'], 'Wie kann ich helfen?')
        self.assertFalse(state['busy'])
        self.assertFalse(state['ended'])

    async def test_choice_is_validated_and_uses_typed_false(self):
        await self.post('/api/start', {})
        await self.callback(body=[{'uiType': 'Picker', 'options': [
            {'label': 'HR', 'value': 'hr-id', 'enabled': True},
            {'label': 'Admin', 'value': 'admin', 'enabled': False}]}])
        self.assertEqual((await self.post('/api/message', {'choice': 'admin'})).status, 400)
        self.assertEqual((await self.post('/api/message', {'choice': 'hr-id'})).status, 202)
        self.assertEqual(self.requests[-1]['message']['text'], 'hr-id')
        self.assertIs(self.requests[-1]['message']['typed'], False)
        self.assertNotIn('action', self.requests[-1])
        self.assertEqual(self.requests[-1]['clientSessionId'], self.requests[0]['clientSessionId'])

    async def test_conversation_completed_is_terminal(self):
        await self.post('/api/start', {})
        await self.callback(completed=True, body=[{'uiType': 'OutputText', 'value': 'Auf Wiedersehen'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertTrue(state['ended'])
        self.assertEqual((await self.post('/api/message', {'text': 'Hallo'})).status, 409)

    async def test_callback_auth_and_separate_server(self):
        self.assertEqual((await self.cb.post('/callback', json={})).status, 401)
        self.assertEqual((await self.cb.get('/')).status, 404)
        self.assertEqual((await self.ui.post('/callback', json={})).status, 404)

    async def test_csrf_origin_host_and_limits(self):
        self.assertEqual((await self.ui.post('/api/start', json={})).status, 403)
        self.assertEqual((await self.ui.get('/api/session', headers={'Host': 'evil.test'})).status, 403)
        bad = dict(self.headers, Origin='https://evil.test')
        self.assertEqual((await self.ui.post('/api/start', json={}, headers=bad)).status, 403)
        await self.post('/api/start', {})
        self.assertEqual((await self.post('/api/message', {'text': 'race'})).status, 409)
        await self.callback(body=[{'uiType': 'InputText'}])
        self.assertEqual((await self.post('/api/message', {'text': 'x' * 4001})).status, 400)

    async def test_out_of_session_callback_is_ignored(self):
        await self.post('/api/start', {})
        await self.callback(requestId='unrelated', body=[{'uiType': 'OutputText', 'value': 'wrong'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertEqual(state['events'], [])
        self.assertTrue(state['busy'])

    async def test_audio_only_cannot_contact_servicenow(self):
        self.bridge.settings.service_now_enabled = False
        self.assertEqual((await self.post('/api/start', {})).status, 503)
        self.assertEqual(len(self.requests), 0)
        status = await (await self.ui.get('/api/session')).json()
        self.assertFalse(status['serviceNowEnabled'])

    async def test_streaming_partial_never_emitted(self):
        await self.post('/api/start', {})
        await self.callback(body=[{'uiType': 'OutputText', 'value': 'partial',
                                  'streamingStatus': 'INPROGRESS'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertEqual(state['events'], [])

    async def test_documented_stream_envelope_only_publishes_end(self):
        await self.post('/api/start', {})
        await self.callback(streamActive=True, streamState='INPROGRESS', body=[
            {'uiType': 'StreamChunk', 'streamId': 's', 'streamSequence': 2, 'value': 'partial'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertEqual(state['events'], [])
        await self.callback(streamActive=False, streamState='END', body=[
            {'uiType': 'OutputText', 'streamId': 's', 'value': 'Finale Antwort'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertEqual([e['text'] for e in state['events']], ['Finale Antwort'])
        self.assertFalse(state['busy'])
        self.assertFalse(state['ended'])

    async def test_audio_test_uses_server_secret_and_fixed_model(self):
        async def tts(request):
            self.assertEqual(request.headers['Authorization'], 'Bearer audio-secret')
            data = await request.json()
            self.assertEqual(data['model'], 'qwen3-tts-0.6b')
            self.assertEqual(data['voice'], 'ryan')
            self.assertNotIn('language', data)
            return web.Response(body=b'RIFF'+b'0'*40, content_type='audio/wav')
        app = web.Application()
        app.router.add_post('/speech', tts)
        server = TestServer(app)
        await server.start_server()
        try:
            self.bridge.tts_url = str(server.make_url('/speech'))
            response = await self.post('/api/audio-test', {'text': 'Guten Tag'})
            self.assertEqual(response.status, 200)
            self.assertTrue((await response.read()).startswith(b'RIFF'))
        finally:
            await server.close()

    async def test_configured_voice_is_sent_to_tts(self):
        received = []
        async def tts(request):
            received.append(await request.json())
            return web.Response(body=b'RIFF'+b'0'*40, content_type='audio/wav')
        app = web.Application()
        app.router.add_post('/speech', tts)
        server = TestServer(app)
        await server.start_server()
        try:
            self.bridge.settings.tts_voice = 'scc-demo'
            self.bridge.tts_url = str(server.make_url('/speech'))
            response = await self.post('/api/audio-test', {'text': 'Guten Tag'})
            self.assertEqual(response.status, 200)
            self.assertEqual(received[0]['voice'], 'scc-demo')
            self.assertEqual(received[0]['model'], 'qwen3-tts-0.6b')
        finally:
            await server.close()

    async def test_streamed_wav_is_read_to_completion(self):
        async def tts(request):
            response = web.StreamResponse(headers={'Content-Type': 'audio/wav'})
            await response.prepare(request)
            await response.write(b'RIFF')
            await asyncio.sleep(.01)
            await response.write(b'12345678')
            await response.write_eof()
            return response
        app = web.Application()
        app.router.add_post('/speech', tts)
        server = TestServer(app)
        await server.start_server()
        try:
            self.bridge.tts_url = str(server.make_url('/speech'))
            response = await self.post('/api/audio-test', {'text': 'Test'})
            self.assertEqual(await response.read(), b'RIFF12345678')
        finally:
            await server.close()

    async def test_late_previous_turn_does_not_unlock_new_request(self):
        await self.post('/api/start', {})
        old_id = self.requests[-1]['requestId']
        await self.callback(body=[{'uiType': 'InputText'}])
        await self.post('/api/message', {'text': 'Neue Frage'})
        await self.callback(requestId=old_id, body=[{'uiType': 'InputText', 'label': 'late'}])
        state = await (await self.ui.get('/api/events?wait=0')).json()
        self.assertTrue(state['busy'])

    async def test_secure_output_and_input_fail_closed_without_secret(self):
        for control in ('OutputText', 'InputText'):
            with self.subTest(control=control):
                session = next(iter(self.bridge.sessions.values()))
                session.started = session.failed = session.ended = False
                await self.post('/api/start', {})
                sentinel = 'PRIVATE-SENTINEL-DO-NOT-SPEAK'
                await self.callback(body=[{'uiType': control, 'maskType': 'SECURE',
                                          'value': sentinel, 'label': sentinel}])
                response = await self.ui.get('/api/events?wait=0')
                raw = await response.text()
                self.assertNotIn(sentinel, raw)
                self.assertTrue(json.loads(raw)['failed'])
                self.assertEqual((await self.post('/api/message', {'text': 'secret'})).status, 409)
                self.assertEqual((await self.post('/api/speak', {'eventId': session.sequence})).status, 400)

    async def test_choice_value_preserves_meaningful_whitespace(self):
        await self.post('/api/start', {})
        await self.callback(body=[{'uiType': 'Picker', 'options': [{'label': 'Opaque', 'value': ' opaque-id '}]}])
        self.assertEqual((await self.post('/api/message', {'choice': ' opaque-id '})).status, 202)
        self.assertEqual(self.requests[-1]['message']['text'], ' opaque-id ')

    async def test_fixed_identity_allows_only_one_local_session(self):
        other = TestClient(self.ui.server, cookie_jar=CookieJar(unsafe=True))
        try:
            response = await other.get('/api/session')
            self.assertEqual(response.status, 503)
        finally:
            await other._session.close()


class BrowserRaceTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node is required for client race tests')
    def test_reset_discards_old_poll_and_queued_speech(self):
        script = r'''
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) elements.set(id, {textContent:'',className:'',checked:false,value:'',children:[],
    append(...x){this.children.push(...x)},replaceChildren(){this.children=[]},pause(){},addEventListener(){},
    removeEventListener(){},load(){},removeAttribute(){},play(){return Promise.resolve()}});
  return elements.get(id);
}
let resolveOldPoll, speechCalls=0;
const context = {console,AbortController,DOMException,URL,FormData,Blob,ArrayBuffer,DataView,Float32Array,
 setTimeout,clearTimeout,performance,document:{getElementById:element,querySelectorAll:()=>[],
 createElement:()=>element(Math.random()),createTextNode:text=>text},window:{addEventListener(){}},
 fetch: async(url,options={}) => {
  if(url==='/api/session') return {ok:true,json:async()=>({csrf:'old',serviceNowEnabled:true,started:true})};
  if(url==='/api/reset') return {ok:true,json:async()=>({csrf:'new'})};
  if(url.startsWith('/api/events')) return new Promise(resolve=>{if(!resolveOldPoll)resolveOldPoll=resolve});
  if(url==='/api/speak') {speechCalls++; return {ok:true,blob:async()=>new Blob()};}
  throw Error(url);
 }};
vm.createContext(context); vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context);
const tick=()=>new Promise(resolve=>setTimeout(resolve,0));
(async()=>{
 await tick(); assert(resolveOldPoll,'old poll exists');
 vm.runInContext('speakQueue = new Promise(resolve => { globalThis.releaseSpeech = resolve; }); enqueueSpeech(1);',context);
 await element('reset').onclick();
 resolveOldPoll({ok:true,json:async()=>({events:[{id:80,kind:'bot',text:'OLD SECRET'}],cursor:80,
     busy:false,ended:false,failed:false,started:true,choices:[],inputLabel:''})});
 context.releaseSpeech(); await tick(); await tick();
 assert.equal(vm.runInContext('cursor',context),0,'old poll must not overwrite new cursor');
 assert.equal(element('chat').children.length,0,'old conversation must remain cleared');
 assert.equal(speechCalls,0,'old event ID must never reach new-session speech endpoint');
 vm.runInContext('stopped=true',context);
 console.log('client reset race: PASS');
})().catch(e=>{console.error(e);process.exit(1)});
'''
        result = subprocess.run(['node', '-e', script, str(Path(__file__).parents[1] / 'static/app.js')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
