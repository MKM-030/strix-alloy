"""Spoken-number source equivalence through the real local output guard.

The two human calls retained recognized date words, not rejected candidate text.
Candidate sentences below are synthetic and do not reconstruct that missing text.
"""
import unittest

from native_duplex import NativeDuplex
from test_native_duplex import FakeCall
from test_native_duplex_claim_release import SentenceModel


class SpokenNumberGroundingTests(unittest.IsolatedAsyncioTestCase):
    async def check_release(self, source, answer, expected):
        call = FakeCall()
        lane = NativeDuplex(call)
        model = SentenceModel([answer])
        lane.conversation = model
        lane._observe_raw(source)
        turn = (0, source, 1, 'number-input', 0)
        try:
            await lane._general_help(turn, lane.epoch)
            released = [item.text for item in lane._outputs]
            self.assertEqual(answer in released, expected, (source, answer, released))
            self.assertEqual(model.inputs, [source])
            if expected:
                self.assertFalse(model.closed)
                self.assertFalse(lane._model_failed)
        finally:
            call.closed = True
            await lane.close()

    async def test_recognized_spelled_year_can_be_repeated_as_digits(self):
        await self.check_release('Erster November zweitausendsechsundzwanzig.',
            'Meinen Sie den 1. November 2026?', True)

    async def test_full_spoken_date_can_use_padded_german_date_notation(self):
        await self.check_release('Der erste November zweitausendsechsundzwanzig.',
            'Meinen Sie den 01.11.2026?', True)

    async def test_explicit_cardinal_is_equivalent_without_an_extra_model_request(self):
        for source, value in [('zwei', '2'), ('zwölf', '12'), ('fünfundzwanzig', '25'),
                              ('einhundertdrei', '103'), ('zweitausendsechsundzwanzig', '2026')]:
            with self.subTest(source=source):
                await self.check_release('Ich habe ' + source + ' genannt.', 'Meinen Sie ' + value + '?', True)

    async def test_corrupted_asr_year_is_not_silently_repaired_to_2026(self):
        await self.check_release('Der erste November zweihundertzweiundsechzig.',
            'Meinen Sie den 1. November 2026?', False)

    async def test_article_does_not_authorize_a_new_numeric_assertion(self):
        await self.check_release('Eine Lieferung bitte.', 'Die Anzahl ist 1.', False)

    async def test_unmentioned_price_still_rejects(self):
        await self.check_release('Erster November zweitausendsechsundzwanzig.',
            'Das kostet 749 Euro.', False)

    async def test_ordinal_homonym_outside_a_date_is_not_numeric_evidence(self):
        await self.check_release('Ich achte auf die Lieferung.', 'Die Anzahl ist 8.', False)

    async def test_month_name_without_a_day_does_not_license_its_number(self):
        await self.check_release('November ist der Name.', 'Die Anzahl ist 11.', False)

    async def test_numeric_identifier_zeroes_are_not_discarded(self):
        await self.check_release('Die Kennung ist 00123.', 'Die Kennung lautet 123.', False)

    async def test_existing_exact_digit_source_still_works(self):
        await self.check_release('Der Termin ist 12.11.2026.',
            'Meinen Sie den 12.11.2026?', True)

    async def test_other_hard_guards_are_not_masked_by_number_equivalence(self):
        for suffix in (' https://example.invalid', ' <intern>', ' analysis', ' ' + 'c' * 32):
            with self.subTest(suffix=suffix):
                await self.check_release('Erster November zweitausendsechsundzwanzig.',
                    'Meinen Sie den 1. November 2026?' + suffix, False)


if __name__ == '__main__':
    unittest.main()
