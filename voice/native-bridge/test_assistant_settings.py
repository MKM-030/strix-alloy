"""Offline projection validation and per-call language isolation tests."""
import copy
import importlib
import unittest

try:
    candidate = importlib.import_module('assistant_settings')
except ModuleNotFoundError as error:
    if error.name != 'assistant_settings':
        raise
    candidate = None

SERVICE = '8' * 32
AGENT = 'a' * 32
PROFILE = '4' * 32
_MISSING = object()


def authorized_settings():
    return {'result': {'version': 1, 'authorized_agents': [AGENT], 'assistant_settings': {
        'version': 1, 'service_id': SERVICE, 'context_profile': PROFILE, 'language': 'de-DE',
        'language_selection': {'enabled': True, 'dtmf_enabled': False, 'mode': 'voice', 'languages': [
            {'code': 'de-DE', 'display_name': 'Deutsch', 'language_selection_prompt': 'Deutsch bitte.',
             'dtmf_language_selection_prompt': 'Drücken Sie eins.', 'trigger_phrases': ['Deutsch bitte'],
             'secondary_language_prompt': 'Deutsch gewählt.'},
            {'code': 'en-US', 'display_name': 'English', 'language_selection_prompt': 'English please.',
             'dtmf_language_selection_prompt': 'Press two.', 'trigger_phrases': ['English please'],
             'secondary_language_prompt': 'English selected.'}]},
        'tts': {'voice_profile': 'native-cloud-profile', 'voices': {
            'de-DE': {'voice_id': 'native-de', 'voice_gender': 'female'},
            'en-US': {'voice_id': 'native-en', 'voice_gender': 'male'}}},
        'key_terms': {'de-DE': ['SCC', 'Laptop'], 'en-US': ['ServiceNow']},
        'prompt': {'systemMessage': 'Use the configured policy.', 'introduction': 'Guten Tag.'},
        'vad': {'confidence': 0.75, 'min_volume': 0.03, 'start_secs': 0.12, 'stop_secs': 0.8},
        'behavior': {}}}}


class AssistantSettingsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(candidate, 'Validated assistant settings are not implemented')

    def settings(self, response=_MISSING):
        return candidate.CallSettings.from_authorized_response(
            authorized_settings() if response is _MISSING else response, SERVICE, AGENT)

    def test_authorized_projection_sets_per_call_language_and_native_context(self):
        settings = self.settings()
        self.assertEqual(settings.service_id, SERVICE)
        self.assertEqual(settings.primary_language, 'de-DE')
        self.assertEqual(settings.language, 'de-DE')
        self.assertEqual(settings.selected_language, 'de-DE')
        self.assertEqual(settings.context_profile, PROFILE)
        self.assertEqual(settings.introduction, 'Guten Tag.')
        context = settings.native_context()
        self.assertEqual(context, {
            'interaction_requester_session_language': 'de-DE',
            'interaction_user_language': 'de-DE', 'requester_session_language': 'de-DE',
            'voice_assistant': SERVICE, 'interaction_ai_voice': 'true',
            'global_context_profile': PROFILE})
        self.assertEqual(settings.snapshot()['prompt']['systemMessage'], 'Use the configured policy.')
        self.assertEqual(context['global_context_profile'], PROFILE)
        self.assertNotIn('fixed_skill_route', context)

    def test_only_exact_configured_phrase_switches_current_language(self):
        settings = self.settings()
        for text in ('English', 'I would like English please', 'en-US', 'change language to English'):
            self.assertFalse(settings.select_language(text))
            self.assertEqual(settings.language, 'de-DE')
        self.assertTrue(settings.select_language(' English PLEASE '))
        self.assertEqual(settings.language, 'en-US')
        self.assertEqual(settings.asr_context(), {'language': 'en', 'terms': ['ServiceNow']})
        self.assertEqual(settings.native_context()['requester_session_language'], 'en-US')

    def test_unsupported_language_selection_requires_enabled_multiple_dtmf_languages(self):
        for enabled, mode, count, unsupported in (
                (True, 'dtmf', 2, True), (True, ' DTMF ', 2, True),
                (True, 'dtmf', 1, False), (False, 'dtmf', 2, False),
                (True, 'voice', 2, False), (True, '', 2, False)):
            data = authorized_settings()
            value = data['result']['assistant_settings']
            selection = value['language_selection']
            selection.update(enabled=enabled, mode=mode)
            selection['languages'] = selection['languages'][:count]
            if count == 1:
                value['tts']['voices'].pop('en-US')
                value['key_terms'].pop('en-US')
            with self.subTest(enabled=enabled, mode=mode, count=count):
                self.assertIs(self.settings(data).unsupported_language_selection, unsupported)

    def test_dtmf_only_mode_does_not_accept_or_advertise_voice_selection(self):
        for mode in ('dtmf', 'DTMF', 'Dtmf'):
            data = authorized_settings()
            selection = data['result']['assistant_settings']['language_selection']
            selection['mode'] = mode
            selection['dtmf_enabled'] = True
            settings = self.settings(data)
            with self.subTest(mode=mode):
                self.assertFalse(settings.select_language('English please'))
                self.assertFalse(settings.select_dtmf('2'))
                self.assertEqual(settings.language, 'de-DE')
                self.assertEqual(settings.selection_prompt, '')
                self.assertEqual(settings.unsupported_metadata['language_input_mode'], mode)

    def test_single_language_dtmf_mode_keeps_primary_without_offering_choice(self):
        data = authorized_settings()
        value = data['result']['assistant_settings']
        value['language_selection']['mode'] = 'dtmf'
        value['language_selection']['languages'] = value['language_selection']['languages'][:1]
        value['tts']['voices'].pop('en-US')
        value['key_terms'].pop('en-US')
        settings = self.settings(data)
        self.assertEqual(settings.language, 'de-DE')
        self.assertEqual(settings.selection_prompt, '')
        self.assertFalse(settings.select_language('Deutsch bitte'))
        self.assertEqual(settings.asr_context()['language'], 'de')

    def test_disabled_selection_cannot_switch_and_dtmf_has_no_invented_mapping(self):
        data = authorized_settings()
        selection = data['result']['assistant_settings']['language_selection']
        selection['enabled'] = False
        selection['dtmf_enabled'] = True
        settings = self.settings(data)
        self.assertFalse(settings.select_language('English please'))
        self.assertFalse(settings.select_dtmf('2'))
        selection['enabled'] = True
        settings = self.settings(data)
        self.assertFalse(settings.select_dtmf('2'))
        self.assertEqual(settings.language, 'de-DE')

    def test_native_profile_is_isolated_between_authorized_assistants(self):
        first_data = authorized_settings()
        second_data = authorized_settings()
        second_service = '9' * 32
        second_profile = '5' * 32
        second_data['result']['assistant_settings'].update(
            service_id=second_service, context_profile=second_profile)
        first = self.settings(first_data)
        second = candidate.CallSettings.from_authorized_response(second_data, second_service, AGENT)
        second_data['result']['assistant_settings']['context_profile'] = '6' * 32
        first.native_context()['global_context_profile'] = '7' * 32
        self.assertEqual(first.native_context()['voice_assistant'], SERVICE)
        self.assertEqual(first.native_context()['global_context_profile'], PROFILE)
        self.assertEqual(second.native_context()['voice_assistant'], second_service)
        self.assertEqual(second.native_context()['global_context_profile'], second_profile)
        self.assertNotIn('global_deployment_id', first.native_context())
        self.assertNotIn('global_deployment_id', second.native_context())

    def test_instances_and_returned_context_are_independent_copies(self):
        data = authorized_settings()
        first = self.settings(data)
        second = self.settings(data)
        data['result']['assistant_settings']['key_terms']['de-DE'].append('mutated source')
        first.asr_context()['terms'].append('mutated output')
        first.snapshot()['behavior']['mutated'] = True
        first.select_language('English please')
        self.assertEqual(second.language, 'de-DE')
        self.assertEqual(second.asr_context(), {'language': 'de', 'terms': ['SCC', 'Laptop']})
        self.assertEqual(second.snapshot()['behavior'], {})

    def test_native_vad_timing_is_mapped_without_using_confidence_as_rms(self):
        settings = self.settings()
        self.assertEqual(settings.vad_start_ms, 120)
        self.assertEqual(settings.vad_stop_ms, 800)
        self.assertIsNone(settings.max_call_seconds)
        self.assertEqual(settings.unsupported_metadata['vad'], {'confidence': 0.75, 'min_volume': 0.03})
        self.assertEqual(settings.unsupported_metadata['tts']['voices']['de-DE']['voice_id'], 'native-de')
        self.assertNotIn('voice', settings.asr_context())

    def test_empty_optional_source_values_do_not_become_host_defaults(self):
        data = authorized_settings()
        value = data['result']['assistant_settings']
        value['prompt'] = {}
        value['vad'] = {}
        value['tts'] = {}
        value['key_terms'] = {}
        settings = self.settings(data)
        self.assertEqual(settings.introduction, '')
        self.assertIsNone(settings.vad_start_ms)
        self.assertIsNone(settings.vad_stop_ms)
        self.assertEqual(settings.asr_context(), {'language': 'de', 'terms': []})

    def test_envelope_requires_versioned_projection_and_required_agent(self):
        invalid = [None, {}, {'result': [AGENT]}, {'error': 'denied', **authorized_settings()}]
        for field, bad in [('version', 2), ('version', True), ('authorized_agents', []),
                           ('authorized_agents', [AGENT, 'bad']), ('authorized_agents', ['b' * 32]),
                           ('assistant_settings', None)]:
            data = authorized_settings()
            data['result'][field] = bad
            invalid.append(data)
        for response in invalid:
            with self.subTest(response=response):
                with self.assertRaises(ValueError):
                    self.settings(response)

    def test_projection_is_bound_to_requested_service_and_valid_profile(self):
        for field, value in [('version', 2), ('version', True), ('service_id', 'f' * 32),
                             ('context_profile', ''), ('context_profile', 'x' * 32)]:
            data = authorized_settings()
            data['result']['assistant_settings'][field] = value
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValueError):
                    self.settings(data)
        for field in ('language_selection', 'tts', 'key_terms', 'prompt', 'vad', 'behavior'):
            data = authorized_settings()
            del data['result']['assistant_settings'][field]
            with self.subTest(missing=field):
                with self.assertRaises(ValueError):
                    self.settings(data)

    def test_language_configuration_rejects_malformed_duplicate_and_missing_primary(self):
        for bad in ('', 'not a language', 'de_DE', 'x', 'de-123456789', 'en--US'):
            data = authorized_settings()
            data['result']['assistant_settings']['language'] = bad
            with self.subTest(language=bad):
                with self.assertRaises(ValueError):
                    self.settings(data)
        for mutate in (
                lambda v: v.update(language='fr-FR'),
                lambda v: v['language_selection'].update(languages=[]),
                lambda v: v['language_selection'].update(languages=v['language_selection']['languages'] * 9),
                lambda v: v['language_selection']['languages'][1].update(code='de-de'),
                lambda v: v['language_selection'].update(enabled='true'),
                lambda v: v['language_selection']['languages'][0].update(trigger_phrases='Deutsch'),
                lambda v: v['language_selection']['languages'][0].update(trigger_phrases=['shared']),
        ):
            data = authorized_settings()
            mutate(data['result']['assistant_settings'])
            if data['result']['assistant_settings']['language_selection']['languages'] and data['result']['assistant_settings']['language_selection']['languages'][0].get('trigger_phrases') == ['shared']:
                data['result']['assistant_settings']['language_selection']['languages'][1]['trigger_phrases'] = ['SHARED']
            with self.subTest(configuration=data):
                with self.assertRaises(ValueError):
                    self.settings(data)

    def test_only_explicitly_configured_goodbye_can_be_spoken(self):
        data = authorized_settings()
        value = data['result']['assistant_settings']
        value['behavior'] = {'goodbye_message': 'Goodbye.'}
        self.assertEqual(self.settings(data).configured_goodbye, '')
        value['behavior_sources'] = {'goodbye_message': 'native_default'}
        self.assertEqual(self.settings(data).configured_goodbye, '')
        value['behavior']['goodbye_message'] = 'Auf Wiedersehen.'
        value['behavior_sources']['goodbye_message'] = 'configured'
        self.assertEqual(self.settings(data).configured_goodbye, 'Auf Wiedersehen.')

    def test_unlocalized_defaults_and_filler_delay_remain_explicit_metadata(self):
        data = authorized_settings()
        value = data['result']['assistant_settings']
        value['behavior'] = {'retry_prefix': 'Please try again.', 'goodbye_message': 'Goodbye.',
                             'filler_message_delay_in_seconds': '15'}
        value['behavior_sources'] = {'retry_prefix': 'native_default',
                                    'goodbye_message': 'native_default',
                                    'filler_message_delay_in_seconds': 'configured'}
        settings = self.settings(data)
        metadata = settings.unsupported_metadata
        self.assertEqual(metadata['unlocalized_native_defaults'], ['retry_prefix', 'goodbye_message'])
        self.assertEqual(metadata['behavior']['filler_message_delay_in_seconds'], '15')
        metadata['unlocalized_native_defaults'].clear()
        metadata['behavior']['filler_message_delay_in_seconds'] = 'mutated'
        self.assertEqual(settings.unsupported_metadata['unlocalized_native_defaults'], ['retry_prefix', 'goodbye_message'])
        self.assertEqual(settings.unsupported_metadata['behavior']['filler_message_delay_in_seconds'], '15')
        value['behavior_sources']['goodbye_message'] = 'configured'
        self.assertEqual(self.settings(data).unsupported_metadata['unlocalized_native_defaults'], ['retry_prefix'])

    def test_optional_provenance_remains_bounded_and_private(self):
        data = authorized_settings()
        value = data['result']['assistant_settings']
        value['language_source'] = 'configured'
        value['behavior'] = {'goodbye_message': 'Goodbye.'}
        value['behavior_sources'] = {'goodbye_message': 'native_default'}
        settings = self.settings(data)
        self.assertEqual(settings.snapshot()['language_source'], 'configured')
        self.assertEqual(settings.snapshot()['behavior_sources'], {'goodbye_message': 'native_default'})
        self.assertNotIn('language_source', settings.native_context())
        for bad in ({'arbitrary_secret': 'configured'}, {'goodbye_message': 'untrusted'}):
            value['behavior_sources'] = bad
            with self.subTest(sources=bad):
                with self.assertRaises(ValueError):
                    self.settings(data)
        value['behavior_sources'] = {}
        value['language_source'] = 'untrusted'
        with self.assertRaises(ValueError):
            self.settings(data)

    def test_nullable_native_secondary_prompt_is_preserved(self):
        data = authorized_settings()
        data['result']['assistant_settings']['language_selection']['languages'][0]['secondary_language_prompt'] = None
        settings = self.settings(data)
        self.assertIsNone(settings.snapshot()['language_selection']['languages'][0]['secondary_language_prompt'])

    def test_single_language_does_not_ask_a_language_selection_question(self):
        data = authorized_settings()
        value = data['result']['assistant_settings']
        value['language_selection']['languages'] = value['language_selection']['languages'][:1]
        value['tts']['voices'].pop('en-US')
        value['key_terms'].pop('en-US')
        self.assertEqual(self.settings(data).selection_prompt, '')

    def test_native_timers_and_unsupported_vad_timing_are_explicit(self):
        data = authorized_settings()
        value = data['result']['assistant_settings']
        value['behavior'] = {'user_inactivity_threshold_in_seconds': '30',
                             'filler_message_delay_in_seconds': '15'}
        settings = self.settings(data)
        self.assertEqual(settings.inactivity_seconds, 30)
        self.assertEqual(settings.filler_delay_seconds, 15)
        for duration in ('0', '-1', '3601', 'nonsense', 'NaN'):
            value['behavior']['user_inactivity_threshold_in_seconds'] = duration
            settings = self.settings(data)
            self.assertIsNone(settings.inactivity_seconds)
            self.assertEqual(settings.unsupported_metadata['behavior']['user_inactivity_threshold_in_seconds'], duration)
        value['vad']['start_secs'] = 0
        value['vad']['stop_secs'] = .1
        settings = self.settings(data)
        self.assertIsNone(settings.vad_start_ms)
        self.assertIsNone(settings.vad_stop_ms)
        self.assertEqual(settings.unsupported_metadata['vad']['start_secs'], 0)
        self.assertEqual(settings.unsupported_metadata['vad']['stop_secs'], .1)

    def test_native_behavior_is_retained_and_call_duration_obeys_host_ceiling(self):
        for minutes, seconds in [('2.5', 150), ('120', 3600)]:
            data = authorized_settings()
            data['result']['assistant_settings']['behavior'] = {
                'max_call_duration_in_minutes': minutes, 'persist_context_data': 'false',
                'goodbye_message': 'Auf Wiedersehen.', 'voice_max_retries': '0'}
            settings = self.settings(data)
            self.assertEqual(settings.max_call_seconds, seconds)
            self.assertEqual(settings.snapshot()['behavior']['persist_context_data'], 'false')
            self.assertEqual(set(settings.native_context()), {
                'interaction_requester_session_language', 'interaction_user_language',
                'requester_session_language', 'voice_assistant', 'interaction_ai_voice',
                'global_context_profile'})
        for duration in ('NaN', 'inf', '-1', '0', 'nonsense'):
            data = authorized_settings()
            data['result']['assistant_settings']['behavior']['max_call_duration_in_minutes'] = duration
            with self.subTest(duration=duration):
                with self.assertRaises(ValueError):
                    self.settings(data)

    def test_selection_prompt_uses_only_actionable_native_voice_prompt(self):
        data = authorized_settings()
        self.assertEqual(self.settings(data).selection_prompt, 'Deutsch bitte.')
        data['result']['assistant_settings']['language_selection']['dtmf_enabled'] = True
        self.assertEqual(self.settings(data).selection_prompt, 'Deutsch bitte.')
        data['result']['assistant_settings']['language_selection']['languages'][0]['language_selection_prompt'] = ''
        settings = self.settings(data)
        self.assertEqual(settings.selection_prompt, '')
        self.assertEqual(settings.unsupported_metadata['dtmf_language_selection_prompts']['de-DE'], 'Drücken Sie eins.')
        data['result']['assistant_settings']['language_selection']['enabled'] = False
        self.assertEqual(self.settings(data).selection_prompt, '')

    def test_bounded_maps_strings_and_finite_numeric_fields(self):
        for section, field, bad in (
                ('prompt', 'introduction', 'x' * 20000),
                ('prompt', 'systemMessage', {'unexpected': 'object'}),
                ('vad', 'start_secs', float('nan')), ('vad', 'stop_secs', float('inf')),
                ('vad', 'confidence', True), ('vad', 'start_secs', -1),
                ('vad', 'start_secs', 10 ** 400),
                ('tts', 'voice_profile', ['not', 'scalar'])):
            data = authorized_settings()
            data['result']['assistant_settings'][section][field] = bad
            with self.subTest(section=section, field=field):
                with self.assertRaises(ValueError):
                    self.settings(data)
        for key, value in [('de-DE', ['x' * 10000]), ('fr-FR', ['extra']), ('de-DE', 'not-list')]:
            data = authorized_settings()
            data['result']['assistant_settings']['key_terms'][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    self.settings(data)
        data = authorized_settings()
        data['result']['assistant_settings']['behavior'] = {'arbitrary_secret': 'hidden'}
        with self.assertRaises(ValueError):
            self.settings(data)


if __name__ == '__main__':
    unittest.main()
