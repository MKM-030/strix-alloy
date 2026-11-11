# Unused-head NPU live comparison: stopped before measurement

The new live attempt on 11 November 2026 **did not start the NPU helper**.
It saved only the stock BEFORE arm's excluded warmup, then reached the
unchanged 120-second memory-admission limit before its first measured request.
Session **84304 exits 1**, with `completed=false` and `restored=true`.
There is **no measured three-run mean, NPU token rate, NPU acceptance or
full-engine speedup** from this attempt.

| Saved request | Actual input/output tokens | RAW prefill tok/s | RAW decode tok/s | API neural-head accepted/drafted |
| --- | ---: | ---: | ---: | --- |
| Stock BEFORE warmup, excluded | 8192 / 128 | 748.5344 | 32.7074 | 64/104 = 61.54% |

This single warmup is excluded from performance qualification. Its API head
acceptance is explicitly API-scoped; lookup has zero drafts and accepts, so
its 0/0 acceptance ratio is undefined. It is not an NPU observation or a value
for a performance post. Candidate and AFTER arms were never started.

The frozen workload remains one 32768-position slot, paired
`prefill_chunk=max_prefill_tokens=8192`, 8192 actual document input tokens,
128 output tokens, temperature 0/seed 1, Cache Off/no_store and Thinking Off.
The partial RAW journal, response and complete 128 native target IDs are
preserved. Independent file auditing rehashes them, reconstructs the ID/text
hashes and recomputes the saved RAW midpoint rates.

The failed `0004.json` admission receipt retains **472 samples over 120
seconds**, with available physical memory between **21.2917 and 21.9142 GiB**.
No sample reaches the required 22 GiB. The 18 GiB runtime floor is retained;
neither memory limit nor context capacity is lowered. No replacement cohort
is used to fill this failed attempt.

The separate [native unused-head component](halogen0201-core-append-component-20261111.md)
still qualifies **37.5139% less complete commit-loop time** and
20,093,670 exact BF16 values. That result remains a component measurement.
This live attempt supplies no new NPU execution and does not establish whether
the faster component delivers proposals before GPU demand.

Root's actual terminal observation confirms the coordinator is dead and the
normal Halogen **0.20.1** server is restored, with controller/backend
**22152/28860**. Fresh verification at **12:40:55 UTC** reconciles both run IDs,
the original paired8192 profile and all **47** normal source members. An
authenticated, separate 17-input/two-output-token smoke returns `READY`.
Serving remains open on port **8840**, with NPU integration disabled. The smoke
is not a benchmark.

Further measurement awaits a changed memory-admission condition after Root's
request to free about 2 GiB RAM. This audit stops no foreign application and
starts no hardware or API request. The acceleration goal remains open.

[Numeric partial export and pinned evidence](halogen0201-core-append-live-partial-20261111.json)
preserve the terminal failure and distinguish the excluded warmup from zero
measured requests. The retained read-only verifier is
`server/.local/halogen-update-20261110/primary0201/real-npu-core-append-live-v1/verify_public_export_v1.py`;
it passes **73 checks over 63 pinned files** without loading a DLL or contacting
the server.
