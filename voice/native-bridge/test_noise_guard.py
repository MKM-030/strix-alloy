import unittest
from noise_guard import SpeechNoiseGuard, accepted_transcript


class NoiseGuardTests(unittest.TestCase):
    def test_residual_noise_does_not_interrupt_voice(self):
        gate = SpeechNoiseGuard()
        for _ in range(200):
            self.assertFalse(gate.qualify(.12, 650, 20, speaking=True))
        for _ in range(15):
            self.assertFalse(gate.qualify(.7, 1200, 20, speaking=True))
        self.assertFalse(gate.qualify(.99, 600, 20, speaking=True))

    def test_deliberate_speech_interrupts_after_sustained_onset(self):
        gate = SpeechNoiseGuard()
        decisions = [gate.qualify(.98, 700, 20, speaking=True) for _ in range(11)]
        self.assertEqual(decisions, [False] * 10 + [True])
        self.assertTrue(gate.qualify(.5, 25, 20, utterance_active=True))
        gate.reset()
        self.assertFalse(gate.qualify(.98, 700, 20, speaking=True))

    def test_quiet_confident_speech_survives_short_phonetic_gaps(self):
        gate = SpeechNoiseGuard()
        for _ in range(10):
            self.assertFalse(gate.qualify(.98, 18, 20, speaking=True))
        for _ in range(3):
            self.assertFalse(gate.qualify(.5, 12, 20, speaking=True))
        self.assertFalse(gate.qualify(.98, 18, 20, speaking=True))
        self.assertTrue(gate.qualify(.98, 18, 20, speaking=True))
        gate.reset()
        for _ in range(10):
            self.assertFalse(gate.qualify(.98, 18, 20, speaking=True))
        for _ in range(4):
            self.assertFalse(gate.qualify(.5, 12, 20, speaking=True))
        self.assertFalse(gate.qualify(.98, 18, 20, speaking=True))

    def test_soft_speech_and_short_confirmation_are_not_energy_filtered(self):
        gate = SpeechNoiseGuard()
        self.assertTrue(gate.qualify(.97, 18, 20))
        self.assertTrue(gate.qualify(.67, 22, 20))
        self.assertFalse(gate.qualify(float('nan'), 300, 20, speaking=True))

    def test_asr_noise_rejected_without_rewriting_names_or_real_thanks(self):
        self.assertEqual(accepted_transcript({'text': 'Vielen Dank', 'segments': [
            {'no_speech_prob': .95, 'avg_logprob': -1.6}]}), '')
        self.assertEqual(accepted_transcript({'text': 'Marcel Käfke', 'segments': [
            {'no_speech_prob': .01, 'avg_logprob': -1.6}]}), 'Marcel Käfke')
        self.assertEqual(accepted_transcript({'text': 'Vielen Dank', 'segments': [
            {'no_speech_prob': .01, 'avg_logprob': -.1}]}), 'Vielen Dank')
        self.assertEqual(accepted_transcript({'text': 'Ja'}), 'Ja')


if __name__ == '__main__':
    unittest.main()
