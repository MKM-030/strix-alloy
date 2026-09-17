# Engine comparison without mixing benchmark modes

**Source review: 2026-09-17.** strix-alloy snapshot: `199b8ec`. Every third-party figure below was
re-fetched from the pinned revision and checked before being written down; where a source did not render, that
is stated rather than filled in from memory.

This is a comparison of **publisher-reported observations**, not an independently reproduced head-to-head. It
separates measurement modes instead of ordering every tokens/second number into one leaderboard. The source
revisions are pinned at the end; ilintar's page is a retrieved website (no immutable revision).

---

## What the headline numbers mean

- **strix-alloy 31.49 t/s** — synthetic serial `llama-bench tg128`, no drafter, pseudorandom token inputs.
- **strix-alloy 30.16 t/s** — the same test in the `-b/-ub 16384` invocation. Different batch allocation, so it
  is a separate row, not a re-measurement.
- **strix-alloy 45.31 t/s** — served MTP, `n-max 2`, warm median, **one 259-token instructed prompt**.
- **strix-alloy 31.0–32.8 t/s** — served MTP on a separate long-context ladder (16k→251k). A different
  experiment from the short-prompt cell; do not pool the two.
- **Halogen 45.3 t/s** — speculative serving **mean over ten prompt shapes**, 0.6.0 image.
- **CIRU 60.351 t/s** — pooled MTP3 decode over a short HumanEval 0–9 speed panel. Not general chat.

The first is not a competitor to the others. The rest are all speculative-generation measurements, but their
prompts, depths, statistics, weights and timing contracts still prevent a fair ranking. Our withdrawn
**51.21 t/s / "depth four adds 10% on chat"** result is explicitly not a comparison point
([ledger](CLAIM-LEDGER.md)).

**Naming:** `olliehm/qwen-flash-next-windows` is the Windows/Lemonade project compared here — **not Ollama**.
CIRU refers to `ciru-ai/Qwen3.8-Flash-CIRU-STRIX-IU4`. No verified matching Ollama result exists in these
sources, so none is invented.

---

## 1. Vocabulary: what each metric does and does not establish

| Metric | What it measures | What it does not establish |
|---|---|---|
| Synthetic serial `tg128` | 128 sequential single-token evaluations, no drafter | Natural autoregressive answer speed, quality, or MTP speed |
| Served serial decode | Generated-token rate with speculation disabled | Equality with synthetic `tg128`, or with a different occupied depth |
| Served speculative decode | Generated-token rate with MTP active | The target's one-token speed; a content-independent rate |
| Prefill / prompt processing | Input-token processing inside the stated boundary | Generation speed or whole-request throughput |
| TTFT / first piece | Waiting until the first output event under the stated transport | Identical work across engines that expose different first events |
| Whole-request latency | User-visible duration including prefill and generation | The inverse of decode t/s alone |
| Cached follow-up | Work after history reuse | Fresh prefill of the entire nominal conversation |
| Concurrent throughput | Sum of rates across streams | Single-stream rate |

**`pp16384` names input tokens processed; `tg128` names single-token evaluations.** Running both in one
invocation does **not** mean the generation test follows a 16k prompt — our own canonical record pairs
`pp16384 892.59` with `tg128 30.16`, where the generation test starts from an empty cache. Initial/occupied
depth must always be reported separately from allocated capacity: `-c 262144` is not an occupied 262k history.

---

## 2. Synthetic serial benchmarks — no speculative rows belong here

| Publisher / platform | Harness and shape | Prefill (t/s) | Serial eval (t/s) |
|---|---|---:|---:|
| strix-alloy / Windows HIP | `llama-bench pp512` / `tg128`; batch 2048, ubatch 512 | 761.30 ± 38.24 | 31.49 ± 0.17 |
| strix-alloy / Windows HIP | `llama-bench pp16384` / `tg128`; batch/ubatch 16384 | 892.59 ± 22.50 | 30.16 ± 1.00 |
| ilintar / pwilkin / Linux | published `pp16384` / `tg128`; initial depth 0; batch/ubatch 16384 | **1204.31 ± 2.31** | 26.28 ± 0.29 |

Our `±` is a **sample standard deviation**, not a confidence interval.

Paired against the *matching* rows: **−25.9% prefill and +14.8% serial evaluation**. Pairing 31.49 against
26.28 instead would give +19.8% — that is the default invocation against their large-batch invocation, so
do not use it. These are ratios of published measurements, **not isolated Windows-versus-Linux engine gains**:
revisions, runtime, token sequences, loading modes and conditions all differ.

