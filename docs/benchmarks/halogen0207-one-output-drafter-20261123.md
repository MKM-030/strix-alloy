# Halogen 0.20.7 prefill for one-output-token requests

Explicit serial drafting produced the same one-token completion as MTP on
the frozen novel workload. Serial averaged 31 ms more over three warm
request pairs. The measured difference changed direction across pairs.
The serving configuration remains on its existing MTP path.

| Drafter | Actual input/output tokens | API prefill tok/s | Windows HTTP mean |
| --- | ---: | ---: | ---: |
| MTP | 8,192 / 1 | 2,022.90 | 4.111 s |
| Serial | 8,192 / 1 | 2,008.42 | 4.142 s |

Both modes reported zero proposed and accepted drafts, so acceptance has
no denominator. The table describes prefill and full HTTP delivery for a
one-token response. The benchmark does not characterize sustained decode.

The same Halogen 0.20.7 process on port 8840 served all eight requests.
The request body differed only by `drafter`. Both arms used temperature
0, seed 1, Cache Off with `no_store`, and the same 8,192-token contiguous
novel prefix as the [128-token reference](halogen0207-performance-after-recovery-20261122.md).
The first pair was excluded. The remaining pairs alternated mode order
and yielded serial-minus-MTP Windows HTTP times of −136, −17 and +246 ms.
All eight completions had the same output bytes and `length` finish reason.

The excluded MTP and serial calls took 8.008 s and 4.131 s, respectively.
They share host cache state and form a single warmup pair. Inference
reserve stayed at or above 27.09 GiB. The service was never restarted.

The raw responses, request hashes and Windows QPC boundaries are retained
under `server/.local/halogen-update-20261122/primary0207/tts-cpu-offload-prep-v1/one-token-drafter-8k-run-v1`.
Summary SHA-256 is
`feacf872e6a21fdd896a06d8fbc6b839e84b082bf4c6a87c3cbbf1c00c3a1973`.
