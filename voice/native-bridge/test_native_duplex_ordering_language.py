"""Ordering grammar: noncompletion language versus unsupported actual claims."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from native_duplex import NativeDuplex
from test_native_duplex import FakeCall


class OrderingLanguageTests(unittest.TestCase):
    def admitted(self, text, source_event=None):
        call = FakeCall()
        lane = NativeDuplex(call)
        identity = SimpleNamespace(server_session_id='offline-session', socket_instance='offline-socket')
        lane.conversation = SimpleNamespace(is_current=lambda candidate: candidate is identity)
        turn = (0, 'Welche Unterstützung bieten Sie?', 1, 'offline-request', 0)
        lane._observe_raw(turn[1])
        key, snapshot, observation = lane._dialogue_snapshot(turn, lane.epoch)
        if source_event is not None:
            fact = {name: key[name] for name in ('call_id', 'task_id', 'task_revision',
                    'context_revision', 'observation_revision')}
            fact.update(source_event=source_event, text='Der Laptop wurde bestellt.',
                        evidence_id='offline-finding', sequence=1, observed_at=0, superseded=False)
            snapshot['public_findings'] = (fact,)
        return bool(lane._admit_conversation(SimpleNamespace(text=text, identity=identity),
                                             turn, lane.epoch, observation, snapshot))

    def test_clear_noncompletion_grammar_is_allowed(self):
        for text in (
            'Es wurde noch nichts bestellt.',
            'Der Laptop wurde noch nicht bestellt.',
            'Ich habe nichts bestellt.',
            'Ich habe noch nicht bestellt.',
            'Ein Laptop kann über ServiceNow bestellt werden.',
            'Der Laptop könnte nach Ihrer Freigabe bestellt werden.',
            'Ich kann erklären, wie ein Laptop bestellt wird.',
            'Wir besprechen, ob ein Laptop bestellt werden soll.',
        ):
            with self.subTest(text=text):
                self.assertTrue(self.admitted(text))

    def test_positive_ambiguous_and_scope_reversing_language_stays_held(self):
        for text in (
            'Ich habe den Laptop bestellt.', 'Der Laptop wurde bestellt.',
            'Der Laptop ist bereits bestellt.', 'Icb habe den Laptop bestellt.',
            'Ich habe nicht nur den Laptop bestellt.',
            'Der Laptop wurde nicht nur bestellt, sondern auch bezahlt.',
            'Nicht nur der Laptop wurde bestellt.',
            'Es wurde nicht nichts bestellt.', 'Es wurde fast nichts bestellt.',
            'Es wurde nichts außer dem Laptop bestellt.',
            'Es wurde nichts bestellt, außer einem Laptop.',
            'Es wurde nichts bestellt, abgesehen von einem Laptop.',
            'Es wurde nichts bestellt, aber den Laptop schon.',
            'Es wurde nichts bestellt, es sei denn, Sie zählen den Laptop.',
            'Der Laptop wurde nicht bestellt, der Monitor schon.',
            'Der Laptop wurde nicht bestellt, sondern der Monitor.',
            'Nicht bestellt wurde lediglich der Monitor.',
            'Der Laptop wurde nicht von mir bestellt.',
            'Der Laptop wurde nicht gestern bestellt.',
            'Der Laptop wurde nicht hier bestellt.',
            'Der Laptop wurde nicht vollständig bestellt.',
            'Der Laptop wurde nicht erst heute bestellt.',
            'Der Laptop wurde kein bisschen anders bestellt.',
            'Der Laptop wurde in keiner Weise anders bestellt.',
            'Ich habe den Laptop mit keinem Zweifel bestellt.',
            'Der Laptop wurde ohne keinen Zweifel bestellt.',
            'Der Laptop wurde keineswegs nicht bestellt.',
            'Es wurde nie nichts bestellt.',
            'Der Laptop wurde niemals nicht bestellt.',
            'Wenn auch der Laptop bestellt wurde, fehlt die Adresse.',
            'Falls der Laptop schon bestellt wurde, können wir die Lieferadresse prüfen.',
            'Wenn ein Laptop bestellt wird, übernimmt ServiceNow die Ausführung.',
            'Falls das hilft: Ich habe den Laptop bestellt.',
            'Wenn es hilft - der Laptop ist bestellt.',
            'Es wurde so gut wie nichts bestellt.',
            'Es wurde nahezu nichts bestellt.',
            "Die Aussage 'Es wurde nichts bestellt' ist falsch.",
            'Ich habe noch keinen Laptop bestellt.',
            'Bislang wurde kein neuer Laptop bestellt.',
            'Der Laptop muss bestellt worden sein.',
            'Es ist nicht so, dass nichts bestellt wurde.',
            'Es ist falsch, dass nichts bestellt wurde.',
            'Es ist unmöglich, dass nichts bestellt wurde.',
            'Auch wenn der Laptop bestellt wurde, fehlt die Adresse.',
            'Obwohl der Laptop bestellt wurde, fehlt die Adresse.',
            'Nachdem der Laptop bestellt wurde, folgt die Lieferung.',
            'Wenn Sie bereit sind, habe ich den Laptop bestellt.',
            'Ich habe den Laptop bestellt, falls alles klappt.',
            'Es wurde noch nichts bestellt; ich habe den Laptop jetzt bestellt.',
            'Es wurde noch nichts bestellt und der Laptop wurde bestellt.',
        ):
            with self.subTest(text=text):
                self.assertFalse(self.admitted(text))

    def test_free_text_findings_never_authorize_a_positive_local_completion_claim(self):
        for source in ('complete_public_va_reply', 'servicenow_processing_presentation',
                       'complete_emitted_assistant_speech'):
            with self.subTest(source=source):
                self.assertFalse(self.admitted('Der Laptop wurde bestellt.', source))

    def test_safe_ordering_clause_does_not_hide_other_existing_guards(self):
        for text in ('Es wurde noch nichts bestellt. Das ist bestätigt.',
                     'Es wurde noch nichts bestellt. https://example.invalid',
                     'Es wurde noch nichts bestellt. Die Nummer ist 749.',
                     'Es wurde noch nichts bestellt. analysis'):
            with self.subTest(text=text):
                self.assertFalse(self.admitted(text))


if __name__ == '__main__':
    unittest.main()
