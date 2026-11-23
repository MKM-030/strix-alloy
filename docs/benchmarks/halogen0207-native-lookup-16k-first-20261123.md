# Halogen 0.20.7 native WSL lookup on the first 16K request

The first request finished **0.31 to 0.94 s sooner on ext4** than in
the two NTFS controls. First text arrived **0.53 to 1.16 s sooner**.
The ext4 first-request Decode rate fell to 43.31 tok/s from
46.70 and 46.84 tok/s. After the first request, all three arms
delivered about 55 Decode tok/s. Every response had the same output
bytes and accepted 60 of 93 native MTP head proposals over 66 rounds.

## First natural 16K request after each start

| Lookup path | API Prefill tok/s | API Decode tok/s | Native MTP | First visible text | Full Windows HTTP | Guest lookup reads per 8K slice |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| NTFS before | 1,269.52 | 46.70 | 60/93 (64.52%) | 12.960 s | 15.700 s | 4.3 / 4.2 s |
| WSL ext4 | 1,393.66 | 43.31 | 60/93 (64.52%) | 11.800 s | 14.757 s | 2.3 / 5.5 s |
| NTFS after | 1,332.82 | 46.84 | 60/93 (64.52%) | 12.334 s | 15.068 s | 4.1 / 4.0 s |

Each row is one first-request observation after startup readiness smokes.
NTFS bookends differed by 0.63 s. OS file-cache residency was unmeasured.
The lookup reports cover 131,072 rows per slice with 64 readers. The
engine may overlap lookup with compute, and the reported slice durations
have their own guest timing scope. First text and full HTTP use Windows
QPC.

## Three identical repeats per start

| Lookup path | Mean API Prefill tok/s | Mean API Decode tok/s | Pooled native MTP | Mean first text to EOF | Mean full Windows HTTP |
| --- | ---: | ---: | ---: | ---: | ---: |
| NTFS before | 2,060.77 | 55.17 | 180/279 (64.52%) | 2.319 s | 10.340 s |
| WSL ext4 | 2,051.75 | 55.13 | 180/279 (64.52%) | 2.321 s | 10.378 s |
| NTFS after | 2,043.73 | 55.25 | 180/279 (64.52%) | 2.316 s | 10.406 s |

The repeated ext4 requests took 0.04 s longer than the first control
and 0.03 s less than the second. The regular profile uses NTFS. Native
lookup remains an opt-in for first-request latency. The prior
[8K-first comparison](halogen0207-native-lookup-20261122.md) also saw a
first-request reduction with warm results near the controls.

## Method and evidence

All three arms used the exact 16,384-token novel prefix, 128 output
tokens, one 32K BF16 slot, 8,192-token prefill chunks, temperature 0,
seed 1, Thinking Off, Cache Off, and the stock greedy MTP policy on
Halogen 0.20.7 v2 with the official r2-HT4 head. Each launch finished
its normal readiness checks before the four benchmark requests. Cache
reuse and disk prompt-cache restores were zero. Native lookup and
grammar drafting also recorded zero proposals.

The updated lookup validation permits a WSL-projected device number to
change if the standard checkpoint receipt still binds the complete
current identity, stock lookup path and pinned full-source SHA-256.
The source header, remaining identity fields, ext4 file identity and
canonical payload seal are checked at qualification and before creating
and starting the container. The activation evidence records the
effective table, its read-only bind and the native startup line for each arm.

All 12 raw SSE responses, exact output files, Windows QPC times, native
logs, and a separate replay of the results are retained under
`server/.local/halogen-update-20261122/primary0207/lookup-first16k-campaign-prep-v2/lookup-first16k-run-v1`.
The request SHA-256 is `5ab14773484c4d0ea2f9f817b6be3a8ce09b10e9487dcb0b18ae9d4992bdb7ba`.
The output SHA-256 is `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b`.
The independent SSE replay found a minimum sampled physical or commit
reserve of 27.15 GiB. The regular Halogen service returned to port 8840.
The authenticated gateway, native backend, ServiceNow router, Native
Voice, TTS and ASR passed the final health checks. The private
benchmark listener was closed.

| Local artifact | SHA-256 |
| --- | --- |
| Completed campaign | `d503c12aa937ddcae654090b312ac7c4dac70cdbe043844f1af74802ad22a390` |
| Independent replay of all 12 raw SSE streams | `e970285e26146d94b00b3e89c337eccde14cae4198f269291f5cfd55ff25923b` |
| Candidate activation | `c3df0166c15cf1ce0ae4467ee1fad7be94e0f51e9743b7d0e2623496d6a0aacb` |
| Restored service health | `0f998c26d7ea0c81fbf5385670a9a7182c3a41f5fc9680e414f57b42ca1a5a65` |
