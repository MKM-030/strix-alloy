"""Fresh post-fair consent must not reopen expired fair recordings."""
from datetime import datetime, timezone
import hashlib
import json
import unittest
from unittest.mock import patch
from aiohttp import CookieJar
from aiohttp.test_utils import TestClient, TestServer
import test_studio_server as fixture

DUE = datetime(2026,10,16,6,tzinfo=timezone.utc)
AFTER = datetime(2026,10,16,7,tzinfo=timezone.utc)
NOTICE = 'Neue Aufnahmen bleiben gespeichert, bis Sie oder ein Administrator sie löschen.'
HELPER_HASH = '06a34af5d3cebddb4458bfe91a2f5720f39588e05f848a621a5a09d7592767c1'

def seal(runtime):
    runtime.mkdir(parents=True, exist_ok=True)
    receipt = json.dumps({'schema_version':1,'status':'purged','due_at_utc':'2026-10-16T06:00:00Z',
        'attempted_at_utc':'2026-10-16T06:24:00+00:00','profiles':0,'quarantine':0,
        'upload_directories':0,'staging_directories':0,'preview_files':0,'preview_aliases':0}).encode()
    (runtime / 'fair-campaign-cleanup-result.json').write_bytes(receipt)
    marker = {'schema_version':1,'campaign':'scc-2026','due_at_utc':'2026-10-16T06:00:00Z',
        'completed_at_utc':'2026-10-16T06:25:00+00:00','cleanup_helper_sha256':HELPER_HASH,
        'cleanup_result_sha256':hashlib.sha256(receipt).hexdigest(),
        'verified':{'remaining_fair_profiles':0,'selected_profile_id':'synthetic-scc-demo','native_sessions':0},
        'postfair_enabled':True}
    (runtime / 'fair-campaign-completed.json').write_text(json.dumps(marker))

class PostfairHTTPTests(unittest.IsolatedAsyncioTestCase):
    login=fixture.VoiceStudioHTTPTests.login
    upload=fixture.VoiceStudioHTTPTests.upload
    activate=fixture.VoiceStudioHTTPTests.activate
    async def asyncSetUp(self):
        await fixture.VoiceStudioHTTPTests.asyncSetUp(self)
        seal(self.config.runtime)
        self.now=AFTER
        clock=patch.object(self.manager,'utc_now',return_value=AFTER.isoformat())
        clock.start();self.addCleanup(clock.stop)
        async def idle(): return self.live_sessions
        def register(profile): self.registered.append(profile['profile_id']); return {'status':200}
        app=self.server.create_app(self.config,manager=self.manager,idle_check=idle,register=register,now=lambda:self.now)
        self.client=TestClient(TestServer(app),cookie_jar=CookieJar(unsafe=True))
        await self.client.start_server();self.addAsyncCleanup(self.client.close)
        await self.login()
    def fresh(self):
        value=self.upload()
        value['consent'].update(confirmed_at_utc=AFTER.isoformat(),retention='until_deleted',retention_notice=NOTICE)
        return value
    async def post(self,value): return await self.client.post('/api/profiles',json=value,headers=self.headers)
    async def test_sealed_completed_campaign_allows_fresh_recording(self):
        session=await (await self.client.get('/api/session',headers=self.headers)).json()
        self.assertTrue(session['recording_allowed'])
        self.assertTrue(session['postfair_mode'])
        self.assertEqual(session['retention_notice'],NOTICE)
        response=await self.post(self.fresh());self.assertEqual(response.status,201,await response.text())
        profile=(await response.json())['profile']
        self.assertTrue(profile['can_activate'])
        self.assertEqual((await self.activate(profile)).status,200)
        self.assertEqual(self.registered,[profile['id']])
    async def test_original_fair_consent_is_not_reused_after_expiry(self):
        response=await self.post(self.upload());self.assertEqual(response.status,400)
        self.assertEqual((await response.json())['code'],'postfair_consent_required')
        self.assertEqual(list(self.root.rglob('*.wav')),[])
    async def test_missing_or_modified_marker_keeps_recording_closed(self):
        path=self.config.runtime/'fair-campaign-completed.json'
        path.unlink()
        response=await self.post(self.fresh());self.assertEqual(response.status,409)
        self.assertEqual(list(self.root.rglob('*.wav')),[])
    async def test_receipt_tamper_fails_closed(self):
        (self.config.runtime/'fair-campaign-cleanup-result.json').write_text('{}')
        response=await self.post(self.fresh());self.assertEqual(response.status,409)
    async def test_old_profile_cannot_be_reactivated_with_new_campaign(self):
        value=self.upload();value['wav_path']=str(self.root/'source.wav')
        (self.root/'source.wav').write_bytes(fixture.wav_bytes())
        with patch.object(self.manager,'utc_now',return_value='2026-10-13T20:00:00Z'):
            profile=self.manager.stage(value,self.config.profile_root)
        response=await self.activate({'id':profile['profile_id']})
        self.assertEqual(response.status,409);self.assertEqual(self.registered,[])
    async def test_expired_profile_preview_rejected_before_native_tts(self):
        value=self.upload();value['wav_path']=str(self.root/'source.wav')
        (self.root/'source.wav').write_bytes(fixture.wav_bytes())
        with patch.object(self.manager,'utc_now',return_value='2026-10-13T20:00:00Z'):
            profile=self.manager.stage(value,self.config.profile_root)
        with patch.object(self.server,'native_profile_preview',return_value=b'\x00\x00'*24000) as preview:
            response=await self.client.post('/api/profiles/'+profile['profile_id']+'/preview',
                json={'text':'Eine neue Vorschau.'},headers=self.headers)
        self.assertEqual(response.status,409)
        preview.assert_not_called()

    async def test_seal_removed_during_staging_never_publishes_revision(self):
        original=self.manager.stage
        def crossing(*args,**kwargs):
            result=original(*args,**kwargs)
            (self.config.runtime/'fair-campaign-completed.json').unlink()
            return result
        with patch.object(self.manager,'stage',side_effect=crossing): response=await self.post(self.fresh())
        self.assertEqual(response.status,409)
        self.assertEqual(list((self.config.profile_root/'revisions').glob('*')),[])

class StartupCompletionTests(unittest.TestCase):
    def test_sealed_campaign_never_reinvokes_cleanup_or_tts(self):
        import tempfile
        from pathlib import Path
        import launch_studio
        with tempfile.TemporaryDirectory() as folder:
            runtime=Path(folder);seal(runtime)
            with patch.object(launch_studio,'RUNTIME',runtime), patch.object(launch_studio.subprocess,'run') as run:
                result=launch_studio.retention_catchup()
            self.assertEqual(result['status'],'completed')
            run.assert_not_called()
if __name__=='__main__': unittest.main()
