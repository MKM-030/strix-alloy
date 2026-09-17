# Engine comparison: strix-alloy vs olliehm — what is actually different

Written 2026-09-16 after the question *"is ours basically a clone of his?"* It is not, and the honest
answer is more interesting: **we run different engines, from different lineages, with different
patches, and we each win a different benchmark.**

## Short answer

| | |
| --- | --- |
| **Different kernel?** | **Yes — different fork entirely.** We run `pwilkin/llama.cpp` @ `strix-halo` (ilintar). He runs upstream `ggml-org/llama.cpp` + `stew675/llama-cpp-rdna-boosts` (Stew Forster). |
| **Different patches?** | Yes. Our base already carries the `qwen4exp`/QSA/PLE work; his applies it as mailbox patches onto a different tree. |
| **Bridge between them?** | **No.** Neither repo wraps the other. They are independent. |
| **Better numbers?** | **Split.** We are much faster at prefill and at non-speculative decode. He is faster at speculative decode on a short prompt, at a much higher acceptance rate. |

## 1. Engine lineage — the root of the difference

**Ours (`strix-alloy`).** `git remote -v` → `pwilkin/llama.cpp`, branch **`win-native`**, based on
`strix-halo` `40a9f4d0`. The tree we build already contains this fork's own arch work:

```
40a9f4d0 hip: extend MMB quants and fuse Flash-Next F32 PLE
d67d5883 hip: enable sparse QSA decode and incremental indexer state
0f295019 qwen4exp: skip unused HIP decode indexer work
ac1ebb4e strix: compile in the tuned defaults and drop the env gating
```

Plus our own three commits on top (`_WIN32` prefetch stub, d2t draft-vocab trim + on-device
speculative checkpoints, hidden-dump harness) and two timing commits.

**His (`olliehm/qwen-flash-next-windows`).** From his own build doc: upstream `ggml-org/llama.cpp`
cloned fresh, then patches from **`stew675/llama-cpp-rdna-boosts`** applied — described as carrying
"the qwen4exp/MTP work from upstream PRs **#27836, #28243 and #28118** plus RDNA perf blocks". He
deploys through **Lemonade** with MSVC-ABI builds and a ROCm 10.1 TheRock nightly.

So the load-bearing difference is **which kernel set you get for free**:

