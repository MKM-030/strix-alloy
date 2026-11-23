# MTP delivery bursts in Halogen 0.20.7

The retained natural-text streams group into client-side bursts with
the same grouping at both 3 and 10 ms. All 45 measured single-slot
captures reconciled with the native head totals and the response byte
hashes. A separate screen reconciled 18 streams from the two-slot
campaign. These are delivery observations from Windows QPC. The
0.20.7 token stream carries no verifier round identifiers, and the
HTTP adapter and gateway can buffer token delivery.

The measured single-slot captures span fixed depth one, fixed depth
two, their adaptive controls and the small BF16 KV-pool comparison.
Each completion returned 128 tokens and had a length finish. The
audit requires one streaming delta per token, no prompt-cache reuse,
no reasoning, zero lookup and grammar counts, and agreement between
the aggregate native head counts and the grouped SSE events.
One or two singleton boundary events account for the difference
between total output tokens and native rounds plus accepted drafts.
The table counts inferred accepted tokens per group after those
boundaries. Native capture would be needed for round-level labels.

| Actual input | Draft policy | Inferred accepted tokens per group | Native head accepted / drafted |
| ---: | --- | --- | ---: |
| 8,192 | Adaptive | 0 × 17, 1 × 31, 2 × 10, 3 × 3, 4 × 1 | 64 / 97 |
| 8,192 | Fixed depth 1 | 0 × 24, 1 × 51 | 51 / 75 |
| 8,192 | Fixed depth 2 | 0 × 12, 1 × 18, 2 × 26 | 70 / 112 |
| 16,384 | Adaptive | 0 × 22, 1 × 30, 2 × 12, 3 × 2 | 60 / 93 |
| 16,384 | Fixed depth 1 | 0 × 21, 1 × 53 | 53 / 74 |
| 16,384 | Fixed depth 2 | 0 × 23, 1 × 17, 2 × 23 | 63 / 126 |

The distribution explains how a lower percentage can coincide with
faster delivery. At 8K, fixed depth two used 56 rounds and accepted
70 drafts. Adaptive used 62 rounds and accepted 64. The measured
8K win had **62.50%** acceptance against **65.98%**.
[Fixed-depth comparison](../benchmarks/halogen0207-fixed-mtp-depth-two-20261123.md)

## What a third draft would need

The aggregate fixed-two counters alone place the number of rounds
accepting both proposals between 14 and 35 at 8K, and between 0 and
31 at 16K. The delivery proxy places those counts at 26 and 23.
Adaptive showed a four-or-more-token burst at three of the same
output start indices at 8K and one at 16K. For other indices, the
stream leaves the third proposal and its acceptance unobserved.
A deeper policy would also change the remaining round start points.

For a sensitivity calculation, hold the observed round starts fixed.
Give depth three one extra committed token with probability `p` on
each inferred full fixed-two group. Charge an extra `d` seconds to
every fixed-two round. With `F` eligible groups, `R` native rounds,
`N = R + accepted` tokens and observed Windows first-text-to-EOF
time `W`, the modeled rate ratio is `(1 + Fp/N) / (1 + Rd/W)`.

| Added cost per round | Required third-draft acceptance for a modeled 5% gain, 8K | 16K |
| ---: | ---: | ---: |
| 0 ms | 24.2% | 27.4% |
| 1 ms | 37.7% | 42.6% |
| 2 ms | 51.2% | 57.9% |
| 3 ms | 64.6% | 73.1% |
| 5 ms | 91.6% | 103.5% |

These probabilities are conditional on both initial drafts being
accepted. They are model inputs, with no measured third-rank probability
or added cost. The observations support keeping the measured 8K
fixed-two option and the adaptive standard profile.

## Replay

`scripts/benchmarks/halogen_mtp_sse_bursts.py captured.sse.json` replays a
retained completion stream. Supply `--fixed-depth 2` only when the launch
and native startup evidence verify that policy. The code reads saved
files and contains no inference, lifecycle or network calls.

The separate cross-campaign calculation is retained in the local
`sources-20261123/sse-mtp-burst-evidence-v2.json` receipt. It binds all
three complete single-slot handles and the captured SSE bytes.
SHA-256 `d83b1a937a99bd42e413a915d597ab503659584123d290f5dc0b25af8517bcfb`.