**Do not attribute the prefill gap to retained PM4.** That attribution is withdrawn: ilintar's own page states
that for Next-Flash prefill "HIP graphs never engage (each prefill chunk shape appears only once per request)",
so retained PM4 pays off in *decode*. The cause is **unresolved**
([ledger](CLAIM-LEDGER.md), [canonical record](canonical-llama-bench-20260916.md)).

No matched synthetic `tg128` result was found on the Halogen, CIRU or olliehm pages. Their serving rates do not
belong in this table.

---

## 3. Served serial decode — context, not a matched race

| Publisher / configuration | Occupied prompt/history | Serial decode (t/s) |
|---|---:|---:|
| strix-alloy, no drafter | 16,384 | 28.3 |
| strix-alloy, no drafter | 65,536 / 131,072 / 251,904 | 27.8 / 26.9 / 25.1 |
| **Halogen** (0.2.0 figures, decode kernels unchanged since) | 1,500 / 8,000 / 32,768 | **37.6 / 36.1 / 34.1** |
| olliehm, **stock `llamacpp-rocm b1326` baseline** | 500 / 2,000 / 8,000 | 21.7 / 21.6 / 20.3 |
| CIRU IU4 v4.4 | — | not reported |

**Halogen's published serial rates are higher than our served serial ladder**, and that should be stated
plainly rather than hidden. Their machine configuration differs (see §5 caveats) and no boundary-matched test
exists, so it is not a settled ranking — but we do not have a serial win to claim here either.

**The olliehm row is a stock baseline, not his final engine.** His report labels it "Stock llamacpp-rocm
b1326, no MTP (baseline)"; his final patched stack is the 38 t/s MTP row in §4. Do not use 20.3 to claim a
serial advantage over his final engine — our earlier comparison did exactly that and it was unfair.

---

## 4. Served speculative decode — attach the workload to every number

### Ours

| Workload / occupied input | Speculation | Decode (t/s) | Statistic and limitation |
|---|---|---:|---|
| Instructed answer / 259 tokens | MTP `n-max 2` | **45.31** | repaired warm median; one prompt cell |
| Same instructed answer | MTP `n-max 4` | **45.45** | same protocol; +0.3%, a tie at this evidence level |
| Document continuation / 1,024 | MTP `n-max 2` | **33.07** | repaired median; one corpus-prefix cell |
| Document continuation / 8,192 | MTP `n-max 2` | **26.97** | repaired median; different occupied depth |
| Separate depth ladder / 16,384 · 65,536 · 131,072 · 251,904 | MTP `n-max 2` | **31.2 · 32.6 · 32.8 · 31.0** | different experiment; do not pool with the rows above |

The `n-max 2` recommendation rests on **three prompt cells from one corpus family** — evidence for the current
default, not proof of a universal mixed-workload optimum.

### Others (each in its own category)

| Publisher / version | Workload | Decode (t/s) | Statistic / condition |
|---|---|---:|---|
| **Halogen 0.6.0** | ten real short-prompt shapes, served | **45.3** | mean with speculation; cases span 39.5–49.4 |
| Halogen served | 32,768 context, ten prompts | **41.7** | mean with speculation |
| Halogen 0.6.0 | ctx 1,500 prose / code | 44.8 / 49.9 | MTP with the 0.6.0 sidecar (42.4 / 48.3 with 0.5.x) |
| Halogen 0.6.0 | coding-agent turn (± prompt lookup) | 49.1 → **56.3** | MTP alone vs MTP + lookup; not general prose |
| **olliehm patched stack** | Lemonade/admission serving | **38** | MTP `n-max 4 p-min 0.75`; occupied depth and aggregation not specified for the headline |
| **CIRU IU4 v4.4** | 12,960-token incident replay | **44.53** | MTP3; candidate arm of a controlled pair (control 37.79); one block |
| CIRU IU4 v4.4 | HumanEval 0–9, short prompts | **60.351** | pooled timed decode, one speed panel; not a coding-accuracy result |
| CIRU IU4 v4.4 + Boost | same panel | 64.067 | opt-in follow-up load; not a production-default result |
| CIRU IU4 v4.4 | 245,760-token cold workload | 21.14 | MTP3 (control 7.62); separate long-context observation |

