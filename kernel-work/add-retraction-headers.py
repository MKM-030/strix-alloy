import io
import os

BASE = r"C:\Projects\strix-alloy-clean\docs\benchmarks"


def prepend(fn, block):
    p = os.path.join(BASE, fn)
    s = io.open(p, encoding="utf-8").read()
    if "SUPERSEDED" in s.split("\n\n")[1] if len(s.split("\n\n")) > 1 else False:
        print(f"  {fn}: already has a header, skipping")
        return
    io.open(p, "w", encoding="utf-8", newline="").write(block + s)
    print(f"  {fn}: header prepended")


# ---- 1. acceptance-width-report.md  (review §10) -------------------------------
prepend("acceptance-width-report.md", """# acceptance-width-report.md — handover v2, Priority 1 / A0

> ## CORRECTION (2026-09-17): "benign" was too strong, and two correctness gates are still open
>
> External review objected that this document **dismisses token divergence as harmless on insufficient
> grounds**, and it is right. The measurements below stand and are good work; three claims built on them do
> not, and are corrected here.
>
> **What is established:** serial and wide-verify differ in the dense regime; the difference is
> *deterministic* (repeatable, graphs-off identical), *bounded* (sub-0.2-nat top-1/top-2 margins), and the
> speculative arm emits serial's **#2** token at every observed site. That is real and useful.
>
> **What is NOT established:**
> - **That the divergence is harmless.** "The verifier sampled its own logits correctly" is not a
>   correctness argument — a verifier can sample its logits correctly while those logits came from a wrong
>   mask, wrong state, or a wrong batched computation. Near-tie magnitude and emitted-token rank bound the
>   *size* of the difference; they do not show its *cause* is benign.
> - **That the cause is reduction order.** The mechanism section says so itself ("a plausible reading, not
>   a kernel-audited proof"). It remains a hypothesis. Note the reviewer's point that a global max-logit-
>   difference threshold cannot substitute: the first meaningful divergence must be localised and compared
>   against a reference computation.
> - **Anything about sequence-level quality.** No multi-turn, depth-band, retrieval or tool-output testing
>   was done here. olliehm documents exactly the failure modes single-turn speed tests miss (multi-turn
>   slash flooding, depth-dependent incoherence) despite improved throughput.
>
> **The four correctness gates, as separate questions** (only the first two are answered anywhere in this
> repository):
>
> | # | Gate | Status |
> | --- | --- | --- |
> | 1 | Same-build repeatability | **DONE** — `same` arm IDENTICAL; harness deterministic |
> | 2 | Width-1 vs width-2/3 numerical consistency | **DONE (this doc)** — diverges in dense, matches in sparse |
> | 3 | Correct state after accepting 0, 1 or N draft tokens | **NOT DONE** |
> | 4 | Sequence-level quality: multi-turn, context boundaries, retrieval, tool output | **NOT DONE** |
>
> **Also owed:** `stew675`'s patch set carries width-invariance and masked/freed-cell fixes *and* documents
> patches that intentionally alter reduction order. Those distinctions are the reference to import — not an
> unqualified "same output" promise. The audit is still listed as future work.
>
> Downstream consequence: the "no fixable verify bug exists" conclusion below is **withdrawn**. What holds is
> narrower — the observed divergence is deterministic and sub-0.2-nat, so chasing those particular near-ties
> is unlikely to pay; it does not follow that the verify path is proven correct. Gates 3 and 4 are the
> remaining work.

""")

# ---- 2. final-results.md ------------------------------------------------------
prepend("final-results.md", """# final-results.md — handover v2 progress (2026-09-15)

> ## STATUS (2026-09-17): correctness claims in this document are SUPERSEDED
>
> This is a dated session record, kept for its measurements. Its **correctness verdicts are not endorsed**:
> read `acceptance-width-report.md` (which now carries the current correction) and
> `CLAIM-LEDGER.md` instead.
>
> Specifically superseded here:
> - "the cause is the dense decode regime" — that is a **hypothesis**, not an established cause; no
>   sequence-level or state-correctness gate was run. The near-tie magnitude does not establish that the
>   divergence is benign.
> - Any "uniform efficiency loss" or ALU-bound framing — see the RETRACTED header in
>   `decode-alu-bound-dp4a-20260916.md` (the measured bottleneck was the benchmark's own contended
>   `atomicAdd` epilogue) and the per-operator fixed-cost result in
>   `real-kernel-measured-20260916.md`.
> - Headline throughput figures in this file predate the 96 GB carve restoration and the canonical
>   `llama-bench` protocol. Quote the README's `llama-bench` numbers, not these.

""")

# ---- 3. decode-byte-accounting-20260915.md -----------------------------------
prepend("decode-byte-accounting-20260915.md", """# Where a decode step's bytes actually go — and why the loss is uniform (2026-09-15)

> ## STATUS (2026-09-17): the census is useful; the "uniform loss" conclusion is WITHDRAWN
>
> The per-tensor census below is a legitimate **nominal active weight payload** model and is still used.
> Two things built on it are not endorsed:
>
> 1. **"The loss is uniform / a uniform quantized-matvec efficiency loss"** — superseded. The follow-up
>    measurement (`real-kernel-measured-20260916.md`) found the cost is **per-operator, not per-block**:
>    a fitted ≈5.4 µs fixed + bytes/133 GB/s across the tested operator family. "Uniform loss" is the wrong
>    shape and the wrong explanation.
> 2. **The ALU-bound reading it led to** — **RETRACTED** in `decode-alu-bound-dp4a-20260916.md`: the
>    apparent bandwidth shortfall was the benchmark's own contended `atomicAdd` epilogue. With a fair
>    epilogue the same kernel reached ~100% of bandwidth.
>
> **Provenance caveats a reader must carry** (raised by external review): the dtype mix here (a **Q6_K**
> head, **F32** routers) is *not* the mix the README's summary prose describes, and `pf-census.json` totals
> ≈**4.254 GB**, not the 4.219 GB quoted elsewhere. This is version drift, not necessarily a faulty census,
> but it means the number's physical interpretation is not settled. It is a tensor-metadata estimate, not a
> bus measurement: activation quantisation, state traffic, attention reads, repeated weight reads and cache
> reuse are accounted separately, if at all. Regenerate it from the exact benchmarked GGUF hashes before
> citing it as traffic.

""")
print("done")
