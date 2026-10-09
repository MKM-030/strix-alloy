"""Source-prepared CPU checks. Root owns execution; these are not result data."""
import copy
import unittest

import numpy as np
import selector_policy as policy
from causal_width import project


def row():
    return dict(source="neural", attempted=2, accepted_prefix=1,
                context_available=True, context_total=6,
                context_suffix=[12, 21, 12, 34, 34, 55], current_id=55,
                opening_id=8, model_position=6, stock_width=2,
                native_allowance=2, survival_labels=[1, 0],
                native_counter_deltas=dict(neural_rounds=1, neural_drafted=2,
                    neural_accepted=1, pld_rounds=0, pld_drafted=0, pld_accepted=0))


class SelectorPolicyChecks(unittest.TestCase):
    def test_no_outcome_or_offer_feature_leak(self):
        first = row()
        second = copy.deepcopy(first)
        second.update(accepted_prefix=0, survival_labels=[0, 0],
                      offer_ids=[999, 1000], observed_begin_to_outcome_ns=12345,
                      transported_delta=500, request_id="another-request")
        second["native_counter_deltas"]["neural_accepted"] = 0
        np.testing.assert_array_equal(policy.features(first), policy.features(second))
        self.assertEqual(policy.features(first).shape, (64,))

    def test_unattempted_pld_and_censoring_excluded(self):
        for mutation, reason in ((dict(source="pld"), "source"),
                                 (dict(attempted=1), "unattempted_horizon"),
                                 (dict(censored=True), "censored"),
                                 (dict(stock_width=1), "native_ineligible"),
                                 (dict(context_available=False), "history_unavailable")):
            candidate = row()
            candidate.update(mutation)
            self.assertEqual(policy.exclusion(candidate), reason)

    def test_label_counter_mismatch_rejected(self):
        candidate = row()
        candidate["accepted_prefix"] = 2
        with self.assertRaises(ValueError):
            policy.exclusion(candidate)

    def test_prefix_labels_only_attempted_horizon(self):
        candidate = row()
        candidate.update(attempted=3, accepted_prefix=3, stock_width=3,
                         native_allowance=3, survival_labels=[1, 1, 1])
        candidate["native_counter_deltas"].update(neural_drafted=3, neural_accepted=3)
        self.assertIsNone(policy.exclusion(candidate))
        self.assertEqual(policy.label(candidate), 2)

    def test_request_and_document_split_guard(self):
        requests = [dict(request_id="a", document_ids=["doc"], split="train"),
                    dict(request_id="b", document_ids=["doc"], split="test")]
        with self.assertRaises(ValueError):
            policy.validate_split(requests)
        requests[1]["document_ids"] = ["separate-doc"]
        policy.validate_split(requests)
        requests[1]["request_id"] = "a"
        with self.assertRaises(ValueError):
            policy.validate_split(requests)

    def test_normalization_train_only(self):
        train = np.array([[1., 2.], [3., 4.]], dtype=np.float32)
        mean, scale = policy.fit_normalizer(train)
        np.testing.assert_array_equal(mean, [2., 3.])
        np.testing.assert_array_equal(scale, [1., 1.])
        policy.normalize(np.array([[1000., -1000.]], dtype=np.float32), mean, scale)
        np.testing.assert_array_equal(mean, [2., 3.])

    def test_probability_survival_consistent(self):
        probabilities = policy.softmax(np.array([[-10., 2., 1.], [10., 2., 1.]], dtype=np.float32))
        survival = policy.survival(probabilities)
        self.assertTrue(np.all(survival[:, 0] >= survival[:, 1]))
        np.testing.assert_allclose(probabilities.sum(axis=1), 1., atol=1e-6)

    def test_request_macro_weights(self):
        weight = policy.request_weights(["a", "a", "b"])
        np.testing.assert_allclose(weight, [.25, .25, .5])

    def test_fixed_width_uses_causal_begin_and_profile(self):
        candidate = row()
        candidate.update(stock_width=-1, causal_depth_low=2, causal_depth_high=0, adaptive=0)
        projected = project(candidate, dict(mtp_depth=2, spec_adapt=False))
        self.assertEqual(projected["stock_width"], -1)
        self.assertEqual(policy.effective_width(projected), 2)
        candidate["attempted"] = 1
        self.assertEqual(project(candidate, dict(mtp_depth=2, spec_adapt=False))["causal_stock_width"], 2)
        candidate["causal_depth_low"] = 3
        self.assertNotIn("causal_stock_width", project(candidate, dict(mtp_depth=2, spec_adapt=False)))
        candidate["causal_depth_low"] = 2
        self.assertNotIn("causal_stock_width", project(candidate, dict(mtp_depth=2, spec_adapt=True)))


if __name__ == "__main__":
    unittest.main()
