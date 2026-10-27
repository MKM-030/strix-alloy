import unittest
from array import array
try:
    from core import EndpointGate, PlaybackBuffer, local_auth, authorized_agents
except ImportError:
    EndpointGate = PlaybackBuffer = local_auth = authorized_agents = None


class SafetyTests(unittest.TestCase):
    def test_short_spoken_confirmation_is_not_discarded(self):
        for frames in (8, 10, 11):
            gate = EndpointGate(threshold=300)
            speech = array('h', [3000]*320).tobytes()
            result = [gate.feed(speech) for _ in range(frames)]
            result += [gate.feed(bytes(640)) for _ in range(40)]
            self.assertEqual(sum(ended is not None for _, ended in result), 1,
                             f'{frames*20} ms spoken confirmation was discarded')

    def test_odd_network_chunk_keeps_incomplete_pcm_sample_for_next_chunk(self):
        self.assertIsNotNone(PlaybackBuffer)
        output = PlaybackBuffer()
        output.put(b'\x01\x02\x03', 0)
        self.assertEqual(output.read(4), b'\x01\x02\x00\x00')
        output.put(b'\x04', 0)
        self.assertEqual(output.read(4), b'\x03\x04\x00\x00')

    def test_split_pcm_sample_is_counted_once_after_completing_next_chunk(self):
        output = PlaybackBuffer()
        output.put(b'\x01\x02\x03', 0)
        self.assertEqual(output.accepted_samples, 1)
        self.assertEqual(output.read(2), b'\x01\x02')
        output.put(b'\x04', 0)
        self.assertEqual(output.accepted_samples, 2)
        self.assertEqual(output.emitted_samples, 1)
        self.assertEqual(output.read(2), b'\x03\x04')
        self.assertEqual(output.emitted_samples, 2)

    def test_odd_chunks_cannot_mark_question_complete_before_last_sample_drains(self):
        from types import SimpleNamespace
        from native_duplex import NativeDuplex

        output = PlaybackBuffer()
        call = SimpleNamespace(playback=output, call_settings=None, closed=False,
            closing=False, input_lost=False, failed=False)
        lane = NativeDuplex(call)
        state = lane.begin_greeting('Continue?')
        output.put(b'\x01\x02\x03', 0)
        output.put(b'\x04', 0)
        lane.finish_greeting(state, complete=True)
        output.read(2)
        self.assertEqual(lane.question_context(), ('Continue?', 'greeting', False))
        output.read(2)
        self.assertEqual(lane.question_context(), ('Continue?', 'greeting', True))

    def test_interruption_discards_partial_sample_before_counting_new_generation(self):
        output = PlaybackBuffer()
        output.put(b'\x01', 0)
        generation = output.interrupt()
        self.assertFalse(output.put(b'\x02', 0))
        output.put(b'\x03', generation)
        self.assertEqual(output.accepted_samples, 0)
        output.put(b'\x04', generation)
        self.assertEqual(output.accepted_samples, 1)
        self.assertEqual(output.read(2), b'\x03\x04')
        self.assertEqual(output.emitted_samples, 1)

    def test_native_authorization_requires_expected_agent_in_valid_envelope(self):
        self.assertIsNotNone(authorized_agents, 'native authorization response validator missing')
        agent = 'a4a9438393738354e7f2b9fa6aba101d'
        self.assertTrue(authorized_agents({'result':[agent]}, agent))
        for malformed in ([], [agent], {'result':[]}, {'result':[None]},
                          {'result':['bad']}, {'result':[agent],'error':'denied'},
                          {'result':{'authorized':True}}, {'result':['0'*32]}):
            self.assertFalse(authorized_agents(malformed, agent))

    def test_missing_wrong_or_remote_development_credentials_are_rejected(self):
        self.assertIsNotNone(local_auth, 'loopback credential verifier is missing')
        secret = 'development-only-credential-with-32-bytes'
        self.assertFalse(local_auth('', secret, '127.0.0.1'))
        self.assertFalse(local_auth('wrong', secret, '127.0.0.1'))
        self.assertFalse(local_auth(secret, secret, '192.168.1.2'))
        self.assertFalse(local_auth(secret, '', '127.0.0.1'))
        self.assertTrue(local_auth(secret, secret, '127.0.0.1'))

    def test_barge_in_discards_queued_and_late_audio_from_previous_generation(self):
        self.assertIsNotNone(PlaybackBuffer, 'generation-fenced audio buffer is missing')
        output = PlaybackBuffer()
        old = output.generation
        output.put(b'\x01\x00' * 480, old)
        new = output.interrupt()
        self.assertNotEqual(old, new)
        self.assertFalse(output.put(b'\x02\x00' * 480, old))
        self.assertEqual(output.read(960), bytes(960))
        self.assertTrue(output.put(b'\x03\x00' * 480, new))
        self.assertEqual(output.read(960), b'\x03\x00' * 480)

    def test_automatic_endpoint_includes_speech_and_emits_once_after_silence(self):
        self.assertIsNotNone(EndpointGate, 'automatic speech endpoint detector is missing')
        gate = EndpointGate(sample_rate=16000, threshold=300, onset_ms=160,
                            silence_ms=500, minimum_ms=250)
        silence = bytes(640)
        speech = array('h', [3000] * 320).tobytes()
        for _ in range(20):
            self.assertEqual(gate.feed(silence), (False, None))
        starts = 0
        utterance = None
        for _ in range(30):
            began, ended = gate.feed(speech)
            starts += int(began)
            self.assertIsNone(ended)
        for _ in range(40):
            began, ended = gate.feed(silence)
            if ended is not None:
                self.assertIsNone(utterance, 'one utterance emitted twice')
                utterance = ended
        self.assertEqual(starts, 1)
        self.assertIsNotNone(utterance)
        self.assertIn(speech * 20, utterance)

    def test_short_noise_does_not_start_or_submit_a_turn(self):
        self.assertIsNotNone(EndpointGate, 'automatic speech endpoint detector is missing')
        gate = EndpointGate(sample_rate=16000, threshold=300, onset_ms=160,
                            silence_ms=500, minimum_ms=250)
        noise = array('h', [3000] * 320).tobytes()
        result = [gate.feed(noise) for _ in range(4)]
        result += [gate.feed(bytes(640)) for _ in range(40)]
        self.assertEqual(result, [(False, None)] * 44)


if __name__ == '__main__':
    unittest.main()
