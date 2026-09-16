# Engine provenance and reproduction (2026-09-16)

External review's most consequential finding was that **the benchmarked engine is not reconstructible from
this repository**: `setup/build-windows.ps1` takes a separate `$Src` checkout, so no value published here let
a reader rebuild the binary behind the headline numbers.

This document closes that gap by publishing the engine delta as an ordered patch series, plus the hashes of
everything else needed.

## The engine delta is small

Our working branch is `win-native` on a clone of **`pwilkin/llama.cpp`** (`origin` =
`https://github.com/pwilkin/llama.cpp.git`), branched from the public `strix-halo` tip:

| | |
| --- | --- |
| upstream base commit | **`40a9f4d01b69314d0f75c9120abe8e199e49111d`** (`strix-halo`, "hip: extend MMB quants and fuse Flash-Next F32 PLE") |
| branch | `win-native` |
| total delta over that base | **8 commits, 581 insertions, 17 deletions across 10 files** |

The base commit is reachable from the public fork, so the whole engine is
`pwilkin/llama.cpp@40a9f4d0` + these 8 patches. Nothing else is needed.

## The patch series

`engine-patches/` in this repository, generated with `git format-patch 40a9f4d0..HEAD`:

| # | file | what it does |
| --- | --- | --- |
| 0001 | `win-restore-the-_WIN32-lazy-reader-prefetch-no-op-st.patch` | `_WIN32` no-op `prefetch()` stub so the lazy reader builds on Windows |
| 0002 | `win-native-d2t-draft-vocab-trim-on-device-speculativ.patch` | draft-vocab trim + on-device speculative checkpoints |
| 0003 | `tools-add-hidden-dump-harness-for-MTP-draft-head-tra.patch` | hidden-state dump harness (`tools/hidden-dump/`) for MTP draft-head training data |
| 0004 | `server-add-generation-gated-decode-phase-timing.patch` | decode phase timing (generation-gated) |
| 0005 | `server-add-round-width-yield-accounting-to-the-timin.patch` | round / width / yield accounting in the timing block |
| 0006 | `hip-add-RDNA3.5-512-expert-10-active-MoE-routing-pat.patch` | MMID_512 — **large-batch path only; see below** |
| 0007 | `spec-add-spec-draft-adaptive-acceptance-EMA-draft-si.patch` | `--spec-draft-adaptive` controller (off by default) |
| 0008 | `hip-record-that-MMID_512-is-a-large-batch-path-not-a.patch` | comment-only: records the measured coverage fact |

Applying: `git am engine-patches/*.patch` against `40a9f4d0`.

**None of these are required for the headline `llama-bench` numbers.** Patches 0006–0008 are the two measured
negatives and their documentation; 0004–0005 are instrumentation; 0003 is a training-data tool. The only
patch that touches a hot path for the published figures is 0002.

## Hashes

### Binaries (the build behind the published numbers)

| artifact | bytes | SHA-256 |
| --- | ---: | --- |
| `llama-server.exe` | 9,728 | `9653C982F7EF3E83C0498D764F33D01E793A581A0043111C36FA87C3ACB89ED6` |
| `ggml-hip.dll` | 86,771,200 | `ABD803DDC27931D6BD6F581A8D7D8DA862B40A38CA4BA02C6B717B23A71CCCF1` |
| `ggml.dll` | 90,624 | `BB7F9ABF6398B71FFA9719A58060DCB05B2C0C34185724CAB23764781F102712` |
| `llama-server-impl.dll` | 6,787,584 | `98791E0A3EE34798AA535BDAC1A3E6ED8767462C7331B8BD73F3D0C9FE2CBAE4` |
| `llama-common.dll` | 6,123,520 | `0A2BC79A958614C77B856DCF32A7AE5518CA5EF74DB411561BA2A1B233F4FE7D` |

### Model and draft head

| artifact | SHA-256 |
| --- | --- |
| `Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf` | `5B6032B1F3428A148A3B63D661A992DBE0E5F8E278AB684B3D2B474BC5372D30` |
| `...-00002-of-00009.gguf` | `81EA612C230E5C3EE1E1036873B316BD6F3D0BA00AA9E12DA9238B3EC75EF643` |
| `...-00003-of-00009.gguf` | `D4C2432777AD3F2073989D9B584AAA69EA53201C22BFA69B0EFC58FB3D4FFB9C` |
| `...-00004-of-00009.gguf` | `72E276E9FFD33891B0640136B7F8C3AC765D34B3FAE57D91CDBD4D25CE61477C` |
| `...-00005-of-00009.gguf` | `C61C34D8C6E27051FB903F7117C6577CBD87B945E7FCDD3B7642A794DEC78BAC` |
| `...-00006-of-00009.gguf` | `C9B36BCA38AD5994C24A9D840460C7C3763CD64DFE2816EFFE1EABEF5D7FC77A` |
| `...-00007-of-00009.gguf` | `B18C40E93081DF6B1001ED344AF7DE796F07A754F23001376CC9ED2D400EFFBA` |
| `...-00008-of-00009.gguf` | `3389E8907CE093D3AD45F5B46F14098D34352241CBC676361EDBED7186AB023E` |
| `...-00009-of-00009.gguf` | `8229BE447E559C6F1186D8C878621AFCF3466DE71ACA1B1C97E895288723B36E` |
| `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` | `5FF54097406A905CF3A724C709124CEB0E3E10235EE862298969E91C96FA96E6` |

**The draft head hash matches the one `myhacsint` documents** for the official shared sidecar
(`5ff54097406a905cf3a724c709124ceb0e3e10235ee862298969e91c96fa96e6`, 2,786,568,256 bytes), so we are
verifiably running the publisher's artifact rather than a local derivative.

### Toolchain

| item | value |
| --- | --- |
| compiler | `AMD clang version 24.0.0git (ROCm/llvm-project bc1e171b6a5333d498ad60fa4894549aa112db93)` |
| SDK runtime `amdhip64_7.dll` | 16,578,560 bytes, `71C41D9DB361E544D1CB6DFF91530D5705FFC5F1A91BA8EDCF583FB882E282BF` |
| SDK path used | `C:\AI\sdk\therock1151` (TheRock gfx1151) |
| build flags | `-DGGML_HIP=ON -DGPU_TARGETS=gfx1151 -DGGML_HIP_GRAPHS=ON -DGGML_NATIVE=ON`, Release, see `setup/build-windows.ps1` |
| carve | 96 GB (device pool 107.87 GB) |

## What this does NOT establish

- **No runtime network evidence.** These are configuration and artifact hashes; nothing here proves a specific
  binary made no unexpected network request.
- **The SDK is a nightly.** The compiler string identifies it, but a nightly tarball is not a pinned release;
  re-running the build from that URL later may not reproduce byte-identical binaries.
- **Windows/HIP runtime DLLs load from the exe directory** (see `setup/pin-hip-dlls.ps1`), which is why the
  `amdhip64_7.dll` hash above matters more than System32's copy.
- Binaries are not committed to this repository; only the patch series and hashes are. Building from patches is
  the supported path, and `llama-bench` numbers should be re-measured on the rebuild rather than assumed.