**Interpretation.** Our 45.31 and Halogen's 45.3 occupy the same broad category, but a **one-prompt median and a
ten-prompt mean are not evidence of a tie**. CIRU's 60.351 belongs to a short-code panel, not this chat
comparison, and its own release notes call it one speed panel per setting. Our withdrawn 51.21 cannot be used
to claim a win over either.

**Acceptance is not a quality score.** Confidence filtering can raise accepted/proposed while reducing
proposals; deeper drafts increase discarded verification work. Record proposed, accepted, emitted and round
time — and do not infer verification width from `n-max`, which is a maximum.

---

## 5. Prefill — internal benchmarks and serving measurements are different instruments

| Publisher / configuration | Input | Prefill (t/s) | Timing / workload qualification |
|---|---:|---:|---|
| strix-alloy maximum-prefill setup | 16,384 / 65,536 / 131,072 / 251,904 | **1,031 / 993 / 925 / 812** | server-reported prompt timing, **no drafter**, ubatch 16384, warm reps |
| olliehm updated serving config | ~8k–17k | ~660 | **drafter attached**; batch/ubatch 2048 |
| **Halogen 0.5.3 internal prefill bench** | 8,192 / 32,768 / 131,072 | **~1,246 / ~1,424 / 1,358** | engine's own bench, cold single-call real text; **not an HTTP sweep** |
| Halogen HTTP/SSE sweep | 2,048 / 8,192 | 812 / 1,041 | different boundary from the row above |
| CIRU IU4 v4.4 incident replay | 12,960 | 889.13 | qualified MTP3 config; matched against its own control |
| CIRU IU4 v4.4 deep cold | 245,760 | 761.25 | separate workload, limited repetition scope |

**Halogen reaches substantially higher prefill than we do** — ~1,424 vs our 1,031 at 32k — and that is the
honest headline of this table. It is measured with a different instrument (their engine bench vs our server
timing), on a differently configured machine, so a matched comparison is still missing; but the gap is far too
large to be instrument noise and we should not imply otherwise.

Our maximum-prefill row **excludes the drafter** while olliehm's cited update **includes it**, so those two are
not comparable either. Do not combine our fastest no-draft prefill with the 45.31 short-chat MTP rate and
present the result as a measured 32k request.

**Halogen's config caveats, which matter for comparability:** their published conditions are one 128 GB machine
at ~**85 W sustained with IOMMU off**. Our numbers are VBS + hypervisor + HVCI active on a box whose IOMMU
setting we did not change. Their competitor rows are also their own published numbers, not head-to-head runs.

---

## 6. What strix-alloy actually does differently

| Area | Documented choice | Defensible claim |
|---|---|---|
| Engine foundation | `pwilkin/llama.cpp` `strix-halo` lineage — MMB, QSA/indexer, PLE, HC kernels inherited | we inherit that kernel set; **credit stays with its authors** |
| Windows integration | native TheRock HIP build, gfx1151, HIP graphs, matching runtime DLL deployment | a documented Windows-native path — **not exclusivity** |
| Weight/runtime pairing | IQ4_NL PROJFIX vs olliehm's UD-IQ4_XS | our published observations favour this pairing on this fork; file size or average bits alone does not explain it |
| Draft packaging | shared Q8_0 sidecar borrowing target tensors | avoids storing/loading borrowed tensors; does not by itself raise acceptance |
| Batch configuration | separate maximum-prefill (16384) and served configurations | which configuration produced each row must stay attached to it |
| Draft policy | `n-max 2` retained after repaired comparisons | supported for the tested cells; `n-max 4` is **not** a demonstrated 10% chat win |
| Measurement work | claim ledger, retractions, workload identity, warm/interleaved harness fixes | better auditability — **not** another kernel speedup |

**Do not claim MMB explains a decode advantage:** our own applicability ledger records that its large-batch path
is not the ordinary decode path, and `MMID_512` (the halo-box kernel we ported) provably never executes during
decode at all. **Nor claim another engine lacks equivalent optimisations** without auditing its exact revision.

Exact dtype provenance matters: the ledger acknowledges older Q6_K/F32 mixtures in historical censuses, so do
not claim uniform tensor types across all historical measurements.

---

## 7. Correctness and limits belong beside the performance table

Our ledger records that **state restoration after 0/1/N accepted tokens, and full multi-turn / depth-band /
retrieval / tool-output gates, are not done**. Completion at 251,904 tokens establishes **capacity and
execution, not long-context accuracy**. Serial-vs-verify numerical divergence is deterministic and sub-0.2-nat
in the dense regime, but its **cause is not established** and a near-tie magnitude does not make it benign
([acceptance-width-report](acceptance-width-report.md)).

