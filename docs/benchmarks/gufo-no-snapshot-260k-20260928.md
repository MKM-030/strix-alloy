# GUFO no-snapshot long-context experiment — 28 September 2026

**Two simultaneous requests with 260,000 actual input tokens each completed on
native Windows.** GUFO reported width-2 batching, produced 256 tokens per answer,
and shut down with confirmed memory recovery. This is one capacity/performance
trial, not a repeated distribution or a production-service qualification.

## Measured results

Both requests were submitted at 18:54:19 CEST and finished at approximately
19:10:06 on 28 September. Two 262,144-token capacities shared one IQ4_XS model
and the existing Q8_0 MTP sidecar. MTP draft 3/minimum 1, length policy, full
vocabulary, greedy seed 42, thinking off, all prompt caching disabled.

| Measurement | Session A | Session B |
|---|---:|---:|
| Actual input / output tokens | 260,000 / 256 | 260,000 / 256 |
| Native prefill rate | 554.57 tok/s | 560.25 tok/s |
| Native prefill timer | 468.834 s | 464.079 s |
| Native decode rate | **18.98 tok/s** | **18.66 tok/s** |
| Native decode timer | 13.487 s | 13.719 s |
| Client first visible content | 933.843 s | 933.843 s |
| Full HTTP request duration | 947.328 s | 947.562 s |
| MTP accepted / proposed | 167 / 217 (76.96%) | 166 / 219 (75.80%) |
| Cached tokens | 0 | 0 |

The native prefill timers count each request's own processing, excluding the
other request's interleaved prefill. They are **not** both sustained wall-clock
rates at once: both clients waited about **15 minutes 34 seconds** for first
content. Both native records report `physical_execution_width=2` and
`execution_plan=batched-w2`; this is peak observed width, not proof that every
cycle and both unequal tails ran at width two.

Together the responses contain **512 native-counted output tokens**. Whole-group
throughput is `512 / 947.562 = 0.5403 tok/s`, including the long cold prefill.
That is **not a sub-one-token/s decode result**. Fixed common-window pure decode
is not available from these counters; do not add the individual rates or count
SSE text chunks as tokens. This artificial archive corpus is not standard
Halogen PP2048/8192/32768 and must not replace those separate comparisons.

Both responses correctly retrieved their distinct early archive keys
(`ORANGE-7426`, `VIOLET-3198`). Both hit the imposed 256-token limit and ended
inside unfinished code. This proves key retrieval and token generation, **not**
complete correct coding answers or general long-context answer quality. No
generated code was executed.

## Memory and cleanup

Across 983 load/inference samples:

- Windows physical memory available before launch: **46.601 GiB** baseline
  minimum; lowest during the run: **27.755 GiB**, above the retained 24 GiB floor.
- Adapter-wide GPU committed peak: **81.137 GiB** (about **87.121 decimal GB**).
  Shared usage peaked at **17.712 GiB** and is already included, not added again.
- Engine load report: **81,453 MiB = 79.544 GiB**, a different accounting scope.
- System commit headroom minimum: **119.999 GiB**, above the 12 GiB floor.
- Owned exit code 0; HTTP, module-inspection and collector workers terminated;
  evidence writes and cleanup confirmed. All **1,004/1,004** telemetry queries
  completed; longest query 0.625 s, largest recorded age 1.625 s.
- Recovery log contains seven observations, with five final qualifying frames:
  **47.891–48.481 GiB available**, adapter commitment **0.812–0.837 GiB**.
  The owned PID 37260 and port 8836 listener were independently checked absent.

Sampled peaks are lower bounds on instantaneous maxima. GPU commitment is not a
direct physical-residency measurement; do not add it to Windows RAM usage.
The experiment does not qualify three full sessions or a persistent server.

Before the long run, the same build completed the bounded arithmetic request
(`4`) and a complete 376-token merge-lists answer at **54.03 native decode tok/s**.
That short prompt is not a full-context comparison; its answer and cleanup were
reviewed before starting the long run.

## Implementation and reproducibility

Dedicated experimental source `8309dfc150bf0a213f52597abfb5bd80d0ea9c05` on
pixmaate Windows pin `cff564964e8506c0abb3e530cecb55332187ac6c`. The patch changes
only Flash-Next serving snapshot/fork/prefix-reuse/persistence capabilities and
retained snapshot capacity. It removes full host prompt snapshots, not ordinary
token vectors, MTP rollback state, full FP16 KV, or model memory.

Original GUFO binary, pinned source and Halogen remain untouched. New binary:
`build/gufo-no-snapshot-hip-10.2/gufo.exe`, SHA256
`F9CA7499D7D19259C36ADABEC5DA93CCF4FE5C6331959A4FC229D170FB222E87`.
TheRock10.2, gfx1151, RelWithDebInfo HIP `-O2 -DNDEBUG -g0`, two build jobs,
existing vcpkg dependencies. Raw build and staged dependency identities live in
`reports/gufo-no-snapshot-build-20260928/`. All five focused existing CPU tests
passed: runner, scheduler, OpenAI chat, MTP sampling, prompt lookup. Compiler
warnings were inherited nodiscard/include-next/initializer warnings; this is not
a warning-free full repository qualification.

Four exact request bodies were prepared with native GGUF tokenizer/template code
and independently reviewed. Short arithmetic/code inputs are26/31 tokens. Long A
and B are each exactly260000 complete rendered native tokens, with256 output cap,
inside262144 capacity. Request bodies are1456530/1456384 bytes. Their artificial
repeated archive plus distinct retrieval key and coding tasks is **not** the
Halogen standard PP corpus. Both runtime native counts confirmed the prepared
260,000-token inputs. Request inventory and proofs: `reports/no-snapshot-260k-prompts/`.

The user waived the49/50GiB startup gate for this experiment. Runtime stop floors
remain24GiB available physical and12GiB system commit headroom. Source accounting
found13.196777GiB extra device state versus two4k sessions. Disabling snapshots
removes about13.57GiB of additional host captures from the unmodified260k path.
The independently reviewed empirical memory scenario has a narrow reserve, not
a reservation or guarantee against WDDM freezes. Limits are stop ceilings; do not
equate them with measured memory usage. No BIOS/driver/service/pagefile changes,
reboot, D: actions or publication are part of this experiment.

Raw run:
`C:\Projects\strix-alloy-research\reports\no-snapshot-260k-long-20260928-v1-runs\20260928T165313Z-2d6d41d029894f55a5e4144d3241528a`.
Result SHA256:
`AB4748FF57165571F765B64372CAE9B5969E53C9B8D59D6046554AE1F7BBD7F9`.
It contains native counters/timers, complete raw SSE bodies and arrival times,
request hashes, source/binary/configuration bindings and cleanup evidence.
Independent audit: `reports/no-snapshot-260k-long-audit-20260928.md`, completed
with the timing, sampling and incomplete-answer caveats above; SHA256
`2BA345B8DDDE3AEAD77E39DD2EA43D198C6958639390287B90C13F607752760D`.
The one-use run is consumed; retain its evidence and do not replay its adapter.
