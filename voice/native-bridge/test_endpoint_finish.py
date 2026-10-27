import importlib.util
import os
from pathlib import Path
from array import array
import unittest

CORE = Path(os.environ.get('NATIVE_GAP_CORE', str(Path(__file__).with_name('core.py'))))
spec = importlib.util.spec_from_file_location('finish_core', CORE)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)

class EndpointFinishTests(unittest.TestCase):
    def feed(self, gate, n):
        for _ in range(n): gate.feed(array('h',[3000]*320).tobytes())
    def test_finish_is_exactly_once_and_contains_only_actual_pcm(self):
        gate = core.EndpointGate(silence_ms=1200)
        self.feed(gate,20)
        actual = array('h',[3000]*6400).tobytes()
        self.assertEqual(gate.finish(),actual)
        self.assertIsNone(gate.finish())
        self.assertFalse(gate.active)
        self.assertEqual(len(gate.audio),0)
    def test_finish_rejects_onset_below_minimum_speech(self):
        gate = core.EndpointGate(silence_ms=1200)
        self.feed(gate,5)
        self.assertFalse(gate.active, 'Speech shorter than the minimum cannot interrupt playback')
        self.assertIsNone(gate.finish())
        self.assertFalse(gate.active)
    def test_finish_no_voice_returns_none(self):
        gate = core.EndpointGate(silence_ms=1200)
        self.assertIsNone(gate.finish())
    def test_new_utterance_is_independent_after_finish(self):
        gate = core.EndpointGate(silence_ms=1200)
        self.feed(gate,20)
        first = gate.finish()
        for _ in range(20): gate.feed(bytes(640))
        self.feed(gate,20)
        second = gate.finish()
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        self.assertTrue(second.endswith(first))
    def test_continuous_loud_stream_keeps_twenty_second_limit(self):
        gate = core.EndpointGate(silence_ms=1200)
        endings = []
        for _ in range(1000):
            _, ended = gate.feed(array('h',[3000]*320).tobytes())
            if ended: endings.append(ended)
        self.assertEqual(len(endings),1)
        self.assertEqual(len(endings[0]),640000)

if __name__ == '__main__': unittest.main()
