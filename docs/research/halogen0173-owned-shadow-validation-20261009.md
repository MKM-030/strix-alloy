# Native MTP round capture on Halogen 0.17.3

The corrected, default-off adapter completed one owned native capture without
loss. All nine installed sites passed the exact ELF and instruction checks.
The request produced the same output hash and API counters as the retained
stock request. No NPU execution or speed improvement was measured.

The request used 8,192 actual input tokens and 128 output tokens, temperature 0,
seed 1, Thinking Off, Cache Off, MTP2/PLD3,3. Context capacity was 262,144 and both
prefill limits were 8,192. The input is synthetic pseudoprose with 116 repeated
calibration units. This is capture validation, not a natural-text benchmark or
a performance cohort. Native phase clocks were not qualified for this request.

| Observation | Result |
| --- | ---: |
| Matched native begin/outcome pairs | 59 |
| Censored pairs | 3 |
| Complete attempted-prefix label rows | 56 |
| Drops / gaps / unmatched records / live owners at close | 0 |
| API accepted / drafted tokens, unchanged from stock | 70 / 113 = 61.95% |
| Neural counters in the complete label rows | 69 / 112 |
| PLD counters in those rows | 0 / 0 |

The two counter scopes are different: the reader excludes censored terminal or
partial pairs from its complete label rows. The 69/112 row counters must not
replace the request's 70/113 API result. All 56 complete rows attempted depth 2:
15 accepted no draft token, 13 accepted one, and 28 accepted both. These describe
one request's observed prefixes; they establish neither generalization nor the
speed of a policy that chooses another width.

The first capture passed output parity but failed whole-journal qualification
because of two leading drops. The exact native branch paths show that both
append sites can bypass Request construction. The two serial startup smoke
requests therefore reached those sites with a null Request. The collector
incorrectly classified them as lost MTP lifetimes. The fix ignores that proved
non-Request case; malformed nonnull owners still cause loss. The changed-source
capture then closed with zero drops. The unsuccessful first attempt remains
retained locally.

The CPU qualification included 11 reader tests, the actual collector fixture,
88 copied-relay checks and disabled-preload thread forwarding. The final linked
relay island matched the independently reviewed island byte for byte. The native
capture, nonce-bound journal closure and unchanged request result supply the
separate runtime evidence. Capture and normal servers were run sequentially
through the existing lifecycle.

Evidence: [validation.json](halogen0173-owned-shadow-20261009/validation.json),
[journal](halogen0173-owned-shadow-20261009/journal.h0173sl),
[startup status](halogen0173-owned-shadow-20261009/startup-status.json),
[close receipt](halogen0173-owned-shadow-20261009/close-receipt.json), and
[serial append proof](halogen0173-owned-shadow-20261009/serial-birth-source.txt).
Source and offline reader: [README](../../scripts/research/halogen0173_owned_shadow/README.md).

The next policy step needs independent real requests with their loaded-asset
and request-to-document provenance, held-out prediction evaluation, and actual
end-to-end cost comparisons. Wire v1 has no round costs. The native skip path is
available after eligibility and bounds checks; passing width zero or one directly
to the neural controller is not equivalent. No width policy is implemented here.
Compare the same policy on CPU, GPU and NPU, including submission and transfer
overhead, and adopt a placement only if delivered Prefill/Decode improves.
