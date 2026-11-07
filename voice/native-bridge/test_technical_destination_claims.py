"""Offline qualification of destination assertions and failed-start recovery."""
from types import SimpleNamespace
import unittest
from conversation_claims import unproven_technical_destination_claim as claim
from native_backend import BackendEvent
from native_duplex import NativeDuplex, _PublicFinding
from test_native_duplex import FakeCall
from test_native_duplex_claim_release import SentenceModel

class WordingTests(unittest.TestCase):
    def test_target_independent_assertions_and_exact_authority(self):
        for target in ('Nordhafen', 'Team Blau', 'beliebiger Ausdruck'):
            text = f'Ich kann keine Verbindung zu „{target}“ herstellen, da dies kein gültiger Zielname ist.'
            self.assertTrue(claim(text))
            self.assertFalse(claim(text, (text.upper(),)))
            self.assertTrue(claim(text, ('Ein anderer Zielname ist ungültig.',)))
        self.assertTrue(claim('Dies ist keine gültige Gegenstelle.'))
        self.assertTrue(claim('Der Zielname Nordhafen ist ungültig.'))

    def test_qualified_language_and_clause_local_exceptions(self):
        for text in ('Ist dies kein gültiger Zielname?',
            'Sie sagten: „Dies ist kein gültiger Zielname.“',
            'Laut Ihrer Aussage ist dies kein gültiger Zielname.',
            'Dies ist kein gültiger Zielname, sagten Sie.',
            'Wenn die Prüfung fehlschlägt, ist dies kein gültiger Zielname.',
            'Dies ist möglicherweise kein gültiger Zielname.',
            'Allgemein ist eine Nummer ohne Präfix kein gültiger Zielname.',
            'Der Zielname ist nicht ungültig.',
            'Ich kann gerade keine Verbindung zu ServiceNow herstellen.'):
            with self.subTest(text=text): self.assertFalse(claim(text))
        for text in ('Dies ist kein gültiger Zielname und falls Sie möchten, können wir darüber sprechen.',
            'Laut Ihrer Aussage ist der erste Zielname ungültig, aber dies ist keine gültige Gegenstelle.',
            'Sie sagten: „Dies ist kein gültiger Zielname.“ Dies ist keine gültige Gegenstelle.',
            'Dies ist kein gültiger Zielname, aber laut Ihrer Aussage ist der andere Zielname gültig.',
            'Dies ist keine gültige Gegenstelle, aber allgemein sind andere Gegenstellen möglich.'):
            with self.subTest(text=text): self.assertTrue(claim(text))

class ReleaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        self.lane = NativeDuplex(self.call)
        self.turn = (0, 'Bitte die Verbindung aus unserem Gespräch.', 1, 'owned-input', 0)
        self.lane._observe_raw(self.turn[1])
        self.lane._pending.append(self.turn)

    async def asyncTearDown(self):
        self.call.closed = True
        await self.lane.close()

    async def test_recorded_classes_hard_reject_remainder_keep_fifo(self):
        for predicate, remainder in (
            ('keine gültige Gegenstelle ist', 'Bitte nennen Sie den korrekten Namen oder die Abteilung, mit der Sie verbunden werden möchten.'),
            ('kein gültiger Zielname ist', 'Bitte nennen Sie den korrekten Namen oder die Kennung des gewünschten Ansprechpartners.'),
            ('kein gültiger Zielname ist', 'Bitte nennen Sie den korrekten Namen des Mitarbeiters oder der Abteilung für die Bestellung.')):
            self.lane._bootstrap_state = 'failed'
            self.lane._backend_unavailable = True
            self.lane._help_failure_seen.clear()
            self.lane._outputs.clear()
            first = f'Ich kann keine Verbindung zu „Nordhafen“ herstellen, da dies {predicate}.'
            model = SentenceModel([first, remainder])
            self.lane.conversation = model
            await self.lane._general_help(self.turn, self.lane.epoch)
            self.assertEqual(model.offered, [first])
            self.assertTrue(model.closed)
            self.assertIsNone(self.lane.conversation)
            self.assertEqual([item.text for item in self.lane._outputs], [self.lane._status()])
            self.assertEqual(list(self.lane._pending), [self.turn])
            self.assertEqual(self.call.dialog.calls, [])

    async def test_only_current_owned_matching_outputtext_corroborates(self):
        text = 'Dies ist kein gültiger Zielname.'
        self.call.dialog.business_request_id = 'native-request'
        model = SentenceModel([])
        self.lane.conversation = model
        for owned, current, ui, state, output, expected in (
            (True, True, 'OutputText', 'pending', text, 'enqueued'),
            (True, True, 'OutputText', 'fully_host_emitted', text.upper(), 'enqueued'),
            (False, True, 'OutputText', 'pending', text, 'rejected'),
            (True, False, 'OutputText', 'pending', text, 'rejected'),
            (True, True, 'InputText', 'pending', text, 'rejected'),
            (True, True, 'OutputText', 'interrupted', text, 'rejected'),
            (True, True, 'OutputText', 'pending', 'Ein anderer Zielname ist ungültig.', 'rejected')):
            with self.subTest(owned=owned,current=current,ui=ui,state=state):
                self.lane._backend_receipts.clear()
                self.lane._outputs.clear()
                event = BackendEvent(1, 'native-request' if current else 'previous-request', ui,
                    output, 'native-event', self.call.dialog.backend_owner if owned else object())
                self.lane._backend_receipts[self.lane._backend_key(event)] = dict(event=event,state=state,
                    finding=_PublicFinding(self.lane._request, self.lane.task_revision, 1, self.lane.clock(), output))
                _, snapshot, observation = self.lane._dialogue_snapshot(self.turn,self.lane.epoch)
                candidate = SimpleNamespace(text=text,identity=model.identity)
                self.assertEqual(self.lane._release_conversation_sentence(candidate,self.turn,
                    self.lane.epoch,observation,snapshot,skip_unsupported_claim=True),expected)
        self.assertEqual(list(self.lane._pending),[self.turn])
        self.assertEqual(self.call.dialog.calls,[])

    async def test_failed_fallback_keeps_dedup_and_speech_fences(self):
        self.lane._bootstrap_state = 'failed'
        self.lane._enqueue_help_fallback(self.turn)
        self.lane._enqueue_help_fallback(self.turn)
        self.assertEqual([item.text for item in self.lane._outputs],[self.lane._status()])
        self.lane._outputs.clear()
        self.lane._turn_speech_started.append(self.turn[3])
        self.lane._enqueue_help_fallback(self.turn)
        self.assertEqual(list(self.lane._outputs),[])

if __name__ == '__main__': unittest.main()
