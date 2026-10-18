"""Boundary tests for preserving the historical SCC locale instructions."""
from copy import deepcopy
from pathlib import Path
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scc_voice_locale import restore_scc_voice_locale


SUFFIX_FILE = Path(__file__).resolve().parents[2] / 'voice/servicenow/evidence/scc-request-transformer-locale-suffix-20261013.txt'
SUFFIX = SUFFIX_FILE.read_text(encoding='utf-8')
ROUTE = '/v1/chat/completions'
TITLE = 'SCC Laptop Onboarding Voice'
PROMPT = ('agent_name: ' + TITLE + '\n'
          'persona: Antworte auf Deutsch.\n'
          'conversation_history: Bitte einen Laptop fuer den Mitarbeiter bestellen.\n'
          'action_id: fixture_unchanged; reply: reply; transition_message: transition_message;\n'
          'English example: I can help you with that.\n'
          'Require explicit order confirmation; never repeat submission automatically.')


def request(role='system', content=PROMPT, **extras):
    return dict(model='halogen-v2', messages=[{'role': role, 'content': content,
                'name': 'provider', 'metadata': {'preserve': True}}],
                max_tokens=4096, temperature=0, stream=False,
                response_format={'type': 'json_object'}, **extras)


class LocaleBoundaryTests(unittest.TestCase):
    def apply(self, body, route=ROUTE, demo='halogen-v2'):
        return restore_scc_voice_locale(body, route=route, demo_model=demo)

    def test_selected_flat_system_prompt_gets_existing_suffix_without_changing_prefix(self):
        body = request()
        before = deepcopy(body)
        observed = self.apply(body)
        expected = deepcopy(before)
        expected['messages'][0]['content'] += SUFFIX
        self.assertEqual(observed, expected)
        self.assertEqual(body, before, 'The caller request must remain intact')

    def test_historic_flat_user_shape_gets_same_locale_suffix(self):
        observed = self.apply(request(role='user'))
        self.assertEqual(observed['messages'][0]['content'], PROMPT + SUFFIX)

    def test_explicit_other_language_request_is_preserved_and_has_priority(self):
        prompt = PROMPT + '\nuser: Please answer this conversation in English.'
        observed = self.apply(request(content=prompt))
        self.assertEqual(observed['messages'][0]['content'], prompt + SUFFIX)
        self.assertIn('Eine ausdrueckliche andere Sprachwahl des Benutzers hat Vorrang.',
                      observed['messages'][0]['content'])

    def test_existing_locale_override_is_not_appended_twice(self):
        body = request(content=PROMPT + SUFFIX)
        self.assertIs(self.apply(body), body)
        self.assertEqual(self.apply(self.apply(request())), self.apply(request()))

    def test_existing_marker_without_closing_tag_is_not_replaced_or_repaired(self):
        body = request(content=PROMPT + '\n<scc_voice_locale_override_20261013>custom')
        self.assertIs(self.apply(body), body)

    def test_agent_marker_is_required(self):
        for prompt in ('Antragsformular ausfuellen.', 'General IT help', 'Laptop order'):
            with self.subTest(prompt=prompt):
                body = request(content=prompt)
                self.assertIs(self.apply(body), body)

    def test_other_models_routes_and_disabled_demo_are_untouched(self):
        for model, route, demo in (
            ('halogen-v2', ROUTE, ''), ('halogen-v2', ROUTE, 'different'),
            ('halogen-qwen3.8-flash-next', ROUTE, 'halogen-v2'),
            ('other', ROUTE, 'halogen-v2'),
            ('halogen-v2', '/v1/responses', 'halogen-v2')):
            with self.subTest(model=model, route=route, demo=demo):
                body = request()
                body['model'] = model
                self.assertIs(self.apply(body, route, demo), body)

    def test_native_tools_and_ambiguous_tools_shapes_are_untouched(self):
        for tools in ([{'type': 'function', 'function': {'name': 'fixture'}}], {}, False, ''):
            with self.subTest(tools=tools):
                body = request(tools=tools)
                self.assertIs(self.apply(body), body)

    def test_explicit_empty_tools_list_has_no_tool_contract_to_modify(self):
        observed = self.apply(request(tools=[]))
        self.assertEqual(observed['messages'][0]['content'], PROMPT + SUFFIX)
        self.assertEqual(observed['tools'], [])

    def test_multi_message_and_multimodal_contracts_are_untouched(self):
        shapes = [
            [{'role': 'system', 'content': PROMPT}, {'role': 'user', 'content': 'fixture'}],
            [{'role': 'system', 'content': [{'type': 'text', 'text': PROMPT}]}],
            [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'fixture'}}]}],
            [{'role': 'assistant', 'content': PROMPT}],
            [{'role': 'tool', 'content': PROMPT}],
            [{'role': 'system', 'content': {'text': PROMPT}}],
            [{'role': 'system', 'content': None}],
            [], None,
        ]
        for messages in shapes:
            with self.subTest(messages=messages):
                body = request()
                body['messages'] = messages
                self.assertIs(self.apply(body), body)


if __name__ == '__main__':
    unittest.main()