olliehm publishes sequence-level gate results; Halogen publishes serial/speculative identity checks; CIRU
records its numerical and lifecycle checks with stated scope limits. These are **each publisher's evidence**,
not independent certification or proof of equal quality between quants.

---

## 8. The benchmark that would support a real head-to-head

Freeze a shared prompt suite spanning instructions, document continuation, coding-agent turns and retrieval,
with **occupied depth stated separately from capacity**. Use identical prompt/token IDs where tokenizers allow.
Run serial and speculative serving as separate modes. Keep output budgets, thinking, sampling, cache policy and
stream count explicit.

Either use the same exact weights to compare engines, or a predeclared quality budget to compare complete
deployments — those answer different questions. Fix and record power, cooling, driver/runtime revisions and
weight hashes. Preserve all repetitions, warm-up rules and output counts, and include variability.

Per request, retain at least:

```text
engine + source / binary / runtime hashes
weight + tokenizer hashes and tensor-type manifest
prompt ID/hash; token count; occupied depth; allocated capacity
serial/MTP; proposed / accepted / emitted counts; proposal source
sampling and thinking; output budget; stop reason; actual output count
batch/ubatch; graph state; cache state; single vs concurrent streams
prefill time; decode time; TTFT; total request wall time
rep index; warm-up exclusion; output/quality validation
```

Until that exists:

> **strix-alloy runs Qwen3.8-Flash-Next natively on Windows. Its published observations include 31.49 t/s
> synthetic serial evaluation, 45.31 t/s served MTP on one short instructed prompt, and 31.0–32.8 t/s MTP in a
> separate long-context ladder. Halogen, CIRU and olliehm publish other strong results under different
> workloads and runtime conditions. These figures demonstrate operating points, not a matched cross-engine
> winner.**

---

## Reproduce / verify

- Our figures: `docs/benchmarks/canonical-llama-bench-20260916.md`,
  `docs/benchmarks/bench-gap-resolved-20260917.md`, README benchmark tables.
- Claim status and retractions: `docs/benchmarks/CLAIM-LEDGER.md`.
- The ~13% `llama-bench`-vs-server difference is **resolved as harness-side, with the token stream excluded**
  (server fed llama-bench's own distribution: 1010.5 vs 892.59 t/s; random vs prose −1.0%). The remaining work
  is localising which part of the harness, not whether the gap is real. See
  `docs/benchmarks/bench-gap-resolved-20260917.md`.

## Sources and revisions

Third-party performance remains publisher-reported. All were re-fetched and checked on 2026-09-17; none were
taken on trust from a previous summary.

| Source | Revision |
|---|---|
| strix-alloy | `199b8ec` (this repository) |
| Halogen | `peonist-ai/halogen-flash-server@501dbcdd` |
| olliehm | `olliehm/qwen-flash-next-windows@09b1b14e` |
| CIRU IU4 | `ciru-ai/Qwen3.8-Flash-CIRU-STRIX-IU4@111a6638` |
| ilintar / pwilkin | `pwilkin.github.io/strix-halo` (live page, no pinned revision) |

**Verification notes from this pass, so a reader knows what was actually checked:**

- Halogen's internal prefill (1,246 / 1,424 / 1,358), HTTP sweep (812 / 1,041), serial ladder (37.6 / 36.1 /
  34.1) and ten-prompt MTP mean (45.3) all confirmed.
- olliehm's 20.3 t/s @8k confirmed as **explicitly labelled a stock `llamacpp-rocm b1326` baseline**; final
  stack 38 t/s with `n-max 4 p-min 0.75`.
- CIRU's figures came from `docs/qualification/v4.4.0/IU4-RESULTS.json` (the prose qualification file would not
  render): incident replay 37.79 → **44.53** decode and 824.28 → **889.13** prefill; HE0–9
  **60.351** → **64.067** with Boost; 240k cold 7.62 → **21.14**. The JSON also flags
  `prompt_work_comparable: false` on two prefill cells — hence the qualification attached to the 889.13 row.
- ilintar's `1204.31 / 26.28` at depth 0, batch/ubatch 16384, `--load-mode none --lazy-mode on-direct`, and the
  statement that HIP graphs do not engage on prefill, all confirmed on the live page.
