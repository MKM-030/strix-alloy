# Frontier-review corrections + measured round timing (2026-09-15, evening)

The frontier model reviewed our work and found several real errors. This documents which ones I verified,
what I changed, and the new direct measurement that settles the biggest dispute.

## Correction 1 (mine, confirmed): the @16k MTP decode figure was mis-transcribed

`current-numbers-20260915.md` printed **30.2 t/s @16k**. The raw `ab-shared-n2.json` rep-1 row is
**32.80 t/s (139/230 accepted)**. 30.2 is the **8k** figure. Decode at 16k is *higher* than at 8k because
acceptance recovers (70% at 16k vs 63% at 8k). Fixed in the doc. This is exactly the kind of silent 8%
baseline error the review warned about — it matters because "30.2" would have made our gap to Halogen look
33% instead of 24%.

## Correction 2 (mine, confirmed): `r ≈ 0.47` was a fitted artefact, not a measurement

I claimed "one draft step costs half a target step". The review said a constant-cost fit absorbs a
width-dependent verify cost into the apparent `d`. **It does.** The fork already accumulates the real
timers (`t_begin_us`, `t_draft_us`, `t_accept_us` in `common/speculative.cpp`), printed at trace verbosity
(`-lv 4`) — no rebuild needed. Measured, PROJFIX, ub 2048, MTP n-max 2, 8k prompt:

```
statistics draft-mtp: #calls(b,g,a) = 1 67 67, #gen drafts = 67, #acc drafts = 37,
  #gen tokens = 134, #acc tokens = 53, #mean acc len = 1.79,
  #acc rate/pos = (0.552, 0.239), dur(b,g,a) = 0.004, 738.044, 0.354 ms
```

| phase | total | per round | share of decode wall |
| --- | ---: | ---: | ---: |
| `begin` (refresh) | 0.004 ms | 0.0001 ms | ~0% |
| **`draft` (drafting)** | **738.0 ms** | **11.02 ms** | **16.1%** |
| `accept` (accumulation) | 0.354 ms | 0.0053 ms | 0.01% |
| **residual (target verify + host)** | **3852.2 ms** | **57.49 ms** | **83.9%** |

**Measured draft : residual = 0.19**, not 0.47. The fitted `r` was conflating the width-3 verification
cost into the draft cost. The review was right.

**Also new and useful:** the fork reports **per-position acceptance** (`0.552, 0.239`) — position 1 accepts
55%, position 2 only 24%. That is the shape of the depth problem, and it is now directly observable.

**Caveat on this specific run:** aggregate acceptance was **40.9%**, lower than the 50.6% we measure at 8k
in the A/B (and 62–63% in other runs). I have not yet explained the gap — possibly the trace logging, the
first-request effect, or a different prompt-cache state. The *structure* (draft ≈ 16%, accept ≈ 0,
verify ≈ 84%) is the finding; the exact percentages should be re-measured on a warm, high-acceptance run.

### What this does to the levers — corrected arithmetic

Using the measured round cost (68.5 ms, 1.81 tokens emitted):

| lever | modelled effect | verdict |
| --- | --- | --- |
| make the draft **free** | 68.5 → 57.5 ms/round → **~31 t/s** | **cannot reach 42** |
| acceptance 75% → 90% at depth-2 | `(1+0.9+0.81)/(1+0.75+0.5625) = 1.172` → **+17.2%** | real, the review's figure, not my +21% |
| same at depth-1 | `1.9/1.75 = 1.086` → **+8.6%** | — |
| halve the *fixed* 70% of draft | draft 11 → 7.2 ms → **+5.5%** | small |

**The headline consequence: the draft head alone cannot get us to 42 t/s.** With draft at 16% of wall,
even eliminating it entirely tops out near 31 t/s at this acceptance. The dominant cost is the target
verify (84%), so the two real levers are **higher tokens-per-round (acceptance)** and **faster/smaller
verification** — not a cheaper drafter. This *reorders* my earlier recommendation: I had ranked the
draft-architecture shrink (lever B) above acceptance (lever A); on the measured numbers **acceptance is
the larger and more tractable lever**, matching the review's ranking.

## Correction 3 (the review's, confirmed): our measurements all ran with the hypervisor ON

I said the IOMMU finding was "not testable on Windows". That was too strong, and the read-only collector
proves the machine state I was assuming is not what I assumed:

```
HypervisorPresent        = true      <- Windows hypervisor IS running in all our runs
VirtualizationBasedSecurityStatus = 2 (running)
SecurityServicesRunning  = [2]        (HVCI)
SecurityServicesConfigured = [2, 3]
RequiredSecurityProperties = [1, 2, 3]   <- 3 = DMA protection is REQUIRED on this box
```

So "we shut WSL down" never meant "no hypervisor" — `wsl --shutdown` stops the WSL utility VM, not the host
hypervisor. The review is correct. Whether the 8060S's GPU traffic is IOMMU-translated is a **separate,
testable question**, and the BCD controls (`hypervisorlaunchtype`, `vsmlaunchtype`,
`hypervisoriommupolicy`) let us A/B it. See `windows-boot-ab-20260915.md` for the prepared experiment.

Also corrected from the original source table (it is more restrictive than I first summarised): the
**ROCm** gains were **1.8–3.2% (MoE)** and **3.7–6.0% (dense)**; the 26–32% figures were **Vulkan**. Applied
to our 1057 t/s that is **1076–1091 t/s** for the MoE ROCm case — hypothetical, and short of 1204.

## Correction 4 (the review's, and it matters for funding): the training plan's data pipeline

The review is right that a **stateless row-wise harness can reproduce tensor shapes while failing to
reproduce the inference computation** — the MTP block has its own attention/KV path, position inputs, and
per-stream hyper-connection processing. My harness already writes `(h, token)` rows; what it does *not* yet
do is prove sequence-level parity. The correct gate (which I had listed but not emphasised enough) is:
**reproduce first-step logits, top-token agreement, positional alignment and short rollouts of the
untouched head against the live inference path** before any training. Also accepted: store features
chunked and stream the full-vocab loss (a million rows of features is 20.5 GB; full fp16 logits for a
million tokens would be 497 GB — do not materialise them).

## What I did *not* do, and why

The boot-state experiment requires **rebooting the machine into a modified boot entry**. That is a
hard-to-reverse, disruptive action on the founder's workstation, the review itself says to have local
console access and the BitLocker recovery key on hand, and this box reports **DMA protection as a
required security property** — so a no-hypervisor boot may be refused or may need BitLocker recovery.
I prepared everything and verified the current state read-only, but **I have not changed BCD or rebooted.**
That is the one call in this review that should be the operator's, not mine.
