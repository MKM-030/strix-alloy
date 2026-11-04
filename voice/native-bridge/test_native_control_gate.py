"""Original inputs cannot answer a typed control that they did not hear."""
import unittest
import native_backend as backend


class ControlGateTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(hasattr(backend, 'ControlGate'), 'The universal typed input barrier is missing')
        self.owner = object()
        self.binding = backend.ControlBinding('a' * 32, 'Boolean',
            'Alle Angaben sind vorhanden. Soll ich das bestellen?', 7, 'genuine-control', self.owner)
        self.gate = backend.ControlGate()
        self.gate.observe(self.binding)

    def turn(self, text, number=1):
        return (0, text, number, str(number), 1.0)

    def test_every_unheard_raw_input_is_held_as_original_with_context(self):
        for number, text in enumerate(('Wie geht jetzt weiter', 'Ja und was ist jetzt damit? Sind wir jetzt fertig oder',
                                       'Ja', 'Berlin', 'Bitte ändern.'), 1):
            turn = self.turn(text, number)
            context = {'language':'de', 'profile':'original'}
            self.assertFalse(self.gate.admit(turn, None, context))
            context['language'] = 'en'
            self.assertIs(self.gate.held[-1].turn, turn)
            self.assertEqual(self.gate.held[-1].voice_context['language'], 'de')
        self.assertEqual(len(self.gate.held), 5)

    def test_new_onset_after_full_emission_dispatches_exact_raw_once(self):
        self.gate.mark_emitted(self.binding)
        turn = self.turn('Nein, zuerst möchte ich den Lieferort ändern.')
        self.assertTrue(self.gate.admit(turn, self.binding, None))
        self.assertEqual(turn[1], 'Nein, zuerst möchte ich den Lieferort ändern.')
        self.assertFalse(self.gate.admit(self.turn('Ja', 2), self.binding, None))

    def test_late_asr_with_prequestion_onset_stays_held_after_emission(self):
        old_onset = None
        self.gate.mark_emitted(self.binding)
        turn = self.turn('Ja')
        self.assertFalse(self.gate.admit(turn, old_onset, None))
        self.assertEqual(self.gate.held[0].reason, 'control_onset_unbound')

    def test_same_control_preserves_heard_status_but_new_uid_retires_it(self):
        self.gate.mark_emitted(self.binding)
        self.gate.observe(self.binding)
        self.assertTrue(self.gate.heard)
        replacement = backend.ControlBinding('a' * 32, 'Boolean', self.binding.label,
            8, 'new-genuine-control', self.owner)
        self.gate.observe(replacement)
        self.assertFalse(self.gate.heard)
        self.assertFalse(self.gate.admit(self.turn('Ja'), self.binding, None))


if __name__ == '__main__':
    unittest.main()