| | our fork (pwilkin/ilintar) | his (upstream + Stew Forster) |
| --- | --- | --- |
| MMB large-batch kernels | **yes** (`mmb.cu`, `mmb-quant.cuh`) | no |
| fused F32 PLE | **yes** (`ple-conv.cu`) | no |
| sparse QSA decode + incremental indexer | **yes** (`qsa.cu`, `qsa-decode*.cuh`) | via upstream PR, not the fork's |
| hyper-connection fused kernels | **yes** (`dsv4-hc.cu`, `hc-mix.cu`, `hc-cn.cu`) | no |
| top-k / Lightning indexer tuning | **yes** (`top-k.cu`) | no |
| MTP/NextN draft head | yes (fork) | yes (PR #28243) |
| recurrent-state checkpoints | yes (fork) | yes (PR #28118) — and he documents it as *required* |
| RDNA perf blocks | partial | **his** (`rdna-boosts`) |

**That is why our prefill is ~1.5× his**: his engine has no MMB path at all, so his prefill runs
through generic kernels. Conversely his `rdna-boosts` set is tuned work we do not carry.

## 2. The bridge question

- **Between us and olliehm: there is none, and there is nothing to build.** Both serve the
  OpenAI-compatible `llama-server` HTTP API, so a client can talk to either — that is API compatibility,
  not a bridge.
- **The Halogen bridge is a different thing entirely and it is NOT in this repo.** Searching the whole
  tree for `.hgn`/`flash_serve`/halogen-bridge code returns **docs only, no code**. The artifacts that
  exist are outside any repo, at `C:\AI\models\`: `hipshim.c` (an `LD_PRELOAD` shim making Halogen's
  checkpoint load on WSL/DXG by substituting `hipHostRegister` with `hipMalloc` + copy),
  `run-halogen-shim.sh`, and shim logs. **Halogen's engine itself is no longer present** (no
  `flash_serve` binary anywhere on disk).
- **Halogen was tried and abandoned on this machine, for a documented reason**: Flash-Next on Halogen
  needs a pinned map of 115 GiB, which needs ≥86.55 GiB free host RAM *and* ≥90.75 GiB device pool
  simultaneously — impossible on a 128 GB UMA box. `HALOGEN_FLASH_PIN_TRUNK=0` refuses the
  GGUF-derived Q8S32 expert layout outright. Verdict recorded in
  `docs/benchmarks/halogen-wsl-verdict-and-decode-sweep-20260913.md`: *"on Windows/WSL, Flash-Next runs
  on the open fork; Halogen runs the 27B but not Flash-Next."* The 33.4 GiB 27B `.hgn` is still on disk;
  the 115 GiB Flash-Next `.hgn` set is still on disk but unusable here.
- **The halogen shim should move to its own repo** (or to the REV-N repo) — it is not Flash-Next engine
  work. This repo is being cleaned to Flash-Next only.

## 3. Direct benchmark comparison

> ### CORRECTION (2026-09-17): the decode rows below were unfair, and the "ours, +42%" claim is withdrawn
>
> External review checked olliehm's pinned benchmark file. Its **20.3 t/s @8k is explicitly labelled
> "Stock `llamacpp-rocm b1326`, no MTP (baseline)"** — a stock upstream baseline, **not the serial performance
> of his final patched engine**. His final stack is the 38 t/s MTP row.
>
> The table below paired our final engine against his *baseline* and declared "+42%", which compares two
> different things: ours-as-shipped against his un-optimised control. **Withdrawn.** A defensible serial
> comparison would need his final engine's serial number, measured without the drafter — he does not publish
> one, so we have no serial win to claim here.
>
> Also withdrawn from this document's framing: any **"winner" column**. Every row is a separately published
> observation on unmatched workloads, and the "~1.5×" prefill figure pairs our server-reported, no-drafter
> timing against his timing with the drafter attached. Both remain interesting operating points; neither
> settles a ranking.
>
> Halogen — absent from this document entirely — publishes a **higher** prefill (~1,424 t/s @32k internal
> bench) and **higher** serial decode (37.6/36.1/34.1) than ours. The corrected, mode-separated comparison
> with pinned revisions is `engine-comparison.md`.

| metric | olliehm | strix-alloy | note |
| --- | ---: | ---: | --- |
| **prefill** | ~660 t/s @8k–17k (**drafter attached**) | 993 @65k, 1031 @16k (**no drafter**) | different instruments and drafter state — not a ratio |
| ~~decode, no MTP @8k~~ | ~~20.3~~ **stock baseline** | 28.8 | **withdrawn** — his row is a stock control, not his engine |
| decode, MTP | **38 t/s** (depth not published) | 31–47 t/s (content-dependent) | his headline; different depth and aggregation |
| draft acceptance | **85–100%** | 40–92% | content-dependent on both — not comparable as single figures |
| context | 262,144 | 251,904 verified | he claims the trained max |
| footprint in carve | 74.0 GB | ~74 GB (same weights + KV) | equivalent |

### The MTP row needs a caveat, and we tested it

His `38 t/s` is published **without a depth**, and his own config is `n-max 4, p-min 0.75` — a
*different operating point* from ours (`n-max 2, p-min 0.0`). `p-min 0.75` only proposes
high-confidence drafts, which is exactly why his acceptance is 85–100%.

**We had never tested that regime** (our n-max 3–8 sweep ran at default `p-min 0.0`), so we ran his
exact flags on our engine at 65k on 2026-09-16:

| config | decode @65k | acceptance |
| --- | ---: | ---: |
| ours: `n-max 2, p-min 0.0` | **33.08–33.46 t/s** | 65% |
| his: `n-max 4, p-min 0.75` | 26.42 t/s | **96%** (115/124, 119/124) |

**His config reproduces his acceptance rate on our engine — but it is 20% slower here.** Higher
acceptance did not mean higher throughput: at `n-max 4` each round costs 4 draft steps plus a 5-row
verify, and with `p-min 0.75` the round often stops early anyway, so the extra draft machinery is paid
for little gain. **This is the single most useful thing we learned from his repo**, and it is a
*negative* transfer: his acceptance figure is real, his decode figure does not transfer to our fork's
kernel mix.

## 4. What we should learn from him

**Short-term, cheap, do next:**

1. **`--ctx-checkpoints` / recurrent-state checkpointing is on by default in our path but he documents
   it as mandatory.** He reports MTP is a **net loss** without PR #28118 (his pre-trial: 21.4 → 5.1
   t/s). Our fork carries the equivalent (`24559500` "on-device speculative checkpoints"), so we are
   covered — but we have never A/B'd checkpoint count. Worth one experiment.
2. **His correctness gates are the model to copy.** He validates with *sequence-level* gates —
   single-turn, multi-turn, depth bands, ~24k needle retrieval — and warns that **MTP on HIP can show
   2× tok/s while emitting collapsed text**. Our own A0/acceptance work found the same class of
   problem from the numerical side. Adopting a minimal version of his gate set (multi-turn + depth-band
   + needle) as a pre-publish check would have caught our own `indexer.top_k` cliff earlier.
3. **His fit arithmetic is cleaner than ours.** He publishes a component table (weights 61.2 + drafter
   3.2 + KV 8.75 + compute ~2 = **74.0 GB** in carve, with the 26.8 GiB PLE table outside the carve).
   We should publish the same table from our own numbers for direct comparison.
4. **`n-max 4, p-min 0.75` is worth keeping as a *config option*, not our default** — it is the right
   trade when acceptance matters more than throughput (e.g. long generations where verify cost is
   amortised differently), and we now have the measurement to say so.

**Medium-term:**

5. **His `stew675/rdna-boosts` patch set is the one component we do not have.** His engine lacks our
   MMB/QSA/PLE kernels; ours lacks his RDNA blocks. **Auditing that patch set for anything applicable
   on top of our fork is the highest-value external source we have not mined.** This is a concrete,
   bounded task: diff it against our tree, keep what is backend-portable.
6. **He confirms the UD-IQ4_XS vs our PROJFIX split is a real trade, not a mistake on either side.**
   He picked IQ4_XS for *fit margin* (the only ≥Q4 quant fitting full 262k context with ~22 GiB spare);
   we picked PROJFIX for *speed* on this fork's IQ4_NL kernels. Both are right for their engine —
   because his engine has no IQ4_NL fast path, PROJFIX would buy him little.

**Long-term / not from him:**

7. The draft-head fine-tune remains our own track (he ships a full 3.2 GB Q8_0 head; we borrow the
   trunk LM head with a shared 2.6 GB sidecar).

## 5. Consistency audit — what we document vs what runs

Checks performed on this tree, because the question exposed a documentation risk:

| claim in our docs | verified? | finding |
| --- | --- | --- |
| "the fork's MMB fast paths explain the PROJFIX decode gain" | **partly wrong** | **MMB is gated at `T ≥ 512` (`mmb_min_t()`), so it is OFF during decode.** It explains the *prefill* gain. The decode gain is real but must come from the decode-path kernels (QSA/top-k/HC/`mmvq`), not MMB. The README attribution was corrected. |
| "177B parameters" | **wrong** | 120.8B expert + ~4B other = **~125B transformer**; the extra 51B is the PLE n-gram table. Corrected, and reconciled against our own 67.9 GB expert census. |
| "only Windows-native stack with these numbers" | **wrong** | he was there first on decode; corrected to a head-to-head. |
| cross-warp reduction as the decode bottleneck | **closed** | `nwarps == 1` on gfx1151 for every executed MMVQ specialisation (our own coverage probe). |
| K-split as the small-R fix | **retracted** | measured per-**op**, not per-block; K-split adds ops. |
| halogen bridge in the code | **not in the repo** | docs only; the shim lives outside at `C:\AI\models\hipshim.c` and belongs in its own repo. |

## Artifacts

`kernel-work/compare-olliehm-mtp.ps1` (the flags test above), `kernel-work/param-count-check.py`
(parameter arithmetic), `kernel-work/scan-history-secrets.sh`. External sources fetched 2026-09-16 from
`github.com/olliehm/qwen-flash-next-windows` (`README.md`, `docs/benchmarks.md`,
`docs/model-and-flags.md`, `docs/build-engine-windows.md`).
