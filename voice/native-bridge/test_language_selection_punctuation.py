"""Exact configured language choices tolerate terminal ASR punctuation only."""
import unittest
from assistant_settings import CallSettings
from test_assistant_settings import authorized_settings, SERVICE, AGENT


class LanguageSelectionPunctuationTests(unittest.TestCase):
    def settings(self, data=None):
        return CallSettings.from_authorized_response(
            authorized_settings() if data is None else data, SERVICE, AGENT)

    def test_terminal_sentence_punctuation_keeps_exact_configured_language_choice(self):
        for text in ('English please.', 'English please!', 'English please?',
                     'English please…', 'English please。', 'English please！',
                     'English please?!', 'English please.”'):
            with self.subTest(text=text):
                settings = self.settings()
                self.assertTrue(settings.select_language(text))
                self.assertEqual(settings.language, 'en-US')
                self.assertEqual(settings.native_context()['requester_session_language'], 'en-US')
                self.assertEqual(settings.asr_context()['language'], 'en')

    def test_normalization_is_symmetric_for_the_configured_phrase(self):
        data = authorized_settings()
        data['result']['assistant_settings']['language_selection']['languages'][1]['trigger_phrases'] = ['English please!']
        for text in ('English please', 'English please.', '  English please? '):
            with self.subTest(text=text):
                self.assertTrue(self.settings(data).select_language(text))

    def test_case_and_whitespace_normalization_preserves_whole_phrase_comparison(self):
        settings = self.settings()
        self.assertTrue(settings.select_language('  ENGLISH   PLEASE.  '))
        self.assertEqual(settings.language, 'en-US')

    def test_extra_intent_or_substring_never_switches_language(self):
        for text in ('I said English please.', 'English please. Order a laptop.',
                     'English please and order a laptop.', 'English please, then create a request.',
                     'English please+.', 'English', 'en-US'):
            with self.subTest(text=text):
                settings = self.settings()
                self.assertFalse(settings.select_language(text))
                self.assertEqual(settings.language, 'de-DE')

    def test_internal_punctuation_is_preserved(self):
        data = authorized_settings()
        data['result']['assistant_settings']['language_selection']['languages'][1]['trigger_phrases'] = ['U.S. English']
        self.assertTrue(self.settings(data).select_language('U.S. English.'))
        self.assertFalse(self.settings(data).select_language('US English.'))
        self.assertFalse(self.settings().select_language('Eng.lish please.'))

    def test_disabled_or_dtmf_selection_still_cannot_switch(self):
        for enabled, mode in ((False, 'voice'), (True, 'dtmf')):
            data = authorized_settings()
            data['result']['assistant_settings']['language_selection'].update(enabled=enabled, mode=mode)
            settings = self.settings(data)
            self.assertFalse(settings.select_language('English please.'))
            self.assertEqual(settings.language, 'de-DE')

    def test_normalized_colliding_configured_phrases_are_rejected(self):
        data = authorized_settings()
        languages = data['result']['assistant_settings']['language_selection']['languages']
        languages[0]['trigger_phrases'] = ['English please']
        languages[1]['trigger_phrases'] = ['  English   PLEASE! ']
        with self.assertRaises(ValueError):
            self.settings(data)

    def test_punctuation_only_configured_phrase_is_rejected(self):
        data = authorized_settings()
        data['result']['assistant_settings']['language_selection']['languages'][1]['trigger_phrases'] = ['...?!']
        with self.assertRaises(ValueError):
            self.settings(data)


if __name__ == '__main__':
    unittest.main()
