"""Literal German assertion/grammar counterexamples for the pure wording guard."""
import unittest

from conversation_claims import unproven_storage_or_check_claim


class ClaimTests(unittest.TestCase):
    def test_comma_enumerations_do_not_hide_storage_claims(self):
        for text in (
                'Ich habe mir den Namen Mara Testfeld, den Lieferort Hamburg und das Eintrittsdatum notiert.',
                'Ich habe Name, Lieferort und Eintrittsdatum notiert.',
                'Wir haben den Namen, die Kostenstelle und den Lieferort gespeichert.',
                'Der Name, die Kostenstelle und der Lieferort wurden geprüft.'):
            with self.subTest(text=text):
                self.assertTrue(unproven_storage_or_check_claim(text))

    def test_comma_enumeration_support_does_not_join_complement_clauses_into_claims(self):
        for text in (
                'Ich habe verstanden, dass die Angaben gespeichert sind.',
                'Ich habe gefragt, ob die Angaben gespeichert sind.',
                'Ich habe gefragt, wie die Angaben gespeichert werden.'):
            with self.subTest(text=text):
                self.assertFalse(unproven_storage_or_check_claim(text))

    def test_fronted_condition_preserves_future_passive_without_excusing_completed_claims(self):
        for text in (
                'Wenn Sie einverstanden sind, werden die Angaben gespeichert.',
                'Falls Sie einverstanden sind, wird der Lieferort gespeichert.',
                'Sofern die Freigabe vorliegt, dann werden die Angaben geprüft.',
                'Wenn die Freigabe vorliegt, werden Name, Lieferort und Eintrittsdatum gespeichert.'):
            with self.subTest(text=text):
                self.assertFalse(unproven_storage_or_check_claim(text))
        for text in (
                'Wenn Sie einverstanden sind, habe ich die Angaben gespeichert.',
                'Wenn Sie einverstanden sind, werden die Angaben gespeichert, ich habe den Namen notiert.'):
            with self.subTest(text=text):
                self.assertTrue(unproven_storage_or_check_claim(text))

    def test_clear_first_person_or_passive_claims_are_detected(self):
        for text in (
                'Danke, ich habe mir den Namen Mara Testfeld und den Lieferort Hamburg notiert.',
                'Danke, ich habe „Mara Testfeld“ als Namen notiert.',
                'Ich habe Ihre Angaben gespeichert.', 'Ich habe die Angaben bereits geprüft.',
                'Ich hatte den Lieferort notiert.', 'Die Angaben habe ich gespeichert.',
                'Wir haben die Angaben geprüft.', 'Die Angaben haben wir notiert.',
                'Ihre Angaben wurden gespeichert.', 'Der Lieferort wurde notiert.',
                'Die Angaben sind bereits geprüft.', 'Der Name ist notiert.',
                'Die Daten werden gespeichert.', 'Die Daten waren gespeichert.',
                'Ich habe nicht nur den Namen gespeichert.',
                'Ich habe nichts gespeichert. Ich habe den Namen notiert.',
                'Sie sagten: „Ich habe es gespeichert.“ Ich habe Ihre Angaben geprüft.'):
            with self.subTest(text=text):
                self.assertTrue(unproven_storage_or_check_claim(text))

    def test_negatives_questions_and_infinitives_are_not_affirmative_claims(self):
        for text in (
                'Ich habe nichts gespeichert.', 'Ich habe Ihre Angaben nicht gespeichert.',
                'Ich habe die Angaben noch nicht geprüft.', 'Ich habe keine Daten gespeichert.',
                'Ich habe niemals etwas notiert.', 'Wir haben keinerlei Daten gespeichert.',
                'Die Angaben wurden nicht gespeichert.', 'Es wurde nichts notiert.',
                'Die Angaben sind nicht geprüft.', 'Soll ich das speichern?',
                'Habe ich die Angaben gespeichert?', 'Wurden die Angaben geprüft?',
                'Ich kann die Angaben für dieses Gespräch verwenden.',
                'Ich kann die Angaben speichern.', 'Die Angaben können geprüft werden.',
                'Um die Angaben zu prüfen, brauche ich noch die Kostenstelle.',
                'Ich kann nicht bestätigen, dass die Angaben gespeichert wurden.'):
            with self.subTest(text=text):
                self.assertFalse(unproven_storage_or_check_claim(text))

    def test_quoted_user_explanation_is_allowed_but_quoted_name_does_not_hide_own_claim(self):
        for opening, closing in (('„','“'), ('“','”'), ('«','»'), ('"','"'),
                                  ("'","'"), ('‚','‘'), ('‘','’')):
            with self.subTest(opening=opening):
                self.assertFalse(unproven_storage_or_check_claim(
                    f'Sie sagten: {opening}Ich habe es gespeichert.{closing} Das kann ich nicht bestätigen.'))
                self.assertTrue(unproven_storage_or_check_claim(
                    f'Danke, ich habe {opening}Mara{closing} als Namen notiert.'))

    def test_modal_future_or_conditional_plans_are_not_reported_as_results(self):
        for text in (
                'Der Lieferort ist Hamburg und muss noch geprüft werden.',
                'Wir haben noch Angaben zu erfassen bevor diese geprüft werden.',
                'Die Angaben werden später geprüft werden.',
                'Falls diese Angaben noch fehlen, wird zunächst die Zuständigkeit geprüft werden.',
                'Die Angaben werden geprüft, sobald die Freigabe vorliegt.',
                'Die Angaben werden möglicherweise geprüft.',
                'Die Angaben müssen geprüft werden.',
                'Wenn die Angaben geprüft sind, können wir fortfahren.',
                'Die Angaben sind noch zu prüfen.'):
            with self.subTest(text=text):
                self.assertFalse(unproven_storage_or_check_claim(text))


if __name__ == '__main__':
    unittest.main()
