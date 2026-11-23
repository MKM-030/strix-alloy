# Halogen 0.20.7 Keep Trunk memory and benchmark admission

Halogen retained **5.6 GiB** of unpacked model weights with
`HALOGEN_PREFILL_KEEP_TRUNK=1`. The runner completed the 16K candidate warmup
with the reference output bytes and native MTP counters. It then waited
120 seconds for the existing 22 GiB physical reserve before the first
measured candidate request. All observed physical reserves were below
that threshold. The candidate produced zero timed repetitions.

| Actual input | Completed stock control | API Prefill tok/s | API Decode tok/s | Native head accepted/drafted | Mean Windows HTTP |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8,192 | Cache Off, stock MTP | 2,071.25 | 57.51 | 192/291 (65.98%) | 6.243 s |
| 16,384 | Cache Off, stock MTP | 2,057.98 | 55.33 | 180/279 (64.52%) | 10.345 s |

Each stock row excludes one warmup and averages three requests with frozen
novel prefixes and 128 outputs at temperature 0, seed 1 and Thinking Off.
The test used the same 32K BF16 one-slot profile, 8,192-token Prefill chunk
and arena, r2-HT4 head and REV:N Performance profile. API rates retain
the native clock, and Windows QPC measures dispatch through streamed EOF.

## Candidate activation and memory

The first attempt stopped before sending a candidate request because
the collector required a second allocation line found in an earlier
Halogen version. The revised checker uses the 0.20.7 startup memory
breakdown, the named allocation and the OCI flag. It also checks
unchanged weight and KV figures and the rounded difference between arms.
Nine offline tests passed, including replay of the original 0.20.7 logs.

| Receipt | Stock before | Keep Trunk |
| --- | ---: | ---: |
| Native locked weights | 62.1 GiB | 62.1 GiB |
| Native KV pool | 0.9 GiB | 0.9 GiB |
| Native working allocation | 5.6 GiB | 11.1 GiB |
| Native total | 68.5 GiB | 74.1 GiB |

The corrected run admitted the candidate at 22.525 GiB physical and
112.094 GiB commit. The warmup sampled a minimum of 21.672 GiB, above the
18 GiB runtime floor. Before the first timed repetition, the 213 valid
memory frames observed **21.412–21.747 GiB physical** and
111.008–111.405 GiB commit. The admission records showed no active games or
observed competing GPU workload. Candidate performance and a full
before/candidate/after comparison remain unqualified.

The lifecycle restored regular Halogen on port 8840. Authenticated
controller and backend health and Voice, ASR and TTS readiness passed.
Keep Trunk stays off in the regular profile. The earlier
[paired 16K Prefill experiment](halogen0207-prefill16384-20261123.md)
found output changes when changing the chunk and arena. A smaller arena
would need to qualify as a separate change before any speed comparison.

## Evidence

The raw streaming samples, QPC receipts, native logs and admission windows
are retained under
`server/.local/halogen-update-20261122/primary0207/keep-trunk-recheck-prep-v2/keep-trunk-recheck-run-v2`.

| Artifact | SHA-256 |
| --- | --- |
| Corrected runner | `a05775da7a02b7c1d760906adce1419074e8ca26d27ef2144011cede83d8313d` |
| Corrected attempt terminal handle | `60c0f0eacad7ae54bff8dd2e45bb6cf74a175ac7ef017369b724d0a48b23b294` |
| Independent replay of the stock requests and candidate warmup | `43f86a4ec99f9299faa5c127e292535d5b69756e84f8c698bbb962cecac6cc14` |
| Terminal request admission receipt | `93a38fdba18d75f3e65c6eee9a22af94fb233fb4d6f0c0ac50ddbf1bf662ac85` |
| Restored standard server and Voice readiness | `dcc3364f19011961711b1a26a6f6f5bb0ac357f9ba6b0141cba186f2ce8bac73` |
| Original attempt terminal handle | `9999429acc049adda1b639ac0c4b7878f1b4e0bdde31c8a237cd4ac1c75a0a30` |
