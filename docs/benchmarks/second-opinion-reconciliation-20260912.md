# Second-opinion reconciliation — Flash-Next plan vs independent review (2026-09-12)

The founder submitted the plan in `second-opinion-prompt-flash-next-20260912.md` to a second model.
Its reply is reproduced/answered here: what it gets right (and changes our plan), where it conflicts
with **our own measured** data, and where it is unsupported. Headline verdicts from the review:
**Halogen as a shared default = no-go until it passes a whole-machine residency + Brain-latency test;
native-Windows llama.cpp/Vulkan = best default candidate; selecting by standalone tok/s = wrong.**

Our position: the review's *central reframing* is correct and we adopt it. Several of its specific
numbers are publisher figures or general claims, and one conflicts with our own measurements; the
running Flash-Next test will settle those. No configuration is being adopted on this review alone.

---

## 1. Where the review is right — and we are changing the plan

### 1.1 The selection criterion was wrong (the most important correction)

We were ranking by tok/s. The review says the criterion must be **"correct world updates completed
within their deadline *while* the Brain still meets its few-hundred-ms first-token target."** Neither
of our two shapes demonstrates that. **We have never measured gemma4's first-token latency while a
World Engine is mid-prefill on this box.** That is now the deciding test, ahead of any throughput
number. (Our own previous warning — the carve-out/memory probe froze the machine — makes co-load
testing something to do carefully, with watchdog and bounded memory.)

### 1.2 Budget conflation

