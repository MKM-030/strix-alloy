"""Real pinned RNNoise regressions using synthetic PCM, with no services or IO."""
from array import array
import math
import unittest

from core import EndpointGate
from pcm_denoise import MAX_PENDING_SAMPLES, StreamingPCM16Denoiser


class RealRNNoiseTests(unittest.TestCase):
    def denoiser(self):
        denoiser = StreamingPCM16Denoiser()
        self.addCleanup(denoiser.close)
        self.assertTrue(denoiser.active, 'The installed pinned RNNoise runtime must be exercised')
        self.assertIsNone(denoiser.fallback_reason)
        return denoiser

    def test_constant_dc_is_not_qualified_as_speech(self):
        # This deliberately resembles the timing-only microphone unit fixture.
        # A test fake may pass it through; the real DSP must reject its energy.
        denoiser = self.denoiser()
        raw = [array('h', [3000] * 320).tobytes() for _ in range(20)]
        raw += [bytes(640) for _ in range(70)]
        cleaned = [part for frame in raw for part in denoiser.feed(frame)]
        cleaned.extend(denoiser.finish())
        self.assertEqual(sum(map(len, cleaned)), sum(map(len, raw)))
        self.assertIsNone(denoiser.fallback_reason, 'DC rejection must come from real DSP')
        gate = EndpointGate(threshold=450, onset_ms=100, silence_ms=1200)
        events = []
        for pcm in cleaned:
            values = array('h', pcm)
            rms = math.sqrt(sum(value * value for value in values) / len(values))
            self.assertLess(rms, 450, 'Steady DC must remain below the speech energy floor')
            events.append(gate.feed(pcm, voiced=rms >= 450))
        self.assertFalse(any(began or utterance is not None for began, utterance in events))

    def test_irregular_stream_drains_exact_real_sample_count_once(self):
        denoiser = self.denoiser()
        pcm = array('h', [int(1200 * math.sin(index * .17)) for index in range(8671)]).tobytes()
        output = []
        offset, index = 0, 0
        sizes = (1, 17, 319, 320, 321, 161)
        while offset < len(pcm):
            size = sizes[index % len(sizes)] * 2
            output.extend(denoiser.feed(pcm[offset:offset + size]))
            self.assertLessEqual(denoiser.pending_samples, MAX_PENDING_SAMPLES)
            offset += size
            index += 1
        output.extend(denoiser.finish())
        self.assertIsNone(denoiser.fallback_reason, 'Sample accounting must exercise real resamplers')
        self.assertEqual(sum(map(len, output)), len(pcm), 'No padded or dropped input samples')
        self.assertEqual(denoiser.input_samples, len(pcm) // 2)
        self.assertEqual(denoiser.output_samples, denoiser.input_samples)
        self.assertEqual(denoiser.pending_samples, 0)
        self.assertEqual(denoiser.finish(), (), 'Repeated drain must emit no duplicate samples')


if __name__ == '__main__':
    unittest.main()
