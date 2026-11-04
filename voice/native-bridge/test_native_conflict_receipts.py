"""Negative dispatch authority requires exact echo and normal body/context close."""
import json
import unittest
from native_backend import BackendControlChanged
from native_bridge import Config, Dialog


class Content:
    def __init__(self, value):
        self.raw = json.dumps(value).encode()
    async def iter_chunked(self, size):
        yield self.raw


class Response:
    status = 409
    def __init__(self, value, fail_close=False):
        self.content, self.closed, self.fail_close = Content(value), False, fail_close
    async def __aenter__(self):
        return self
    async def __aexit__(self, *args):
        if self.fail_close:
            raise RuntimeError('Synthetic close failure')
        self.closed = True


class HTTP:
    def __init__(self, response):
        self.response, self.calls = response, 0
    def request(self, *args, **kwargs):
        self.calls += 1
        return self.response


class NativeConflictReceiptTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self, value, *, valid=False, fail_close=False):
        dialog = Dialog(Config())
        native = dict(version=1, attemptId='a'*32, ownerId=dialog.native_owner_id, binding=None)
        if valid:
            value = dict(source='servicenow_native_input_conflict', dispatch='not_started',
                attemptId=native['attemptId'], ownerId=native['ownerId'], inputControl=None)
        response = Response(value, fail_close)
        dialog.http = HTTP(response)
        error = None
        try:
            await dialog.request('POST', '/api/message', json={'text':'Offline original.', 'nativeInput':native})
        except Exception as caught:
            error = caught
        self.assertEqual(dialog.http.calls, 1)
        return error, response, dialog

    async def test_null_or_inexact_receipts_never_gain_not_started_authority(self):
        for value in (None, [], {}, {'dispatch':'not_started'},
                dict(source='servicenow_native_input_conflict', dispatch='not_started',
                     attemptId='f'*32, ownerId='f'*32, inputControl=None)):
            with self.subTest(value=value):
                error, response, _ = await self.exercise(value)
                self.assertIsInstance(error, RuntimeError)
                self.assertNotIsInstance(error, BackendControlChanged)
                self.assertIn('Unproven native input conflict', str(error))
                self.assertTrue(response.closed)

    async def test_valid_receipt_only_acquires_authority_after_normal_close(self):
        error, response, dialog = await self.exercise(None, valid=True)
        self.assertIsInstance(error, BackendControlChanged)
        self.assertTrue(response.closed)
        self.assertTrue(error.body_closed)
        self.assertIs(error.owner, dialog.backend_owner)
        error, response, _ = await self.exercise(None, valid=True, fail_close=True)
        self.assertNotIsInstance(error, BackendControlChanged)
        self.assertFalse(response.closed)


if __name__ == '__main__':
    unittest.main()
