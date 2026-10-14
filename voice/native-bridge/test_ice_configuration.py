import unittest
from unittest.mock import patch
from aiortc import RTCPeerConnection
from native_bridge import Config, NativeCall


class IceConfigurationTests(unittest.IsolatedAsyncioTestCase):
    async def test_native_peer_gathers_public_candidate_using_fixed_stun(self):
        with patch('native_bridge.RTCPeerConnection', wraps=RTCPeerConnection) as constructor:
            call = NativeCall(Config(), None, None)
        try:
            ice_servers = constructor.call_args.args[0].iceServers
            self.assertEqual(len(ice_servers), 1)
            self.assertEqual(ice_servers[0].urls, ['stun:stun.l.google.com:19302'])
            self.assertIsNone(ice_servers[0].username)
            self.assertIsNone(ice_servers[0].credential)
        finally:
            await call.peer.close()


if __name__ == '__main__':
    unittest.main()
