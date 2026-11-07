"""Native trace qualification fixtures only. No engine or network access."""
import copy
import unittest

from mtp_cost_trace import qualify_trace


def sample(request_id):
    return dict(native_request_id=request_id, speculation=dict(rounds=3,
        head=dict(rounds=3, drafted=5, accepted=4),
        lookup=dict(rounds=0, drafted=0, accepted=0),
        grammar=dict(rounds=0, drafted=0, accepted=0)))


def banner(rule):
    marker = 'cost rule' if rule == 'cost' else 'confidence gate'
    return ('flash_serve: listening on 0.0.0.0:8730, 1 slots x 32768 ctx, '
            f'max_tok 32768, BATCHED greedy or sampled; MTP depth-1 (up to 8, {marker}) native\n')


def line(request_id, bank=True):
    text = (f'req {request_id} spec: 3 rounds 4 accepted; chain 3 rounds 5 drafted 4 accepted; '
            'lookup 0 rounds 0 drafted 0 accepted; grammar 0 rounds 0 drafted 0 accepted; 0 serial;')
    return text + (' list 0 tokens 0 off;' if bank else '') + '\n'


class CostTraceTests(unittest.TestCase):
    def samples(self):
        return [sample(value) for value in range(7, 11)]

    def text(self, rule='cost', bank=True):
        return banner(rule) + line(99) + ''.join(line(value, bank) for value in range(7, 11))

    def test_expected_native_banner_and_four_counter_rows_qualify(self):
        for rule in ('gate', 'cost'):
            with self.subTest(rule=rule):
                result = qualify_trace(self.text(rule), self.samples(), rule)
                self.assertEqual(result['expected_rule'], rule)
                self.assertEqual(result['startup_banner']['count'], 1)
                self.assertEqual(len(result['samples']), 4)
                self.assertIs(result['native_rule_activation_observed'], True)
                self.assertIs(result['per_decision_policy_observed'], False)

    def test_bank_counts_are_optional_and_zero_is_valid(self):
        result = qualify_trace(self.text(bank=False), self.samples(), 'cost')
        self.assertNotIn('list_tokens', result['samples'][0])
        result = qualify_trace(self.text(), self.samples(), 'cost')
        self.assertEqual(result['samples'][0]['list_tokens'], 0)

    def test_banner_missing_wrong_duplicate_or_ambiguous_rejected(self):
        for text in (self.text().replace(banner('cost'), ''), self.text('gate'),
                     self.text() + banner('cost'), self.text() + banner('gate')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                qualify_trace(text, self.samples(), 'cost')

    def test_missing_duplicate_and_drifted_selected_request_rejected(self):
        for text in (self.text().replace(line(7), ''), self.text() + line(7),
                     self.text().replace('chain 3 rounds 5 drafted', 'chain 3 rounds 6 drafted')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                qualify_trace(text, self.samples(), 'cost')

    def test_exact_four_unique_sample_ids_are_required(self):
        for samples in ([], self.samples()[:3], self.samples() + [sample(11)],
                        [sample(7), sample(7), sample(8), sample(9)]):
            with self.subTest(samples=samples), self.assertRaises(ValueError):
                qualify_trace(self.text(), samples, 'cost')

    def test_matching_lookup_or_grammar_activity_is_rejected(self):
        for scope in ('lookup', 'grammar'):
            samples = copy.deepcopy(self.samples())
            for value in samples:
                value['speculation']['rounds'] = 4
                value['speculation'][scope] = dict(rounds=1, drafted=1, accepted=0)
            text = self.text().replace('spec: 3 rounds', 'spec: 4 rounds').replace(
                scope + ' 0 rounds 0 drafted', scope + ' 1 rounds 1 drafted')
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                qualify_trace(text, samples, 'cost')

    def test_legacy_aggregate_is_diagnostic_not_an_API_token_counter(self):
        text = self.text().replace('spec: 3 rounds 4 accepted;', 'spec: 3 rounds 2 accepted;')
        result = qualify_trace(text, self.samples(), 'cost')
        self.assertTrue(all(row['legacy_accepted'] == 2 for row in result['samples']))
        self.assertTrue(all(row['head_accepted'] == 4 for row in result['samples']))

    def test_head_activity_and_corresponding_API_counters_are_reconciled(self):
        for text in (self.text().replace('5 drafted 4 accepted;', '5 drafted 5 accepted;'),
                     self.text().replace('chain 3 rounds 5 drafted', 'chain 0 rounds 0 drafted')):
            with self.subTest(text=text), self.assertRaises(ValueError):
                qualify_trace(text, self.samples(), 'cost')
        with self.assertRaises(ValueError):
            qualify_trace(self.text(), self.samples(), 'drop')


if __name__ == '__main__':
    unittest.main()
