"""Raw caller dialogue remains owned by the native ServiceNow conversation."""
import asyncio
import json
import sys
from types import SimpleNamespace
import unittest

from test_native_duplex import FakeCall
from native_duplex import NativeDuplex, _question_kind, _PublicFinding, _conversation_class
from conversation_repair import conversational_snapshot, NATURAL_CONVERSATION_PROMPT
from servicenow_voice_context import build_servicenow_voice_context

NAME = dict(source='servicenow_input_control', controlType='InputText',
            businessRequestId='name-request', label='Wie lautet der Name des Mitarbeiters?')


class RawDeliveryTests(unittest.IsolatedAsyncioTestCase):
    def lane(self):
        self.call = FakeCall()
        async def unavailable(*args):
            raise RuntimeError('offline optional model')
        self.duplex = NativeDuplex(self.call, conversation_factory=unavailable)
        return self.duplex

    def turn(self, text, number=1):
        return (self.call.playback.generation, text, number, str(number), 0)

    async def asyncTearDown(self):
        if hasattr(self, 'duplex'):
            self.call.closed = True
            await self.duplex.close()

    async def test_name_and_free_questions_are_raw_pending_not_local_name_candidates(self):
        for text in ('Mara Lühders', 'Wie lautet dein Name?', 'Kann ich dir eine Frage stellen?',
                     'Welche 2 Geräte sind verfügbar?', 'Nein, der Name lautet Lühders.'):
            with self.subTest(text=text):
                lane = self.lane()
                self.call.dialog.input_boundary = dict(NAME)
                await lane._accept(self.turn(text))
                self.assertEqual([turn[1] for turn in lane._pending], [text])
                self.assertFalse(any('Ich habe „' in item.text or 'buchstabieren' in item.text for item in lane._outputs))
                await lane.close()

    async def test_early_intent_stays_fifo_when_startup_reaches_name_control(self):
        lane = self.lane()
        lane._bootstrap_state = 'pending'
        text = 'Ich brauche einen Laptop und habe eine Frage dazu.'
        await lane._accept(self.turn(text))
        self.call.dialog.input_boundary = dict(NAME)
        opening = asyncio.get_running_loop().create_future()
        opening.set_result([NAME['label']])
        lane._settle_bootstrap(opening)
        self.assertEqual([turn[1] for turn in lane._pending], [text])
        self.assertEqual(list(lane._supplements), [])

    async def test_busy_fallback_is_brief_and_preserves_original_fifo(self):
        lane = self.lane()
        text = 'Wie lautet dein Name?'
        await lane._accept(self.turn(text))
        lane._enqueue_help_fallback(self.turn(text), reason='controller_busy')
        self.assertEqual([turn[1] for turn in lane._pending], [text])
        output = ' '.join(item.text for item in lane._outputs)
        self.assertLessEqual(len(output), 120)
        self.assertNotIn('aktuelle Rückfrage', output)
        self.assertNotIn('Angabe oder welchen Schritt', output)

    async def test_local_prompt_uses_current_configured_assistant_instead_of_developer_demo(self):
        settings = SimpleNamespace(language='de', session_parameters=lambda: {
            'language':'de', 'prompt':{'systemMessage':'Du bist der Laptop-Assistent. Erkläre die angebotenen Geräte.'}})
        context = build_servicenow_voice_context(settings)
        self.assertIn('Du bist der Laptop-Assistent.', context.system_prompt_fragment)
        wire = context.system_prompt_fragment + ' '.join(context.capability_limits)
        for text in ('A2A', 'Fluent', '4.12.2', 'SDK', 'Quellstand 23.10.'):
            self.assertNotIn(text, wire)

    async def test_owned_clarification_is_context_without_forcing_every_free_answer_to_it(self):
        result = conversational_snapshot(dict(raw_inputs=(), public_findings=()),
            question='Meinten Sie Ihre letzte Angabe?', question_source='local_clarification')
        self.assertEqual(result['question'], 'Meinten Sie Ihre letzte Angabe?')
        self.assertFalse(any('erkläre diese konkrete Frage statt' in text for text in result['capability_limits']))

    async def test_presentation_limit_preserves_complete_text_or_refuses_without_truncation(self):
        configured = 'x' * 8000
        context = build_servicenow_voice_context(dict(language='de', prompt=dict(systemMessage=configured)))
        self.assertIn(configured, context.system_prompt_fragment)
        self.assertLessEqual(len(NATURAL_CONVERSATION_PROMPT + '\n' + context.system_prompt_fragment), 10000)
        with self.assertRaisesRegex(ValueError, 'presentation exceeds'):
            build_servicenow_voice_context(dict(prompt=dict(systemMessage=configured + 'x')))

    async def test_optional_question_kind_does_not_exclude_names_digits_or_first_person_questions(self):
        for text in ('Wie lautet dein Name?', 'Welche 2 Geräte gibt es?', 'Kann ich dir eine Frage stellen?'):
            self.assertIsNotNone(_question_kind(text), text)

    async def test_stale_bare_yes_does_not_answer_a_later_native_confirmation(self):
        lane = self.lane()
        await lane._accept(self.turn('Ja'))
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='later-order', label='Soll ich diese Bestellung ausführen?')
        self.call.dialog.release.put_nowait('Unerwarteter Versand')
        await lane._business(lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, [])
        self.assertIn('Soll ich diese Bestellung ausführen?', [item.text for item in lane._outputs])

    async def test_stale_pure_backchannels_cannot_approve_a_new_native_request(self):
        for text in ('Okay', 'in Ordnung', 'verstanden'):
            with self.subTest(text=text):
                lane = self.lane()
                label = 'Soll ich diese Bestellung ausführen?'
                self.call.dialog.input_boundary = dict(source='servicenow_input_control',
                    controlType='InputText', businessRequestId='old-order', label=label)
                native = lane._begin_speech(SimpleNamespace(text=label, kind='backend', question_binding=None))
                self.call.playback.put(bytes(480), self.call.playback.generation)
                self.call.playback.read(480)
                lane._finish_speech(native, complete=True)
                lane._input_questions[self.call.playback.generation] = lane._input_question_snapshot()
                self.call.dialog.input_boundary['businessRequestId'] = 'new-order'
                await lane._accept(self.turn(text))
                self.call.dialog.release.put_nowait('Unerwartete Freigabe')
                await lane._business(lane._pending.popleft())
                self.assertEqual(self.call.dialog.calls, [])
                await lane.close()

    async def test_complete_current_native_backchannel_or_mixed_text_reaches_native_verbatim(self):
        for text in ('Okay', 'in Ordnung', 'Okay, der Name lautet Mara Lühders.'):
            with self.subTest(text=text):
                lane = self.lane()
                label = 'Ist der Name Mara Lühders korrekt?'
                self.call.dialog.input_boundary = dict(source='servicenow_input_control',
                    controlType='InputText', businessRequestId='current-name', label=label)
                native = lane._begin_speech(SimpleNamespace(text=label, kind='backend', question_binding=None))
                self.call.playback.put(bytes(480), self.call.playback.generation)
                self.call.playback.read(480)
                lane._finish_speech(native, complete=True)
                lane._input_questions[self.call.playback.generation] = lane._input_question_snapshot()
                await lane._accept(self.turn(text))
                self.call.dialog.release.put_nowait('Native Antwort')
                await lane._business(lane._pending.popleft())
                self.assertEqual(self.call.dialog.calls, [text])
                await lane.close()

    async def test_answer_to_complete_current_native_confirmation_goes_raw_once(self):
        lane = self.lane()
        self.call.dialog.input_boundary = dict(source='servicenow_input_control',
            controlType='InputText', businessRequestId='current-order', label='Soll ich diese Bestellung ausführen?')
        state = lane._begin_speech(SimpleNamespace(text=self.call.dialog.input_boundary['label'],
            kind='backend', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        lane._finish_speech(state, complete=True)
        self.call.playback.read(480)
        lane._input_questions[self.call.playback.generation] = lane._input_question_snapshot()
        await lane._accept(self.turn('Ja'))
        self.call.dialog.release.put_nowait('Native Antwort')
        await lane._business(lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, ['Ja'])

    async def test_assistant_context_requires_complete_emitted_pcm_not_queued_text(self):
        lane = self.lane()
        text = 'Welche Geräte möchten Sie vergleichen?'
        state = lane._begin_speech(SimpleNamespace(text=text, kind='conversation', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        lane._finish_speech(state, complete=True)
        _, before, _ = lane._dialogue_snapshot(self.turn('Welche sind leichter?'), lane.epoch)
        self.assertFalse(any(item['source_event'] == 'complete_emitted_assistant_speech' for item in before['public_findings']))
        self.call.playback.read(480)
        _, after, _ = lane._dialogue_snapshot(self.turn('Welche sind leichter?'), lane.epoch)
        spoken = [item for item in after['public_findings'] if item['source_event'] == 'complete_emitted_assistant_speech']
        self.assertEqual([item['text'] for item in spoken], [text])

    async def test_interrupted_assistant_output_is_not_complete_dialogue_history(self):
        lane = self.lane()
        state = lane._begin_speech(SimpleNamespace(text='Nicht vollständig gehört.', kind='conversation', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        state['interrupted'] = True
        lane._finish_speech(state, complete=False)
        self.call.playback.read(480)
        _, snapshot, _ = lane._dialogue_snapshot(self.turn('Neue Frage?'), lane.epoch)
        self.assertFalse(any(item['source_event'] == 'complete_emitted_assistant_speech' for item in snapshot['public_findings']))

    async def test_optional_spoken_history_cannot_overflow_current_processing_snapshot(self):
        lane = self.lane()
        raw = 'R' * 4000
        lane._observe_raw(raw)
        lane._request = 1
        lane._reply_revision = lane.task_revision
        lane._public_findings.append(_PublicFinding(1, lane.task_revision, 1, 1.0, 'P' * 2000))
        lane._spoken_history.extend(dict(text='S' * 2000, sequence=i, observed_at=1.0)
                                    for i in (1, 2))
        self.call.dialog.processing = dict(revision=1, messages=['V' * 2000], ageSeconds=0)
        key, snapshot, _ = lane._dialogue_snapshot(self.turn(raw), lane.epoch)
        self.assertEqual(snapshot['raw_inputs'], (raw,))
        self.assertTrue(any(item['source_event'] == 'servicenow_processing_presentation'
                            for item in snapshot['public_findings']))
        self.assertLessEqual(len(json.dumps(snapshot, ensure_ascii=False, separators=(',', ':'))), 10000)
        _conversation_class()
        sys.modules['omni_conversation']._snapshot(snapshot, key)

    async def test_yes_after_a_different_local_question_cannot_approve_native_order(self):
        lane = self.lane()
        self.call.dialog.input_boundary = dict(source='servicenow_input_control', controlType='InputText',
            businessRequestId='order-current', label='Soll ich diese Bestellung ausführen?')
        native = lane._begin_speech(SimpleNamespace(text=self.call.dialog.input_boundary['label'],
            kind='backend', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.call.playback.read(480)
        lane._finish_speech(native, complete=True)
        local = lane._begin_speech(SimpleNamespace(text='Möchten Sie den Unterschied erklärt haben?',
            kind='conversation', question_binding=None))
        self.call.playback.put(bytes(480), self.call.playback.generation)
        self.call.playback.read(480)
        lane._finish_speech(local, complete=True)
        lane._input_questions[self.call.playback.generation] = lane._input_question_snapshot()
        await lane._accept(self.turn('Ja'))
        self.call.dialog.release.put_nowait('Unerwarteter Versand')
        await lane._business(lane._pending.popleft())
        self.assertEqual(self.call.dialog.calls, [])


if __name__ == '__main__':
    unittest.main()