The review is right that **physical RAM, device-allocation budget, and commit limit are three
different numbers** and must not be summed from arbitrary counters. Our own short-hand ("pool =
64 GiB + ½ carve") is loose — our *measured* device pool was ~**68.6 GiB at 0.5 GiB carve** and
~**119.9 GiB at 96 GiB carve**, which is `≈ 68 + ½·carve`, not `64 + ½·carve`. We will record the
three budgets separately going forward.

### 1.3 The Halogen-halogen co-residence arithmetic

Taking our own numbers: non-lookup weights `115.55 − 47.7 = 67.85 GiB`; device allocation for a
524,288-position pool ≈ **35 GB** (documented); brain+STT+TTS 20 GiB; OS/WSL 8–12 GiB. Even at the
favourable end **≈ 128.45 GiB, over capacity before any useful lookup-cache residency or Voice
Studio.** We accept this as a **planning rejection of the 512k-pool Halogen shape as a shared
default.** It does not prove Halogen can't run here — its n-gram table is pageable and we will test a
*smaller* pool — but the proposed "115 GiB + 524k pool beside everything else" is not defensible.

### 1.4 Two label facts we got wrong

- **Overlay sizes are swapped in the older halogen doc.** Verified against HuggingFace: **quality
  `overlay.hgn` = 2.396 GiB (2,572,466,560 B)** and **speed `overlay-speed.hgn` = 2.308 GiB
  (2,478,095,488 B)**. The model card (2.40 quality / 2.31 speed) is the correct one; our
  fit-analysis's "2.4 GiB quality" was right and the architecture doc's "2.31 GiB quality" was the
  speed file. Pin by filename+sha, not by label.
- **The two lookup tables are different sizes and must not be mixed.** Halogen's n-gram table ≈
  **47.7 GiB** (paged through host page cache). The GGUF's PLE (`per_layer_token_embd`) table ≈
  **26.8 GiB**. Our second-opinion prompt used "47.7 GiB" in the *llama.cpp* tactics bullet — that was
  our error and the review caught it. Corrected: llama.cpp PLE = 26.8 GiB.

### 1.5 MTP is not the main cold-prefill lever

The review's arithmetic is right and important: for a 65,536-token prompt at 300 tok/s prefill and a
256-token generation, MTP moves total time from **229.8 s → 225.1 s (2.1%)**, even though it lifts
decode 71%. **For a cold-prefill-heavy World Engine, prefix reuse and prefill speed dominate; MTP
matters on warm turns and long reasoned generations.** This reorders our priorities (prefix caching
first).

### 1.6 MTP risks are real, not just "CJK leak at temp>0"

Adopted: both **#28243 and #28118 are still draft PRs**; there is a reported **hard abort when
on-device recurrent state spans multiple cell ranges**; and the checkpoint PR's own Strix numbers
(**32.4 t/s serial vs 6.2 host-checkpoint MTP vs 41.5 device-checkpoint MTP**) show MTP can *hurt*
without the right checkpoint path. We will:
- run **serial-vs-serial first** on the same binary, then serial-vs-MTP, to separate an MTP
  regression from pre-existing nondeterminism;
- start at **depth 3**, then sweep off/1/2/3/4 on *our* world/german workloads;
- add a **guarded fallback** rather than accepting a process abort on unusual state layouts.

### 1.7 `--load-mode none` ≠ "PLE on disk"

Adopted: `--load-mode none` disables ordinary mmap loading but the loader still creates mappings when
lazy loading needs them; **it does not by itself force the PLE table to disk.** We must verify, on the
exact pinned build, that the PLE tensor takes the lazy CPU path and that startup logs report lazy
loading (not full materialization).

### 1.8 IOMMU — budget zero gain on our path

Adopted. The controlled experiment's large gains (+26–32%) were **Vulkan/dense on native Linux**; its
**ROCm gains were only ~1.8–6%**, and one MoE-Q8 saw +20%, so "MoE = 2–8%" is also too broad. IOMMU is
a kernel parameter and **does not apply to the Windows-owned DXG path at all**. We drop it as a
lever for the current plan.

### 1.9 The pagefile is a ceiling, not capacity

Adopted. 163,840 MB raises the **commit ceiling**; it adds no physical RAM and does not raise the GPU
residency budget. "The 262k profile starts after raising the pagefile" is **not** evidence it is
usable — we must measure hard faults and latency under steady load.

### 1.10 MTP at temp 0 is not a blanket correctness guarantee

Adopted. Exact greedy speculative decoding should reproduce the target's greedy sequence, but a new
implementation with changed batching / FP reduction / recurrent rollback must be tested. Also,
Halogen's cache **mode 2 (default) can differ from cold execution; mode 1 is the stricter
reproducibility mode** — so "temp 0 ⇒ identical output" is two separate properties (spec decoding and
cache semantics) and both must be tested.

---

## 2. Where the review conflicts with our own measurements — and the test decides

### 2.1 "The shim makes a shadow copy" — true for the 27B, **not applicable to Flash-Next**

The review assumed our `hipshim` would carry over. It does not: the **27B `halogen` engine** pins
(`hipHostRegister`), which fails on DXG on file-backed mmap, so our shim hipMalloc+hipMemcpy's the
mapping into a device buffer — that *is* a full second copy, and the review is right to flag it. But
**`flash_serve` (Flash-Next) has a built-in `Pin::None` mode** (`HALOGEN_FLASH_PIN_TRUNK=0`) that
copies the trunk itself and needs **no shim**. So the shim's shadow-copy concern does not apply to the
Flash-Next path we are testing. We will still verify actual residency from the engine's own startup
line.

### 2.2 "`PIN_TRUNK=0` preserves Halogen's published speed — unestablished" — correct

The review is right that we have not measured it. The engine's own text warns unpinned "costs several
times the decode speed." Our imminent run **is** the measurement: it prints the effective mode and
per-request milliseconds. We will report unpinned (and, if memory allows, pinned) numbers rather than
transfer the published figures.

### 2.3 Halogen prefill figures — use the publisher's numbers, then measure ours

The review cites the current README as **1,246 @8,192 / 1,424 @32,768 / 1,358 @131,072**, and flags
our "250–380 @60k" as an unverified Reddit fragment. Agreed — both are non-local. Our run reports its
own cold-prefill milliseconds; that becomes the reference.

### 2.4 "MoE vs dense is the whole story" — too strong, accepted

Adopted: it explains most of the *decode* contrast, but not long-context kernel efficiency, lookup
page faults, recurrent prefill, or scheduling. Our own IOMMU-style data (two quantizations of the same
MoE differing) supports this.

---

## 3. Where the review adds detail we did not have (record it)

- **Halogen admission pauses** are documented in seconds (a ~28 s chunk in one configuration) — a
  concrete reason to **measure Brain interference** rather than assume fair GPU sharing.
- **Halogen Responses endpoint** returns no `reasoning_content` and has no response-store/cancel
  endpoint — so "missing thinking traces" is endpoint-specific, not a blanket agent breaker.
- **Q8 KV sizing:** ~24 KiB/token f16 → ~12.75 KiB/token Q8_0 for full-attention layers
  (65,536 → 1.50 vs 0.80 GiB; 262,144 → 6.00 vs 3.19 GiB), excluding recurrent/draft/workspace.
- **CIRU IU4 v3** card: **369.81 t/s prefill, 24.22 t/s gen @65,536, 177.32 s to first streamed
  content**; package ≈ 73.95 GiB target + 48.83 GiB PLE + 3.85 GiB head — *not* a smaller-resident
  solution, and qualified on native NixOS, one workload at a time.
- **EngramHalo's chunked Gated DeltaNet prefill kernel** is documented as *not active* in its
  published measurements — so its numbers are not a promise.
- **Proposed acceptance budgets** (adopt as initial targets, not gospel): cold-KV prefill 8,192 ≤20 s
  (≥410 tok/s), 32,768 ≤90 s (≥365 tok/s), 65,536 ≤180 s (≥365 tok/s); World decode ≥20–25 tok/s at 64k
  depth; warm append 128/512/1,024 → first token ≤1/3/5 s; Brain under concurrent World work
  p95 ≤300 ms / p99 ≤500 ms.
- **Measure three "cold"s separately:** cold-KV/warm-process (the steady-state rebuild), cold-KV +
  cold-lookup-cache (SSD dependency), and cold-process (startup). Never let one engine enjoy warm PLE
  pages while the other faults from disk.

---

## 4. What we adopt vs defer

**Adopt now (change the plan):**
1. Decide by **correct world updates within deadline + Brain latency under co-load**, not tok/s.
2. **Prefix preservation** is priority #1 (keep authoritative state outside the model; append compact
   event deltas; measure cache hit rate).
