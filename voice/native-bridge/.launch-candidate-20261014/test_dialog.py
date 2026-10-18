import unittest
from native_bridge import Config, Dialog


class DialogTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_reset_does_not_resume_previous_conversation(self):
        class FailedResetDialog(Dialog):
            def __init__(self):
                super().__init__(Config())
                self.http = object()
                self.csrf = 'owned-session-token'
                self.paths = []
            async def request(self, method, path, **kwargs):
                self.paths.append(path)
                if path == '/api/end':
                    raise RuntimeError('transport down')
                return {'csrf':'old','started':True,'serviceNowEnabled':True,
                        'cursor':0,'events':[],'busy':False}
        dialog = FailedResetDialog()
        with self.assertLogs('native-voice', level='WARNING'):
            await dialog.close()
        with self.assertRaises(RuntimeError):
            await dialog.open()
        self.assertNotIn('/api/session', dialog.paths)


if __name__ == '__main__':
    unittest.main()
