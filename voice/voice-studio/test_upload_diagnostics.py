"""Profile-upload diagnostics must identify rejections without voice/private data."""
import base64
from datetime import timedelta
import unittest

from test_postfair import PostfairHTTPTests, AFTER


class UploadDiagnosticTests(PostfairHTTPTests):
    async def test_browser_clock_ahead_does_not_reject_new_explicit_consent(self):
        value = self.fresh()
        value['consent']['confirmed_at_utc'] = (AFTER + timedelta(hours=2)).isoformat()
        response = await self.post(value)
        self.assertEqual(response.status, 201, await response.text())
        identifier = (await response.json())['profile']['id']
        profile = self.manager.read_profile(self.config.profile_root / 'revisions' / identifier)
        self.assertEqual(profile['consent']['confirmed_at_utc'], AFTER.isoformat())

    async def test_malformed_browser_timestamp_still_rejected_without_audio(self):
        value = self.fresh()
        value['consent']['confirmed_at_utc'] = 'not-a-date'
        response = await self.post(value)
        self.assertEqual(response.status, 400)
        self.assertEqual((await response.json())['code'], 'validation_failed')
        self.assertEqual(list(self.root.rglob('*.wav')), [])

    async def test_missing_consent_logs_fixed_reason_without_private_fields(self):
        value = self.upload()
        value.update(name='NEVER_LOG_PRIVATE_NAME', wav_b64=base64.b64encode(b'NEVER_LOG_AUDIO').decode())
        with self.assertLogs('scc.voice_studio', level='INFO') as records:
            response = await self.post(value)
        self.assertEqual(response.status, 400)
        output = '\n'.join(records.output)
        self.assertIn('operation=profile_upload status=400 code=postfair_consent_required', output)
        self.assertNotIn('NEVER_LOG_PRIVATE_NAME', output)
        self.assertNotIn('NEVER_LOG_AUDIO', output)
        self.assertNotIn(value['wav_b64'], output)
        self.assertNotIn(self.headers['X-CSRF-Token'], output)

    async def test_success_logs_status_without_profile_identity(self):
        value = self.fresh()
        value['name'] = 'NEVER_LOG_SUCCESS_NAME'
        with self.assertLogs('scc.voice_studio', level='INFO') as records:
            response = await self.post(value)
        self.assertEqual(response.status, 201, await response.text())
        output = '\n'.join(records.output)
        self.assertIn('operation=profile_upload status=201 code=ok', output)
        self.assertNotIn(value['name'], output)
        self.assertNotIn((await response.json())['profile']['id'], output)


if __name__ == '__main__':
    unittest.main()
