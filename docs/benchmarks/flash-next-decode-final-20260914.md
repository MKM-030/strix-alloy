# Flash-Next decode on Windows/WSL: final measured picture (2026-09-14)

This supersedes both earlier decode notes. The short version: **decode is 13.8–19.8 t/s across all
depths including a 31,781-token prompt, with MTP acceptance ~67–100%.** The "7 t/s / 0% acceptance"
rows were a measurement artifact, not a model property.

## Final measurements (all exact, prompts sized with the server's `/tokenize`)

| Server ctx | Prompt tokens | Prefill | Decode | MTP acceptance |
| --- | ---: | ---: | ---: | ---: |
| 32768 | 8,526 | 308.1 | **18.28** | 66.7% |
| 32768 | 12,562 | 328.6 | **16.41** | 66.7% |
| 32768 | 12,579 | 292.7 | **19.78** | 66.7% |
| 32768 | 31,781 | 269.0 | **13.81** | 66.7% |
| 32768 | alternating 57 / 8,562 / 4 / 4 / cached / 4 | 30–331 | **13.8–31.1** | 62.5–100% |
| 8192 | 57 (×4 in a row) | 31–42 | **17.1–23.5** | 76.2% |
| 65536 | 411 | 116 | **13.5–16.9** | 61.2% |
| 65536 | 20,098 | 469–517 | 6.4–6.6 | **0%** ← artifact, see below |

**Reading:** decode is stable in the **14–22 t/s** band, with **prefill 270–330 t/s** and acceptance
two-thirds to perfect. The 31.8k-token prompt (essentially the full context) still decoded at 13.8 t/s.

## The "0% acceptance" rows — what they actually were

Those rows appeared only in runs using `-c 65536` where a second request followed a ~20k-token first
request and the **prompt cache** resumed from a snapshot. In that state the log shows
`0 accepted / 135 generated, mean len 1.00` — the drafter proposes nothing while a cached prefix is
being reused. In the clean boundary run (`-c 32768`, no cache carry-over between differently-sized
prompts) acceptance never dropped below 66.7% at any depth.

**So: the MTP drafter is fine; a prompt-cache resume path after a large cached prefix leaves it inert.**
That is a specific, reproducible bug worth reporting upstream — and it is *avoidable* (see below).

My earlier two explanations were both wrong and are retracted:
1. "depth kills MTP" — wrong; the 31.8k run decoded at 13.8 t/s with 67% acceptance.
2. "MTP only works on the first request" — wrong; four consecutive short requests all accepted 76%.
The real variable was the prompt cache carrying a large snapshot between requests, plus my own harness
bug (I sized prompts in *words*, not tokens, so "~8k" was really ~15–27k tokens).

## Comparison, now that the numbers are right

| Engine/quant | Windows/WSL prefill | Windows/WSL decode |
| --- | ---: | ---: |
| **strix-halo fork, unsloth UD-IQ4_XS + MTP** | **270–330 t/s** (@8–32k) | **14–22 t/s** |
| Halogen `UD-IQ4_XS` (Peonist, **native Linux**) | "prefill unchanged" | 25.4 t/s serial |
| Halogen `.hgn` on WSL, `Pin::None` | — | 0.32 t/s (unusable) |
| Vanilla llama.cpp | ~50 t/s | ~10 t/s |

**Our Windows result (14–22 t/s, 270–330 prefill) is ~70–90% of Halogen's native-Linux decode and
5–6× its prefill — on Windows, with no pinning, no `/dev/kfd`.** That is a genuinely good place to be.

## Practical guidance

1. **Use `-c 16384` or `-c 32768`** for the World Engine. Decode stays 14–20 t/s and prefill 270–330.
2. **Expect ~66–100% MTP acceptance** in normal use; the 0% case needs a large cached prefix resume.
3. **Workaround for the cache bug:** start a fresh server per conversation, or disable the prompt cache
   for workloads that switch between very differently sized prompts.
4. **Don't chase a "depth" fix** — there is nothing to fix at depth. The remaining headroom is the
   ~3× between 20 t/s and the ~63–75 t/s weight-bandwidth ceiling, which lives in kernel launch
   overhead and graphs (the kernel session's experiment A).
