# Halogen 0.20.7 INT8 KV comparison on Windows/WSL2

KV8 stays out of the HT4 serving profile. On the frozen 8K request, the
INT8 candidate reduced complete HTTP time by 0.68–0.94% against the
two BF16 controls. On 16K it increased HTTP time by 0.07–2.11%, and
native MTP acceptance fell by 11.69 percentage points. The candidate's
output differed from BF16 at both input lengths.

| Actual input tokens | KV cache | API Prefill tok/s | API Decode tok/s | MTP head accepted/drafted | Mean HTTP time (s) |
| ---: | --- | ---: | ---: | ---: | ---: |
| 8,192 | BF16 before | 1,903.09 | 53.08 | 192/291 (65.98%) | 6.190 |
| 8,192 | INT8 | 1,907.60 | 52.72 | 192/282 (68.09%) | 6.131 |
| 8,192 | BF16 after | 1,888.51 | 52.81 | 192/291 (65.98%) | 6.173 |
| 16,384 | BF16 before | 1,847.99 | 49.83 | 180/279 (64.52%) | 10.516 |
| 16,384 | INT8 | 1,882.19 | 46.94 | 168/318 (52.83%) | 10.523 |
| 16,384 | BF16 after | 1,887.09 | 51.12 | 180/279 (64.52%) | 10.306 |

At 8K the higher acceptance percentage came from nine fewer drafts across
the three measured requests. The total of 192 accepted drafts matched
both controls. At 16K the candidate proposed 39 more drafts and accepted
12 fewer. The native phase sums exceeded the independently timed HTTP
duration in all 24 responses. Prefill and Decode retain the API values,
averaged across the measured requests. Windows QPC measured each complete
request from dispatch to EOF. [Phase timing audit](../research/halogen0207-phase-clock-audit-20261123.md).

## Workload and activation

The separate lifecycle used the same Halogen 0.20.7 build, v2 model and r2
HT4 drafter across all three arms. Each arm used one 32,768-position slot,
paired 8,192-token Prefill settings, automatic concurrency, the native MTP
cost rule, and the `REV:N Performance` profile. The profile changed
`HALOGEN_KV8` from 0 to 1 to 0.

Each input was a frozen non-repetitive novel prefix. For each input size
and mode, one warmup preceded three measured requests. All 24 requests
generated 128 output tokens and finished at the length cap. The requests
used temperature 0, seed 1, Thinking Off, and Cache Off with
`prompt_cache_policy=no_store`. The lowest retained request reserve
was 25.06 GiB.

Native health verified `bf16`, `int8`, and `bf16`. The candidate log
reported 16,712 bytes per cache position. The documented opt-in changes
the representation of attention keys and values and permits different
outputs. [Pinned upstream flags](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/dea807d22a638c67553abea876344a8192054a94/docs/FLAGS.md).

The regular BF16 service on port 8840 was restored and left online.
Authenticated gateway and model health, ServiceNow routing and the Native
voice endpoint passed, with ASR and TTS ready. The private comparison
processes exited and their gateway listener closed.

| Actual input tokens | Both BF16 outputs SHA-256 | INT8 output SHA-256 |
| ---: | --- | --- |
| 8,192 | `58de6dc9de77c5c2adf6ae2ca69bdaff255cd06b277adfe73d664cd3c28c52cd` | `9c3c58471235da71c358cf9a80c9825fb9715db5b574f92c7acfe059305127d6` |
| 16,384 | `6f40c008b2660bd680de19adf790061b9ec70e94b1df9edaeb3c32b7f0e9385b` | `154c8e4a2a9fda6b907fb55f9fbbd98e4d15969c93c7731d39673b1f79556615` |

## Reproducibility

Local response bodies, QPC endpoints, manifests and lifecycle receipts are
under `server/.local/halogen-update-20261122/primary0207/kv8-prep-v1/kv8-comparison-run-v1`.

| Evidence | SHA-256 |
| --- | --- |
| Terminal campaign handle | `f3269f5deb506cb5a8174d9a191ac5de2dfaa58c2c00fe84637cc56e139bbfc1` |
| Independent audit of all responses and QPC endpoints | `5cafc10a9900a5fa521b5bbdfee1c62e77bd1b0efab5f6733199cc21656af052` |
| Native INT8 activation | `7124d9b7343887bd67cb548c8828fe838353cbb1f19260bf5aff3639eb6d2961` |
| Normal startup receipt | `3b5e02c10054f27a80da5aff1dec70764e5e881425ab1f0b8852fa1a97fa4cbf` |
| Post-restoration service health | `def3b8e458ee6338f128fd3d1808ce4aac52b1f3c3abc2257ab60fae09632b37` |
