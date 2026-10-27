"""Real NativeCall over SDK HTTP + local ICE, with generated audio only.

No platform, microphone, model, ASR or TTS service requests are performed.
"""
import asyncio
import array
import json
import math
import unittest
from unittest.mock import patch
from aiohttp.test_utils import TestClient, TestServer
from aiortc import AudioStreamTrack, RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from native_bridge import Config, create_app
from sdk_admission import _VerifiedSettingsContext
from assistant_settings import CallSettings
from test_assistant_settings import authorized_settings
from sdk_sessions import _sdk_answer_compatible

GREETING = 'Guten Tag. Dies ist die Sprachprobe.'


class _Dialog:
    metadata = {'conversation_id':'', 'interaction_id':''}
    async def open(self):
        return []
    def record_greeting(self, text):
        pass
    async def turn(self, text, on_reply=None):
        raise AssertionError('No real utterance is submitted by this test')
    async def close(self):
        pass


class _Speech:
    async def synthesize(self, text):
        if text != GREETING:
            raise AssertionError('Unexpected test greeting')
        tone = array.array('h', (int(8000*math.sin(2*math.pi*440*n/24000)) for n in range(12000)))
        for n in range(0,len(tone),2400):
            yield tone[n:n+2400].tobytes()
    async def transcribe(self, pcm):
        raise AssertionError('Generated silence must not invoke ASR')


class SDKNativeAudioTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_call_negotiates_sdk_audio_and_delivers_german_transcript(self):
        config = Config(instance_name='soprasteriaassvsdemo14', auth_mode='servicenow',
            sdk_public_origin='https://strix-alloy.tail7f425a.ts.net',
            voice_service_id='8aa131d793f787105c8132d47aba1095',
            required_agent_id='a6337ddf93f787105c8132d47aba1058',
            native_sdk_enabled=True, greeting=GREETING, max_call_seconds=30)
        payload = authorized_settings()
        payload['result']['authorized_agents'] = [config.required_agent_id]
        projection = payload['result']['assistant_settings']
        projection['service_id'] = config.voice_service_id
        projection['prompt']['introduction'] = GREETING
        projection['language_selection']['enabled'] = False
        settings = CallSettings.from_authorized_response(payload,config.voice_service_id,
                                                          config.required_agent_id)
        async def granted(*args, **kwargs):
            self.assertEqual(kwargs['assistant_settings_version'],1)
            return _VerifiedSettingsContext(config.instance_url,config.voice_service_id,
                config.required_agent_id,'agent_operator',True,settings)
        peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        messages = asyncio.Queue()
        tracks = asyncio.Queue()
        channel = peer.createDataChannel('transcripts',ordered=True)
        channel.on('message', lambda value: messages.put_nowait(json.loads(value)))
        peer.on('track', lambda track: tracks.put_nowait(track))
        peer.addTrack(AudioStreamTrack())
        # Only the test substitutes host ICE. Deployed NativeCall keeps STUN.
        with patch('sdk_admission.admit_sdk_session',side_effect=granted), \
                patch('native_bridge.RTCConfiguration',side_effect=lambda **kw: RTCConfiguration(iceServers=[])):
            client = TestClient(TestServer(create_app(config,
                speech_factory=lambda http: _Speech(), dialog_factory=_Dialog)))
            await client.start_server()
            try:
                headers = {'Authorization':'Bearer sdk-audio-fixture'}
                response = await client.post('/api/webrtc/sessions?instance_name=soprasteriaassvsdemo14&receive_data=true&voice_service_id='+config.voice_service_id,
                    headers=headers,json={'agent_id':'agent_operator'})
                self.assertEqual(response.status, 200)
                session = await response.json()
                endpoint = '/api/webrtc/sessions/'+session['session_id']
                await peer.setLocalDescription(await peer.createOffer())
                response = await client.post(endpoint+'/offer',headers=headers,
                    json={'type':'offer','sdp':peer.localDescription.sdp})
                self.assertEqual(response.status,200)
                answer = (await response.json())['sdp']
                self.assertTrue(_sdk_answer_compatible(answer['sdp']))
                await peer.setRemoteDescription(RTCSessionDescription(answer['sdp'],'answer'))
                transcript = await asyncio.wait_for(messages.get(),10)
                self.assertEqual(transcript['type'],'transcript')
                self.assertEqual(transcript['data']['role'],'assistant')
                self.assertEqual(transcript['data']['content'],GREETING)
                remote_audio = await asyncio.wait_for(tracks.get(),10)
                heard_tone = False
                async with asyncio.timeout(5):
                    for _ in range(80):
                        frame = await remote_audio.recv()
                        samples = frame.to_ndarray()
                        threshold = .01 if frame.format.name in ('flt','fltp','dbl','dblp') else 100
                        if samples.max() > threshold or samples.min() < -threshold:
                            heard_tone = True
                            break
                self.assertTrue(heard_tone,'Generated TTS PCM must reach the SDK peer')
                response = await client.get(endpoint+'/candidates',headers=headers)
                self.assertEqual(await response.json(),{'candidates':[]})
                response = await client.delete(endpoint,headers=headers)
                self.assertIn(response.status,(202,204))
                for _ in range(30):
                    if (await (await client.get('/health')).json())['nativeSessions']==0:
                        break
                    await asyncio.sleep(.05)
                self.assertEqual((await (await client.get('/health')).json())['nativeSessions'],0)
            finally:
                await peer.close()
                await client.close()


if __name__=='__main__':
    unittest.main()
