"""Backlogged raw speech crosses one open text boundary without extra VA turns."""
import asyncio
import unittest
from types import SimpleNamespace

from native_duplex import NativeDuplex
from native_backend import BackendEvent
from test_native_duplex import FakeCall


def boundary(request='a' * 32, control='InputText', label='Für welchen Mitarbeiter soll der Laptop bestellt werden?'):
    return dict(source='servicenow_input_control', controlType=control,
                businessRequestId=request, label=label)


class InputBatchTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.call = FakeCall()
        async def unavailable(*args):
            raise RuntimeError('offline optional model')
        self.lane = NativeDuplex(self.call, conversation_factory=unavailable)
        self.running = None

    async def asyncTearDown(self):
        self.call.closed = True
        if self.running is not None:
            self.running.cancel()
            await asyncio.gather(self.running, return_exceptions=True)
        await self.lane.close()

    async def queue(self, *texts):
        for number, text in enumerate(texts, 1):
            await self.lane._accept((self.call.playback.generation, text, number,
                                     f'{number:032x}', float(number)))

    async def test_three_startup_utterances_reach_native_in_one_ordered_raw_message(self):
        self.lane._bootstrap_state = 'pending'
        originals = ('Für Lea Oldma bitte bestellen für Sie los', 'Mariaz', 'Was dauert da so lange?')
        await self.queue(*originals)
        self.call.dialog.input_boundary = boundary()
        opening = asyncio.get_running_loop().create_future()
        opening.set_result([self.call.dialog.input_boundary['label']])
        self.running = asyncio.create_task(self.lane.run(bootstrap_task=opening))
        sent = await asyncio.wait_for(self.call.dialog.started.get(), 1)
        self.assertEqual(sent, '\n'.join(originals))
        self.assertEqual(self.call.dialog.calls, ['\n'.join(originals)])
        self.assertEqual(list(self.lane._pending), [])

    async def dispatch_once(self):
        self.call.dialog.release.put_nowait('Native Antwort')
        await self.lane._business(self.lane._pending.popleft())

    async def test_same_open_boundary_keeps_spelling_and_date_corrections_exactly(self):
        self.call.dialog.input_boundary = boundary()
        originals = ('Nachname: O, L, T, M, E, R!', 'Eintritt: 01.01.2027, nicht 2029.',
                     'Was genau fehlt noch?')
        await self.queue(*originals)
        await self.dispatch_once()
        self.assertEqual(self.call.dialog.calls, ['\n'.join(originals)])
        self.assertFalse(self.lane._pending)
        self.assertFalse(self.lane._submission_onsets)
        self.assertEqual(tuple(self.lane._raw), originals)

    async def test_native_choice_and_confirmation_boundaries_never_join_inputs(self):
        for control, label in (
                ('Boolean', 'Soll ich bestellen?'),
                ('Picker', 'Welches Gerät möchten Sie?'),
                ('InputText', 'Ist der Name richtig?'),
                ('InputText', 'Bitte bestätigen Sie die Bestellung.'),
                ('InputText', 'Wie bestätigen Sie die Bestellung?'),
                ('InputText', 'Für wen ist der Laptop? Soll ich bestellen?')):
            with self.subTest(control=control, label=label):
                self.call.dialog.input_boundary = boundary(control=control, label=label)
                await self.queue('Der Name lautet Oltmer.', 'Das Datum ist 01.01.2027.')
                await self.dispatch_once()
                self.assertEqual(self.call.dialog.calls, ['Der Name lautet Oltmer.'])
                self.assertEqual([t[1] for t in self.lane._pending], ['Das Datum ist 01.01.2027.'])
                await self.lane.close()
                await self.asyncSetUp()

    async def test_changed_owner_or_input_question_leaves_originals_separate(self):
        for change in ('owner', 'question', 'request'):
            with self.subTest(change=change):
                self.call.dialog.input_boundary = boundary()
                await self.queue('Erste Angabe.', 'Zweite Angabe.')
                if change == 'owner':
                    self.call.dialog.backend_owner = object()
                elif change == 'request':
                    self.call.dialog.business_request_id = 'b' * 32
                else:
                    self.call.dialog.input_boundary = boundary(request='b' * 32,
                                                               label='Welche Lieferadresse gilt?')
                await self.dispatch_once()
                self.assertEqual(self.call.dialog.calls, ['Erste Angabe.'])
                self.assertEqual([t[1] for t in self.lane._pending], ['Zweite Angabe.'])
                await self.lane.close()
                await self.asyncSetUp()

    async def test_language_context_change_and_size_limit_do_not_drop_tail(self):
        for change in ('context', 'size'):
            with self.subTest(change=change):
                self.call.dialog.input_boundary = boundary()
                first = 'A' * 3998 if change == 'size' else 'Erste Angabe.'
                await self.queue(first, 'Zweite Angabe.')
                if change == 'context':
                    self.call.turn_contexts[1] = {'language': 'de'}
                    self.call.turn_contexts[2] = {'language': 'en'}
                await self.dispatch_once()
                self.assertEqual(self.call.dialog.calls, [first])
                self.assertEqual([t[1] for t in self.lane._pending], ['Zweite Angabe.'])
                await self.lane.close()
                await self.asyncSetUp()

    async def test_uncertain_group_submission_is_never_requeued_or_replayed(self):
        self.call.dialog.input_boundary = boundary()
        originals = ('Für Lea Oltmer.', 'Eintritt 01.01.2027.')
        await self.queue(*originals)
        async def uncertain(text, **kwargs):
            self.call.dialog.calls.append(text)
            raise RuntimeError('Delivery uncertain after request write')
        self.call.dialog.turn = uncertain
        with self.assertRaisesRegex(RuntimeError, 'Delivery uncertain'):
            await self.lane._business(self.lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, ['\n'.join(originals)])
        self.assertFalse(self.lane._pending)
        self.assertFalse(self.lane._submission_onsets)

    async def test_future_correction_cannot_reach_context_before_earlier_raw_message(self):
        published = []
        async def publish(revision, text):
            published.append(text)
            return dict(state='context_action_acknowledged', revision=revision,
                        ingested=False, contextStored=True, promptIncluded=False)
        self.lane._context_publisher = publish
        await self.queue('Eintritt 01.01.2029, Führungskraft bin ich.')
        self.running = asyncio.create_task(self.lane._business(self.lane._pending.popleft()))
        self.lane._backend = self.running
        await self.call.dialog.started.get()
        await self.lane._accept((0, 'Nein, es ist 01.01.2027.', 2, 'b' * 32, 2.0))
        self.lane._start_worker('context', self.lane._context_loop())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        self.assertEqual(published, [])
        self.assertEqual([t[1] for t in self.lane._pending], ['Nein, es ist 01.01.2027.'])
        self.assertEqual(self.call.dialog.calls, ['Eintritt 01.01.2029, Führungskraft bin ich.'])

    async def test_old_factual_input_is_held_at_new_picker_and_fresh_answer_is_allowed(self):
        original = 'Eintritt 01.01.2029, Führungskraft bin ich.'
        await self.queue(original)
        label = 'Eintritt 01.01.2027, Führungskraft Marcel. Ist das so korrekt?'
        self.call.dialog.business_request_id = 'a' * 32
        self.call.dialog.input_boundary = boundary(control='Picker', label=label)
        self.call.dialog.input_control = BackendEvent(1, 'a' * 32, 'Picker', label,
                                                      'confirmation-choice', self.call.dialog.backend_owner)
        self.call.dialog.release.put_nowait('An unbound original must not reach this response')
        await self.lane._business(self.lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual([held.turn[1] for held in self.lane._control_gate.held], [original])
        self.assertEqual([out.text for out in self.lane._outputs], [label])
        self.assertIsNone(self.lane._held_context_recovery)
        self.call.dialog.release.get_nowait()
        state = self.lane._begin_speech(SimpleNamespace(text=label, kind='backend', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.call.playback.read(480)
        self.lane._finish_speech(state, complete=True)
        self.lane._input_questions[self.call.playback.generation] = self.lane._input_question_snapshot()
        answer = 'Nein, das Datum ist 01.01.2027 und der Nachname ist noch falsch.'
        await self.lane._accept((self.call.playback.generation, answer, 2, 'b' * 32, 2.0))
        self.call.dialog.release.put_nowait(dict(reply='Wie lautet der Nachname?',
                                               input_boundary=boundary(label='Wie lautet der Nachname?')))
        await self.lane._business(self.lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, [answer])
        self.assertIsNotNone(self.lane._held_context_recovery)

    async def test_held_turn_optional_reply_cannot_replace_heard_question_or_block_fresh_answer(self):
        class Conversation:
            output_epoch = 1
            def __init__(inner):
                inner.calls = 0
                inner.identity = SimpleNamespace(server_session_id='offline-source')
            async def respond(inner, raw, snapshot, key):
                inner.calls += 1
                return SimpleNamespace(text='Gern, ich höre Ihnen zu.', identity=inner.identity, failure=None)
            def is_current(inner, identity):
                return identity is inner.identity
            async def invalidate(inner, epoch, reason):
                inner.output_epoch = epoch
            async def close(inner):
                pass
        await self.queue('Eintritt 01.01.2029, Führungskraft bin ich.')
        held_turn = self.lane._pending.popleft()
        label = 'Eintritt 01.01.2027, Führungskraft Marcel. Ist das so korrekt?'
        self.call.dialog.business_request_id = 'a' * 32
        self.call.dialog.input_boundary = boundary(control='Picker', label=label)
        self.call.dialog.input_control = BackendEvent(1, 'a' * 32, 'Picker', label,
                                                      'confirmation-choice', self.call.dialog.backend_owner)
        await self.lane._business(held_turn)
        state = self.lane._begin_speech(self.lane._outputs.popleft())
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.call.playback.read(480)
        self.lane._finish_speech(state, complete=True)
        self.assertIs(self.lane._speech, self.lane._spoken_question)
        conversation = Conversation()
        conversation.output_epoch = self.lane.epoch
        self.lane.conversation = conversation

        # The queued local work is still present after business input is held.
        queued_turn, kind, epoch = self.lane._local_questions.get_nowait()
        self.lane._local_questions.task_done()
        await self.lane._general_help(queued_turn, epoch, kind)
        self.assertEqual(conversation.calls, 0, 'Held input must not start a new optional reply')
        # A candidate already in flight is rejected even with current context.
        _, snapshot, observation = self.lane._dialogue_snapshot(held_turn, self.lane.epoch)
        candidate = SimpleNamespace(text='Gern, ich höre Ihnen zu.', identity=conversation.identity)
        self.assertEqual(self.lane._release_conversation_sentence(candidate, held_turn,
            self.lane.epoch, observation, snapshot), 'rejected')
        self.lane._enqueue_help_fallback(held_turn)
        self.lane._enqueue('Eine späte lokale Rückmeldung.', held_turn, kind='status')
        self.assertFalse(self.lane._outputs)
        self.assertIs(self.lane._speech, self.lane._spoken_question)

        self.lane._input_questions[self.call.playback.generation] = self.lane._input_question_snapshot()
        answer = 'Nein, das Datum ist 01.01.2027 und der Nachname ist noch falsch.'
        await self.lane._accept((self.call.playback.generation, answer, 2, 'b' * 32, 2.0))
        fresh_turn = self.lane._pending.popleft()
        self.call.dialog.release.put_nowait(dict(reply='Wie lautet der Nachname?',
                                               input_boundary=boundary(label='Wie lautet der Nachname?')))
        await self.lane._business(fresh_turn)
        self.assertEqual(self.call.dialog.calls, [answer])
        self.assertEqual(len(self.lane._control_gate.held), 1)
        await self.lane._general_help(fresh_turn, self.lane.epoch)
        self.assertEqual(conversation.calls, 1, 'A fresh turn must retain ordinary optional conversation')
        self.assertTrue(any(item.kind == 'conversation' for item in self.lane._outputs))

    async def test_holding_turn_retires_already_buffered_optional_speech_lease(self):
        await self.queue('Eintritt 01.01.2029.')
        turn = self.lane._pending.popleft()
        self.lane._enqueue('Ich höre Ihnen zu.', turn, kind='conversation')
        item = self.lane._outputs.popleft()
        self.lane._active_output = item
        state = self.lane._begin_speech(item)
        await self.lane._synthesize(item, self.call.playback.generation)
        lease = state['lease']
        self.assertIsNotNone(lease)
        self.assertTrue(self.call.playback.data)
        label = 'Welches Gerät möchten Sie?'
        self.call.dialog.business_request_id = 'a' * 32
        self.call.dialog.input_boundary = boundary(control='Picker', label=label)
        self.call.dialog.input_control = BackendEvent(1, 'a' * 32, 'Picker', label,
                                                      'device-choice', self.call.dialog.backend_owner)
        await self.lane._business(turn)
        self.assertFalse(self.lane._active_speech_current(item, lease.generation, lease))
        self.assertFalse(self.call.playback.data)
        self.assertEqual([out.text for out in self.lane._outputs], [label])

    async def test_late_recognition_keeps_its_old_onset_after_new_question_is_heard(self):
        class OnsetTurn(tuple):
            pass
        old_onset = self.lane._input_question_snapshot()
        label = 'Eintritt 01.01.2027. Ist das korrekt?'
        self.call.dialog.business_request_id = 'a' * 32
        self.call.dialog.input_boundary = boundary(control='Picker', label=label)
        self.call.dialog.input_control = BackendEvent(1, 'a' * 32, 'Picker', label,
                                                      'confirmation-choice', self.call.dialog.backend_owner)
        state = self.lane._begin_speech(SimpleNamespace(text=label, kind='backend', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.call.playback.read(480)
        self.lane._finish_speech(state, complete=True)
        original = 'Eintritt 01.01.2029, Führungskraft bin ich.'
        turn = OnsetTurn((self.call.playback.generation, original, 1, 'b' * 32, 1.0))
        turn.duplex_onset = (old_onset, False)
        await self.lane._accept(turn)
        self.call.dialog.release.put_nowait('Must not be reached')
        await self.lane._business(self.lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, [])
        self.assertEqual([held.turn[1] for held in self.lane._control_gate.held], [original])


if __name__ == '__main__':
    unittest.main()
