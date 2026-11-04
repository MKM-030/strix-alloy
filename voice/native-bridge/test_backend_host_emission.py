"""CPU-only proof that private backend markers follow real PCM host drain."""
import hashlib
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import native_duplex as d
from native_backend import BackendEvent
from test_native_duplex import FakeCall


class BackendHostEmissionTests(unittest.TestCase):
    text = 'Mir fehlen noch das Eintrittsdatum und die zuständige Führungskraft.'
    caller = 'f' * 32

    def fixture(self, *, kind='backend', turn=True, owned_event=False):
        call = FakeCall()
        call.call_id = 'a' * 12
        lane = d.NativeDuplex(call)
        original = (0, 'Welche Angaben fehlen?', 3, self.caller, time.monotonic()) if turn else None
        if owned_event:
            call.dialog.business_request_id = 'b' * 32
            event = BackendEvent(1, call.dialog.business_request_id, 'OutputText', self.text, '', call.dialog.backend_owner)
            self.assertTrue(lane._admit_backend_event(event, original))
            item = lane._backend_outputs.popleft()
        else:
            item = d._Output(self.text, original, lane.epoch, lane.task_revision, None, kind)
        state = lane._begin_speech(item)
        lease = d._SpeechLease(item, call.playback.generation, lane.epoch, None, None)
        state['lease'] = lease
        call.playback.put(bytes([1, 0]) * 960, lease.generation,
            drain_allowed=lambda: lane._active_speech_current(item, lease.generation, lease))
        return call, lane, state

    @staticmethod
    def markers(log):
        return [entry.args[0] % entry.args[1:] for entry in log.call_args_list
                if 'stage=host_emitted ' in entry.args[0]]

    def test_completion_before_drain_has_no_marker_then_real_drain_emits_once(self):
        call, lane, state = self.fixture()
        with patch.object(d.LOG, 'info') as log:
            lane._finish_speech(state, complete=True)
            self.assertEqual(self.markers(log), [])
            call.playback.read(960)
            lane._update_speech_cursor()
            self.assertEqual(self.markers(log), [])
            call.playback.read(960)
            lane._update_speech_cursor()
            lane._update_speech_cursor()
            self.assertEqual(len(self.markers(log)), 1)
            marker = self.markers(log)[0]
        self.assertIn('call=' + call.call_id + ' ', marker)
        self.assertIn('kind=backend ', marker)
        self.assertIn('caller_turn_id=' + self.caller + ' ', marker)
        self.assertIn('text_sha256=' + hashlib.sha256(self.text.encode()).hexdigest() + ' ', marker)
        self.assertIn('generation=0 accepted_samples=960 emitted_samples=960', marker)
        self.assertNotIn(self.text, marker)
        self.assertTrue(state['history_recorded'])
        self.assertEqual(lane._spoken_history[-1]['text'], self.text)

    def test_synthesis_must_complete_even_when_all_pcm_has_drained(self):
        call, lane, state = self.fixture()
        with patch.object(d.LOG, 'info') as log:
            call.playback.read(1920)
            lane._update_speech_cursor()
            self.assertEqual(self.markers(log), [])
            lane._finish_speech(state, complete=True)
            self.assertEqual(len(self.markers(log)), 1)

    def test_padding_is_not_counted_and_original_item_never_uses_latest_turn(self):
        call, lane, state = self.fixture()
        lane._request = 999
        lane._incoming_turn = (0, 'Andere Eingabe', 99, 'e' * 32, 0)
        with patch.object(d.LOG, 'info') as log:
            call.playback.read(48000)
            lane._finish_speech(state, complete=True)
            self.assertEqual(len(self.markers(log)), 1)
            marker = self.markers(log)[0]
        self.assertIn('caller_turn_id=' + self.caller, marker)
        self.assertNotIn('e' * 32, marker)
        self.assertIn('accepted_samples=960 emitted_samples=960', marker)

    def test_unbound_backend_control_uses_empty_sentinel_without_invented_caller(self):
        call, lane, state = self.fixture(kind='backend_control', turn=False)
        with patch.object(d.LOG, 'info') as log:
            call.playback.read(1920)
            lane._finish_speech(state, complete=True)
            self.assertEqual(len(self.markers(log)), 1)
            marker = self.markers(log)[0]
        self.assertIn('kind=backend_control caller_turn_id=- ', marker)

    def test_local_greeting_processing_outputs_never_emit_backend_marker(self):
        for kind in ('conversation', 'local', 'greeting', 'processing', 'automatic'):
            with self.subTest(kind=kind):
                call, lane, state = self.fixture(kind=kind)
                with patch.object(d.LOG, 'info') as log:
                    call.playback.read(1920)
                    lane._finish_speech(state, complete=True)
                    self.assertEqual(self.markers(log), [])

    def test_interrupted_or_incomplete_output_never_emits_marker(self):
        for interrupted in (False, True):
            with self.subTest(interrupted=interrupted):
                call, lane, state = self.fixture()
                with patch.object(d.LOG, 'info') as log:
                    call.playback.read(1920)
                    state['interrupted'] = interrupted
                    lane._finish_speech(state, complete=False)
                    self.assertEqual(self.markers(log), [])

    def test_hard_owner_change_after_drain_cannot_emit_success(self):
        call, lane, state = self.fixture(owned_event=True)
        with patch.object(d.LOG, 'info') as log:
            call.playback.read(1920)
            call.dialog.backend_owner = object()
            lane._finish_speech(state, complete=True)
            self.assertEqual(self.markers(log), [])

    def test_discarded_samples_and_closed_call_cannot_emit_success(self):
        for reason in ('discard', 'close', 'no_lease'):
            with self.subTest(reason=reason):
                call, lane, state = self.fixture()
                with patch.object(d.LOG, 'info') as log:
                    if reason == 'discard':
                        call.playback.interrupt()
                    else:
                        call.playback.read(1920)
                        if reason == 'close':
                            call.closing = True
                        else:
                            state['lease'] = None
                    lane._finish_speech(state, complete=True)
                    self.assertEqual(self.markers(log), [])

    def test_empty_output_cannot_emit_a_positive_completion_marker(self):
        call, lane, state = self.fixture()
        state['accepted_start'] = call.playback.accepted_samples
        state['emitted_start'] = call.playback.emitted_samples
        with patch.object(d.LOG, 'info') as log:
            lane._finish_speech(state, complete=True)
            self.assertEqual(self.markers(log), [])


if __name__ == '__main__':
    unittest.main()
