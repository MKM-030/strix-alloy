# Version audit: repos, SDK, driver, toolchain (2026-09-15)

## 1. Correcting my own claim about TheRock on Windows

**I previously told you TheRock is Linux-only, that our Windows SDK was therefore behind, and that we
would need to build it ourselves for Windows. That was wrong on both counts, and here is the evidence.**

1. **Windows gfx1151 tarballs are published daily.** From `nightly.repo.amd.com/rocm/core/tarball/`:

```
therock-dist-windows-gfx1151-10.1.0a20260910.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260911.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260912.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260913.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260914.tar.gz
therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz   <-- ours; HTTP 200
```

2. **We are already on the newest one.** Nothing newer than `20260915` exists on that host today.
   Local file: `therock-dist-windows-gfx1151-10.2.0a20260915.tar.gz`, 1,713,662,621 bytes, 09-15 09:18.

**We have never built TheRock ourselves and never needed to.**

### Why I got it wrong — two traps worth recording

- **Two different listing hosts, and they disagree.** `rocm.nightlies.amd.com/tarball/` (which I checked
  first) tops out at **`7.14.0a20260612`** for Windows gfx1151 and 404s on our filename. It is a
  different/stale bucket. `nightly.repo.amd.com/rocm/core/tarball/` is the live one. I drew a conclusion
  from the wrong host.
- **String sort lies for these filenames.** `10.2.0a…` sorts *before* `7.9.0rc…`, so my first `tail -10`
  displayed June's 7.x builds as if they were newest. `sort -V` is required.

## 2. Toolchain (verified)

| item | value |
| --- | --- |
| TheRock SDK | `10.2.0a20260915` — **newest published** |
| HIP | 7.16, git `1091c91191` |
| Compiler | **AMD clang 24.0.0git**, target **`x86_64-pc-windows-msvc`** |
| Build flags | `GGML_HIP=ON`, `GPU_TARGETS=gfx1151`, `GGML_HIP_GRAPHS=ON` |

The target string `x86_64-pc-windows-msvc` is direct evidence this is a native Windows toolchain.

**No profiler ships in it** (no `rocprof`/`rocprofv2`/`rocprofv3`/`rocprofiler-sdk`). That is a real limit
for the composition work, but it is not a version problem — upgrading would not change it, so it is not a
reason to rebuild anything.

**What a future SDK could give us:** the only measured SDK-side lever we have ever found was the compiler
(clang 21 → 24 = **+60–71% prefill**). If a future build bumps LLVM, re-measure. The MMB/QSA/PLE/HC kernels
live in the *llama.cpp fork*, not the SDK, so they advance with the fork.

## 3. Driver (the other half of "are we current")

| item | value |
| --- | --- |
| GPU | AMD Radeon(TM) 8060S, `PCI\VEN_1002&DEV_1586`, `CM_PROB_NONE`, ConfigManagerErrorCode 0 |
| Driver | `32.0.31041.1004` (2026-08-17) — **the driver every measurement in this project was taken on** |
| NPU | `NPU Compute Accelerator Device`, `CM_PROB_NONE` |

**Recommendation: do not upgrade the GPU driver casually.** It is our baseline. We have no evidence the
numbers are driver-invariant, so an upgrade invalidates every benchmark and requires a full re-baseline.
The driver was *considered* as a GPU-recovery step earlier and proved unnecessary once the real cause (the
`System32\amdhip64_7.dll` shadowing) was found.

## 4. Repository pins

| component | our pin | upstream tip | status |
| --- | --- | --- | --- |
| **pwilkin/llama.cpp `strix-halo`** | `40a9f4d0` | **`40a9f4d0`** | **SAME — 0 commits after ours** |
| our branch | `win-native` (3 commits on top) | — | clean tree |
| halo-box/strix-llama.cpp | not pinned | `cfe6bb14e` (09-15) `HIP: keep FA head size 192 off the WMMA kernel (#55)` | newer upstream |
| drluoto `strix-halo-vulkan` | — | `ba5354d46` (09-06) | stale |
| drluoto `strix-halo-flash-next` | — | `590ac45bc` (08-31) | staler |
| peonist-ai/halogen-flash-server | — | **0.11.0** (09-15) | moved; closed source |
| HF ilintar PROJFIX | ours | rev `ba5b0d69` (09-12) | SAME |
| HF drluoto MTP-GGUF | ours | rev `922dc15f` (09-06) | SAME — note: **no `-shared-` variant there** |
| HF unsloth | ours | rev `38bb39ee` (09-02) | SAME — has `MTP/mtp-…-shared-Q8_0.gguf` as an alternative source |
| Heretek-AI/chlorine-server | — | `385d1f966` (09-10) | stale |
| Aristo94/EngramHalo.cpp | — | `15176583b` (committer 09-12) | — |
| ciru-ai/ornith-ciru-halo-agent | — | runtime **1.0.2** (09-15) | moved |
| MakazhanAlpamys/Soup | — | `da17fd4e3` (09-15) | active |
| ggml-org/llama.cpp master | — | `38a5b42d9` (09-15), tag `v0.4.1` | — |

**The headline: our fork base is the current tip. There is nothing to rebase onto.** That is a clean answer
— the rebase work done earlier today put us exactly at upstream head, and upstream has not moved since.

Worth a look (not urgent): **halo-box `cfe6bb14e`** — "keep FA head size 192 off the WMMA kernel". Our model
uses `n_embd_head_k = n_embd_head_v = 256`, so 192 does not apply directly, but the commit implies their
WMMA FA path has a head-size restriction we may share. Low priority given our round-cost-flat result.

**Halogen is at 0.11.0** and remains closed-source; it is a comparison target only (and its README says
native Linux only).

## 5. Bottom line

- **SDK: current.** No action.
- **Toolchain: current** (clang 24, native Windows target).
- **Fork: current.** Base == upstream tip.
- **Model / MTP head: current.** No upstream changes.
- **Driver: deliberately pinned** to our baseline version; do not upgrade without re-baselining.
- **No profiler available** in the Windows SDK — a genuine capability gap, not a version gap.
