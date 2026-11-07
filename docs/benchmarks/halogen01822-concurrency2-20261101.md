# Halogen 0.18.22 distinct 8K + 16K concurrency comparison

**Frozen workload classification, 7 November 2026.** The 8192-token case uses synthetic prose; the 16384-token case uses a contiguous novel excerpt. [Workload identities and new natural 8K preparation](halogen-8k-workload-classification-20261107.md).

One shared engine, two different frozen requests. The metric below counts completed output tokens over the whole pair QPC makespan, including prefill, queue and transport. It is not Prefill or Decode phase tok/s.

The normal server was restored to port 8840 with its original profile and exact source seal: 14 transition paths, eight original files restored, six added files removed, and 44 normal backend source members verified.

A transient status-file read PermissionError interrupted observation of AFTER startup. Root resumed the same confirmed AFTER controller/run, completed that cohort once, and restored normal serving. The interrupted original handle remains unchanged; explicit recovery evidence binds the original before/candidate results and the same AFTER launch.

| Arm | Engine slots | Completed-output tok/s (pooled) | Pair QPC mean (s) | 8K request latency (s) | 16K request latency (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| before | 1 | 14.342 | 17.849556 | 14.007647 | 13.531538 |
| candidate | 2 | 15.160 | 16.886263 | 16.419005 | 16.886066 |
| after | 1 | 14.334 | 17.860248 | 14.026146 | 13.547994 |

| Arm / actual input | Native head accepted / drafted | Native head acceptance |
| --- | ---: | ---: |
| before / 8,192 | 210/318 | 66.04% |
| before / 16,384 | 177/336 | 52.68% |
| candidate / 8,192 | 201/253 | 79.45% |
| candidate / 16,384 | 165/294 | 56.12% |
| after / 8,192 | 210/318 | 66.04% |
| after / 16,384 | 177/336 | 52.68% |

Candidate pooled completed-output throughput changed by +5.70% versus the first control and +5.77% versus the second control. Each comparison uses its own control; the controls are not averaged.

Individual request latency increased by 17.21%/17.06% at 8K and 24.79%/24.64%
at 16K versus the two respective controls. Normal ServiceNow serving therefore
retains one engine slot. The staged two-slot implementation has a measured
aggregate-throughput benefit on this mixed pair, with a latency tradeoff; it
has not been promoted into the normal installed source.

The higher acceptance percentages also have a different denominator. At 8K,
accepted draft tokens fell from 210 to 201 while proposals fell from 318 to
253; at 16K they fell from 177 to 165 while proposals fell from 336 to 294.
This does not establish faster single-request decoding. The latest qualified
single-request phase rates remain in the [RAW 8K/16K report](halogen01822-raw-8k16k-20261101.md).

Each arm contains one excluded warmup pair plus three measured pairs; every pair has distinct 8,192/16,384 actual input tokens and 128 output tokens per request. Temperature 0, seed 1, Thinking Off, Cache Off/no_store, MTP, PLD 3,3, gate 0.90, chunk/max-prefill 8192. Gateway concurrency remains 2, slots are 1/2/1, context and shared pool are 32768, benchmark port is 18840. All responses must match the qualified normal output hashes and strict native scoped accounting.

QPC request latency and whole-pair makespan are independently recomputed from retained endpoints. Acceptance pools accepted/drafted native head tokens across the three measured repetitions; lookup and grammar scopes are preserved separately in JSON. Different proposal counts between arms are legitimate and are not forced equal.

CPU evidence: 14 collector and five coordinator preparation tests were observed in root tool commands; fresh installed logs show 15 portable tests and five forwarding tests passed. Three recovery observation tests also passed. These are distinct evidence scopes. No NPU speed gain is demonstrated, and the full optimization goal remains open.

Matching JSON contains selected evidence pins, profile/manifest snapshot hashes, recomputed per-arm metrics, each pair, and both separate control comparisons. Private prompts, generated text, credentials, and complete private manifests are not published.

Evidence hashes:

- `server/.local/halogen-update-20261101/primary01822/concurrency2-finite-comparison/handle.json` — `a189fa3959be2b568a5a650be5c9f3289028867f4f972f0821e1022779ef48b7`
- `server/.local/halogen-update-20261101/primary01822/concurrency2-finite-recovery/normal-left-ready.json` — `0dc50b13f7c3815a43544ab1e4db0ecbac9d38f5fc05b47633405741e5048269`
- `server/.local/halogen-update-20261101/primary01822/concurrency2-run-prep/transition.json` — `a3adeb48b7b323bd10e5eaea4301d1a02b7e69b9a10f5ed3cf4002983363c0ba`
- `server/.local/halogen-update-20261101/primary01822/serving01822-text32k.json` — `53a943ec4c61d0f3c057d13da561d5551720fe65d29b9a5a2bff39b7cc5566a1`
- `docs/benchmarks/halogen01822-raw-8k16k-20261101.json` — `0c9937acb786aecd17c0a241eddc58a63e60427a340634ec66d16a84a9da6286`

Limitations:

- No singleton RAW observer was used on interleaved requests.
- No qualified phase Prefill/Decode rates are inferred from completed-output throughput.
- Native scoped counters are pooled within each case; legitimate proposal counts may differ between arms.
- Normal readiness is the saved post-campaign snapshot, not a fresh API request by the publisher.
- Candidate source is restored, not promoted, whatever the comparison outcome.
