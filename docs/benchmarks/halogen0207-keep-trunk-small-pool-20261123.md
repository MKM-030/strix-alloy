# Halogen 0.20.7 Keep Trunk with a 10,240-position BF16 pool

A smaller BF16 KV pool let the full 8K comparison run with the existing
memory limits. Keep Trunk increased Windows time to first visible text by
**6.53–6.60%** and complete HTTP time by **4.13–4.20%** against the two
controls. All output bytes, token counts and native MTP counters matched.
The regular serving profile keeps Keep Trunk off.

| Arm | Actual input / output | API Prefill tok/s | API Decode tok/s | Native MTP accepted/drafted | First visible text | Full Windows HTTP |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Off before | 8,192 / 128 | 2,081.07 | 57.62 | 192/291 (65.98%) | 3.999 s | 6.221 s |
| Keep Trunk | 8,192 / 128 | 1,945.90 | 56.57 | 192/291 (65.98%) | 4.263 s | 6.482 s |
| Off after | 8,192 / 128 | 2,025.01 | 55.99 | 192/291 (65.98%) | 4.002 s | 6.225 s |

Each row averages three runs after one excluded warmup. All arms used
the same frozen novel prefix, 128 outputs, temperature 0, seed 1,
Cache Off, Thinking Off, Vision Off, v2/r2-HT4 and REV:N Performance.
The private context and its single BF16 KV pool both held 10,240
positions. Each arm kept both Prefill settings at 8,192. The only
between-arm flag was `HALOGEN_PREFILL_KEEP_TRUNK=1`. The native
startup listener and health confirmed the private capacity.

The engine reported 0.3 GiB of KV in every private arm, versus 0.9 GiB
with its ordinary 32K capacity. Candidate working memory rose from
5.6 to 11.1 GiB. The native log reported 5.6 GiB of kept-unpacked
trunk weights. The candidate started collection with 23.166 GiB of
physical reserve. Its lowest request-sampled reserve was 22.653 GiB.
The benchmark retained 30 GiB physical and 131 GiB commit startup floors,
22 GiB entry and 18 GiB runtime reserve.

API Prefill fell **3.91–6.50%**. Windows time from first visible text
through EOF held at roughly 2.22 s in all arms. The performance comparison
uses the independently timed complete request and time to first text.
[Phase clock audit](../research/halogen0207-phase-clock-audit-20261123.md)

The [32K comparison](halogen0207-keep-trunk-20261123.md) ended after
its candidate warmup when physical reserve fell short. This result
qualifies the complete paired comparison with the smaller pool and the
8,192-token input. The ordinary 32K preset was restored on port 8840.

## Evidence

The raw streaming responses and QPC, activation, admission and recovery
receipts are under
`server/.local/halogen-update-20261122/primary0207/keep-trunk-smallpool-8k-prep-v1/keep-trunk-smallpool-8k-run-v1`.

| Artifact | SHA-256 |
| --- | --- |
| Reviewed runner | `9027353289f27f499cf71f810909e5b293989cda804f521d7ea0c6289ea3e879` |
| Terminal comparison | `02015dbd8ad8eac56e4a0787cae360538f872cd1e63897ae776db0bf32b6ff0e` |
| Independent replay of the 12 raw SSE responses | `a9c51e21679c13d43cb7fd163569404632ecee9a6fcf1237098fe1f10ed9d943` |
| Standard server and Voice readiness | `078cbdf20d77c099c8c4f632d769a9d14d0070cd2970f2a87eabd0f99d2474f8` |