3. **Halogen is not the shared default.** Test it as a controlled challenger with a **smaller pool**,
   alone then co-loaded; do not transfer native numbers.
4. **llama.cpp/Vulkan one bounded slot, verified lazy PLE, warm-prefix reuse, MTP only after it earns
   its place (depth 3 start, serial-vs-serial baseline first).**
5. Test **smaller prefill microbatches (32/64/128/256)** against the co-loaded Brain, not just `-ub 256`.
6. Record the **three budgets** and the **three colds**; pagefile is a ceiling, not capacity.
7. Drop **IOMMU** as a lever for the DXG path (budget zero gain).

**Defer / requires new evidence:** the local UMA patch (obtain the diff + base commit + reproduce the
A/B first); the agentionai Vulkan fork (change one variable at a time); Moe-slices (model surgery, not
lossless); NPU/FastFlowLM (shares the machine, not a first intervention); CIRU IU4/Orca (separate
runtime/checkpoint needing lineage + memory + quality validation).

---

## 5. The ordered test programme (agreed)

1. **Memory + shim audit** — carve-out, Windows budgets, WSL limit, resident-service peaks, whether
   any path makes shadow copies. (Our Flash-Next path should have none.)
2. **Brain latency baseline** with STT/TTS active and no World inference.
3. **llama.cpp candidate without MTP**, one slot, bounded context, verified lazy PLE; 32k cold prefill
   **while exercising the Brain** → earliest viability test.
4. **MTP correctness + state handling**, then sweep depth and microbatch under co-load; guarded
   fallback for unsupported layouts.
5. **8k/32k/64k cold-and-warm matrix**; reject configs that win throughput but break Brain latency.
6. **Halogen as challenger** — alone, then with all services, smaller pool, exact overlay/shim/pin.
7. Only then: UMA patch, specialised forks, alternative quant/runtime packages.

The Flash-Next engine run now in progress feeds steps 1 and 6 directly (it prints its measured fit,
effective pool, pin mode, and cold-prefill/decode milliseconds).

---

## 6. Bottom line

The review's core is sound and we have changed the plan to match: **stop deciding on tok/s, protect
the Brain, make prefix reuse the first lever, treat Halogen as a challenger not a default, and require
co-load evidence.** Its one configuration-level over-reach is that it inherited our 27B shim
assumption; Flash-Next's own `Pin::None` mode removes the shadow-copy concern for the path we are
testing. Its biggest open question — *does the Brain keep its latency while the World Engine
prefills?* — is exactly the test our measurements have not yet run, and it is now first in the queue.

## 7. Addendum (same day): the measurement resolved the Halogen question

The engine run finished after this reconciliation. Measured on this box (`halogen-flash-next-measured-verdict-20260912.md`):

- **`Pin::None`**: stable, full 262,144 context in **25.5 GiB**, correct output — but **0.32 t/s**
  decode (129.5 s cold / 61.5 s warm prefill for 57 tokens). Unusable.
- **Pinned (via `hipshim`)**: the shim reaches the fast path but **bypasses the engine's pin guard**;
  host RSS climbed through 57 GB and Windows free physical fell to **1.1 GB** before we killed it.

So the review's verdict is **confirmed with measurement, and strengthened**: the llama.cpp/Vulkan
shape is the default, and Halogen is a dedicated-host challenger. The one thing the review got wrong
in the other direction is the shim: for Flash-Next it is *required* to reach the pinned path and is
*unsafe* here — whereas for the 27B engine it was the correct fix. The shim must not be used with
`flash_serve` on this host.
