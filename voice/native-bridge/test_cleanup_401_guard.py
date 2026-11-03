import unittest
from native_bridge import Config, Dialog


class Cleanup401Tests(unittest.IsolatedAsyncioTestCase):
    async def test_bound_caller_expired_cookie_preserves_unresolved_cleanup(self):
        dialog = Dialog(Config())
        dialog.bind_caller_authorization('Bearer synthetic.original')
        dialog.csrf = 'original-csrf'
        class Response:
            status = 401
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
        class HTTP:
            def request(self, *args, **kwargs): return Response()
            async def close(self): pass
        dialog.http = HTTP()
        await dialog.close()
        self.assertTrue(dialog.must_reset)
        self.assertEqual(dialog.csrf, 'original-csrf')
        await dialog.shutdown()
