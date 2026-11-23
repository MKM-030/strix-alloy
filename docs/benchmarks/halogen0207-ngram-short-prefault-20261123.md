# Halogen 0.20.7 parallel N-Gram prefault on the first 16K request

With up to four short-lookup prefault workers, the first visible text
to EOF interval was **2.506 s**, compared with **2.753 s** and
**2.741 s** in the two controls. Complete Windows HTTP time fell by
**0.274–0.421 s**. The first-response intervals are one observation per
launch. Warm request times were close in all three windows. The regular
service uses the image default.

## First request after readiness

| Short lookup mode | API Prefill tok/s | API Decode tok/s | Native MTP | First visible text | First text to EOF | Full Windows HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Default before | 1,318.73 | 46.49 | 60/93 (64.52%) | 12.476 s | 2.753 s | 15.229 s |
| Up to four workers | 1,335.88 | 51.12 | 60/93 (64.52%) | 12.302 s | 2.506 s | 14.808 s |
| Default after | 1,332.25 | 46.70 | 60/93 (64.52%) | 12.341 s | 2.741 s | 15.083 s |

The candidate first delivery interval was 8.6–9.0% shorter than the
controls. OS file-cache residency and the number of actual prefault
calls were unmeasured. The observations support a repeat on independent
starts before selecting the option as a default.

## Three warm repeats per launch

| Short lookup mode | Mean API Prefill tok/s | Mean API Decode tok/s | Pooled native MTP | Mean first text to EOF | Mean full Windows HTTP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Default before | 2,038.57 | 55.42 | 180/279 (64.52%) | 2.309 s | 10.422 s |
| Up to four workers | 2,045.78 | 55.55 | 180/279 (64.52%) | 2.304 s | 10.386 s |
| Default after | 2,050.91 | 55.43 | 180/279 (64.52%) | 2.309 s | 10.370 s |

The warm candidate beat the first control on full HTTP and took
0.016 s longer than the second. The warm measurements establish no
repeatable throughput gain on this workload.

## Method

Each window used a frozen, non-repetitive 16,384-token novel prefix,
128 output tokens, one 32K BF16 slot, 8,192-token prefill chunks,
temperature 0, seed 1, Thinking Off and Cache Off. The same read-only
NTFS N-Gram file, v2 checkpoint, r2-HT4 head and native cost policy
were used throughout. All 12 responses matched the frozen output bytes,
with 66 head rounds, 93 drafts and 60 accepted per request. Native
lookup and grammar drafting emitted zero proposals.

The candidate adds the bounded kernel control
`HALOGEN_NGRAM_DECODE_PAR=4`. On the pinned 0.20.7 executable, the
small-gather branch checks mapped page residency and can touch missing
pages in parallel before the ordinary gather processes the original
rows. The branch applies below 4,096 row visits. The managed option
forwards only the value four. The Docker settings match the declared
control on the candidate. Every arm used the same native startup path
and excluded the N-Gram timing diagnostics. Windows HTTP and first text
to EOF use QPC. The API rates retain their native timing scope.

The raw SSE, engine logs, bitwise output and startup proofs are in
`server/.local/halogen-update-20261122/primary0207/ngram-decode-par-prep-v1/prefault-first16k-run-v1`.
The request SHA-256 is `5ab14773484c4d0ea2f9f817b6be3a8ce09b10e9487dcb0b18ae9d4992bdb7ba`.
The output SHA-256 is `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b`.
An independent replay reconciled all 12 SSE streams and Windows time
boundaries. The minimum sampled physical or commit reserve during the
requests was 27.80 GiB. The final checks confirmed the restored model
on port 8840, ServiceNow routing, Native Voice, TTS and ASR. The private
listener and benchmark coordinator had closed.

| Local artifact | SHA-256 |
| --- | --- |
| Completed campaign | `1594a4e5288427a9998963cfda421f698dad55f85eaa1e267a88fc8aad2290b2` |
| Independent SSE replay | `112ac7960b49741c34ad5dd5f146250ea681e19e7b1e91b444add23fb0a8fb0f` |
| Candidate activation | `07db59d8e2439cf4347869639a4d291e249e58c940242a5be16ccb4db3719bbe` |
| Restored service health | `1d95b98a5865c744890848ac86f5ad6e86468e8a5d7e333fbf716c389a92ecc0` |

## Gufo projection reuse

The Gufo Q8_0 optimization caches a separately quantized copy for
one to eight input rows. The pinned Halogen Q8 kernels consume raw
BF16 activation data. Its grouped HT path already folds activation
preparation into the GPU kernel by default on the eligible short
rows. Any further reuse of a common input and matching sign values
would change the native HT kernel and its scratch and synchronization
contract. An optimistic count across the evaluated projection types
puts duplicate logical input bytes at 0.51% of their one-read packed
weight volume. The direct Gufo software cache offers no comparable
Prefill path for the 16K workload. [Gufo commit](https://github.com/mikealanni/gufo/commit/60eb85a92db017c83318e94298169a8adc149424)
