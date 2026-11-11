# Halogen 0.20.1: bounded GPU input-preparation graph assessment

**Verdict: do not implement a graph replacement from the retained evidence.** The
selected count-one/default-wire-D unit is graph-shaped, but its current FC
kernels, scratch lifetimes, and complete real fixture are not closed. No hardware,
compiler, API, WSL, lifecycle or canonical-source operation was performed.

The exact ELF is SHA256
`7a72e138f0090008d171e41358a23f86a875fe92fadbcbc5daf2d3225e426577`.
Every saved instruction in `0x1f9d0a0..0x1f9da5e` was rechecked against its ELF
PT_LOAD bytes: **522 instructions / 2,494 bytes**, all matching. This routine
accepts `(model, host IDs, count)`. Its lazy `HALOGEN_MTP_WIRE` default is `D`.

## Selected complete semantic unit

Host ID validation and the existing four-byte asynchronous H2D copy stay outside
the potential graph. IDs at least 248320 become zero and increment `model+0xbe0`;
those diagnostics and mutation semantics must remain.

| Order | Operation | Site | Input / output or descriptor |
|---|---|---|---|
| 1 | Gather | `1f9d279` | `model+a10`, device IDs `model+dd0` -> `model+d58`; descriptor `20c33e0` |
| 2 | In-place embedding RMS2560 | `1f9d354` | `model+d58`, RMS weights `model+13a8` -> `model+d58`; descriptor `20c2648` |
| 3 | Embedding FC, M1 | `1f9d385` | descriptor `model+11c8`, `model+d58` -> `model+13c0`, N=K=2560; dispatcher `1f355b0` |
| 4 | Whole-hidden RMS10240 | `1f9d46f` | `model+d60`, RMS weights `model+13b0` -> global `20c9680`; descriptor `20c2648` |
| 5 | Hidden FC, M4 | `1f9d49e` | descriptor `model+1240`, global `20c9680` -> global `20c9698`, N=K=2560; dispatcher `1f355b0` |
| 6 | D seed add | setup `1f9d4c6..548`, launch `1f9d9ab` | `model+13c0`, global `20c9698` -> `model+d60`; descriptor `20c33f8` |

Entries identifying device buffers mean the pointers stored at those offsets;
FC descriptors are embedded at their listed model offsets. Direct launches use
default stream0, count-one grid `(1,1,1)`, block `(256,1,1)`. The seed destination
aliases the original hidden input after RMS has consumed it. Ordered edges are
therefore required. These are six semantic stages, **not a proved six-node
launch count**: both current FC routes still require closure.

For a fixed count and wire, the token and hidden data change, while scalar launch
shapes can remain constant. That makes replay plausible if device addresses and
functions are stable. The body has no `model+640` context reference. Caller
position changes, layer48, vocabulary/argmax, accept/reject, stop, state retention
and result completion are outside this bounded unit.

## Why this does not qualify an implementation

1. The current common FC dispatcher `1f355b0` has not been bound here to the exact
   M1/M4 kernels, current device code and argument metadata. Descriptor names and
   old-version shader knowledge do not close that binding.
2. Global scratch pointers `20c9680`/`20c9698` are read, but allocation, extent,
   growth/replacement, sharing and destruction remain unclosed. Retaining a graph
   across request or arena lifetime changes could retain invalid pointers.
3. The inspected authentic A/B fixture contains already normalized **0.16.2**
   FC inputs and individual FC outputs. It does not provide one coherent current
   gather + both RMS operations + FC pair + combined seed oracle. Inverting RMS
   or stitching captures is not an acceptable substitute.
4. The old isolated pair's 0.311702 ms GPU mean and 0.487170 ms enqueue/wait mean
   do not establish a current complete-unit cost budget or token-rate gain.

Absence of direct graph imports does not establish lack of HIP graph support.
The rejection concerns implementation readiness, not theoretical possibility.

Reconsider only with source-closed current FC selection and scratch ownership,
plus an already available authentic complete-unit fixture. The eventual route
would be explicit ordered graph nodes, host validation outside, resources bound
to the model/arena generation, and native fallback on unsupported shapes or
binding changes. Component parity and timing would precede any engine cohort.
This assessment does **not** justify a profiling-only campaign to fill the gaps.
No prefill, decode, acceptance or speedup value is claimed.

[Machine-readable contracts, byte audits and evidence hashes](halogen0201-gpu-input-graph-assessment-20261111.json).
Root independently rechecked all 522 instruction rows / 2,494 bytes and the 11
pinned evidence files. This remains a source assessment, not an implemented or
measured graph optimization.
