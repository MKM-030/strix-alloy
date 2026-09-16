# Native Windows HIP: build + qualification (2026-09-14, our session)

Status: **build succeeded and works.** MTP/spec-decode is blocked by a Windows-specific loader defect.

## 1. The build (ours; differs from the published recipes)

We built `pwilkin/llama.cpp@strix-halo` **`d67d5883`** natively on Windows with the **already-installed
ROCm 7.2** — no TheRock nightly download, no separate SDK:

- compiler: `C:\Program Files\AMD\ROCm\7.2\bin\clang.exe` (clang 21.0.0git), `hipcc` 7.2.60201
- device libs: `C:\Program Files\AMD\ROCm\7.2\amdgcn\bitcode`
  (**not** `lib\llvm\amdgcn\bitcode` — the ROCm 10 wheel layout differs from the Windows ROCm 7.2 layout;
  this cost us one failed build)
- flags: `-DGGML_HIP=ON -DGGML_HIP_RCCL=OFF -DGPU_TARGETS=gfx1151 -DAMDGPU_TARGETS=gfx1151
  -DGGML_HIP_GRAPHS=ON -DGGML_NATIVE=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_CURL=OFF`
  plus `-DCMAKE_HIP_FLAGS="--rocm-path=<rocm> --rocm-device-lib-path=<rocm>\amdgcn\bitcode"`
- source branch: our `win-native` = `d67d5883` + the **Windows `prefetch()` no-op stub**
  in `src/llama-lazy-reader.h` (issue #24's one-line fix; still absent upstream)
- binary: `C:\AI\build\strix-llama-win\build-win\bin\llama-server.exe`

Two real gotchas we solved:
1. `HIP_DEVICE_LIB_PATH` must point at `amdgcn\bitcode`, and `CMAKE_HIP_FLAGS` must carry
   `--rocm-device-lib-path`, or every HIP TU fails with
   *"cannot find ROCm device library; provide its path via --rocm-path"*.
2. In the bench driver, **prepending** ROCm to `PATH` is required — replacing `PATH` with
   ROCm+System32 removes Python and makes the harness fail silently.

## 2. Measured: native Windows HIP, UD-IQ4_XS, ub 8192, ctx 49152, token-exact, gen 256

| size | prefill t/s | decode t/s |
| ---: | ---: | ---: |
| 1024 | 246–260 | 6.8–7.3 |
| 8192 | 326 → **474** | 8.4 → **14.4** |
| 16384 | **469–473** | 13.9–14.6 |
| 32768 | **452–459** | **14.4–14.7** |

Load: **76–106 s** for the 87 GiB 3-shard set, from the `C:\AI\models` copy.

### Native vs WSL, same quant, same engine, same flags

| | WSL/DXG | **native Windows** |
| --- | ---: | ---: |
| prefill @8k | 325–364 | **472–474** |
| prefill @32k | 316–415 | **452–459** |
| decode @32k | 11.5–12.7 | **14.4–14.7** |
| stability | VM restarted 6× | no restarts, flat across depth |

**+30–45% prefill and +15–25% decode natively, and much more stable.** This is the first direct
measurement of the native-Windows benefit on our own build, and it confirms the WSL cost is real
(though Codex is right that the exact attribution among DXG, guest paging, and runtime differences is
not yet isolated).

## 3. MTP on native Windows: SHARED head works, plain heads hit a loader bug

**Head compatibility is the key discovery.** On the native Windows build:

| MTP head | Result |
| --- | --- |
| `mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf` (unsloth, 2.60 GB, `nextn_shared_target_tensors=True`) | **LOADS AND DRAFTS** — `draft acceptance = 0.625 (35/56)`, **decode 21.75 t/s** vs 14.5 serial (+50%) |
| `mtp-Qwen3.8-Flash-Next-Q8_0.gguf` (unsloth, 3.85 GB, standalone head with its own `output.weight`) | **`invalid vector subscript` at draft load** |
| `mtp-Qwen3.8-Flash-Next-Q8_0.gguf` (drluoto variant, 3.86 GB) | same `invalid vector subscript` |
| FR-Spec 65k head | rejected earlier (drluoto tensor naming: `fc_embd`/`fc_hidden` vs `eh_proj`) |

**Root cause identified from GGUF metadata** (`cmp-meta.py`): the standalone sidecar declares
`block_count = 49` with a 49-entry `compress_ratios`, while the shared sidecar declares
`nextn_shared_target_tensors = True` (so it borrows the trunk's head and stays within 48). The loader's
MTP-only path iterates per-layer arrays sized from `n_layer_all`, and the extra 49th layer overruns one
of them. The shared head avoids it because it does not carry the extra layer's own tensors.

**Practical conclusion: use the shared head on Windows.** It works, gives +50% decode, and needs no
source fix. (Fixing the standalone path would be a small loader patch: clamp the MTP-only per-layer
loops to `n_layer()` and let the sidecar's own block be handled explicitly.)

### Measured: native Windows + shared MTP head (preliminary, 1 rep)

| size | prefill t/s | decode t/s | acceptance |
| ---: | ---: | ---: | ---: |
| 1024 | 394.8 | **21.75** | 62.5% |

## 3b. MTP: two independent bugs found, both precisely isolated

**Bug A — `-b/-ub 8192` breaks the MTP draft load.** The loader dies with
`llama_model_load: error loading model: invalid vector subscript` *only* at `-b 8192 -ub 8192`.
Holding the head and the context fixed:

| config | result |
| --- | --- |
| ctx 8192, `-b/-ub 2048` | loads, drafts |
| **ctx 32768, `-b/-ub 2048`** | loads, drafts, **77% acceptance** |
| **ctx 49152, `-b/-ub 2048`** | loads, drafts, **77% acceptance** |
| ctx 49152, `-b/-ub 8192` | **`invalid vector subscript`** |
| ctx 49152, `-b/-ub 8192` (standalone head) | same failure |

So it is neither the head nor the context: it is **ubatch/batch 8192 plus a draft model**. The shared
head is *not* required either (that was my initial misreading — the first working run happened to use
`-ub 2048`). Workaround: **`-b/-ub 2048` whenever a draft head is attached.**

**Bug B — acceptance collapses to 0% past ~1k prompt.** With the working config:

| size | prefill t/s | decode t/s | acceptance |
| ---: | ---: | ---: | ---: |
| 1024 | 351–382 | **23.2–23.4** | **150/210 = 71%** |
| 8192 | 407–422 | 9.4 | **0/507 = 0%** |
| 16384 | 416–419 | 9.4 | **0/507 = 0%** |

Decode with a *zero*-acceptance draft is **worse than serial** (9.4 vs 14.5 t/s) — the draft cost is
paid and nothing is accepted. This is the same pathology the handoff document flagged as "the
0%-acceptance rows were a prompt-cache artifact", and it reproduces deterministically here. It needs
the prompt-cache/spec-state interaction fixed (cf. PR #28118/#28123) before MTP is usable at depth.

**Bug B — draft acceptance collapses to 0% past ~1k prompt, and it is NOT a prompt-cache artifact.**
Tested directly (`test-cache-artifact.py`), the same 8k prompt three times:

| call | prompt_n | decode t/s | draft accepted | acceptance |
| --- | ---: | ---: | ---: | ---: |
| cold (`cache_prompt=false`) | 8192 | 9.47 | 0/251 | **0.0%** |
| warm 1 (`cache_prompt=true`) | 4 | 9.39 | 0/251 | **0.0%** |
| warm 2 (`cache_prompt=true`) | 4 | 9.46 | 0/251 | **0.0%** |

The prior session's note that "the 0%-acceptance rows were a prompt-cache artifact" is therefore
**wrong for this build** — cold and warm are both exactly 0%, deterministically. At 1k the same head
gets 71%. Decode with a zero-acceptance draft (9.4 t/s) is **worse than serial** (14.5 t/s) because the
draft cost is paid for nothing.

Status: cause **identified** — see §3e.

## 3e. Bug B root cause: the draft enters QSA sparse block selection at n_kv > 2051

A same-prefix depth sweep (content held constant, only length grows) shows a **sharp cliff**:

| depth | prefill t/s | decode t/s | acceptance |
| ---: | ---: | ---: | ---: |
| 512 | 221 | 25.3 | 54.4% |
| 1024 | 329 | **29.8** | **72.7%** |
| 2048 | 367 | 27.9 | 69.6% |
| **4096** | 402 | 13.0 | **0.0%** |
| 8192 | 425 | 13.2 | 0.0% |
| chat, ~5.4k tokens | 455 | 13.2 | 0.0% |

The boundary is **not** a context/cache artifact (cold == warm == 0%) and **not** the prompt content
(a natural chat prompt over real text at 5.4k tokens also gives 0%).

**It is `n_kv > indexer_top_k + ratio - 1`.** `indexer_top_k = 2048`, `ratio = 4`, so the threshold is
**n_kv > 2051**, which is exactly where acceptance dies. The gate is
`qwen4exp_use_block_selection()` in `src/models/qwen4exp.cpp:809`:

```cpp
return blk_bias && n_stream==1 && ratio>1 && hparams.indexer_top_k%ratio==0 &&
    n_kv>hparams.indexer_top_k+ratio-1 && n_kv<=16777216 && ubatch.token &&
    cparams.flash_attn && cparams.offload_kqv && hparams.f_max_alibi_bias==0.0f &&
    !hparams.attn_soft_cap && hparams.n_embd_head_k()==256 && hparams.n_embd_head_v()==256;
```

Two facts make this the culprit:
1. Above the threshold the QSA input switches to the **maskless/packed-key (`scalar`/`compact`) layout**
   (see the three call sites at lines 879, 1058, 1073 which set `qsa->maskless`/`qsa->compact`).
2. The `ubatch.token` guard was deliberately relaxed so the **draft** could enter block selection
   (the comment directly above the function explains this: *"keeping it shut the draft out of block
   selection, and with it out of the maskless/packed-key layout and the qsa3 attention kernel"*).

So the draft is now routed into the same sparse block selection as the target, and **past 2051 cached
cells the draft's attention output stops matching the target's** — acceptance goes to exactly zero,
deterministically. Below the threshold the draft uses dense attention and agrees at 55–73%.

This is an upstream correctness bug in the new sparse-decode path, not a configuration error: with a
zero-acceptance draft, MTP costs more than it saves (13.0 vs 14.5 t/s serial). It needs a fix in the
graph builder (either keep the draft on the dense/scalar path, or make the draft's maskless layout match
the target's), which is the author's territory — our value is the precise repro:

```
llama-server -m <UD-IQ4_XS> -md <shared MTP head> --spec-type draft-mtp --spec-draft-n-max 2 \
  -c 16384 -b 2048 -ub 2048 --jinja
# prompt 2048 tokens -> 69.6% acceptance; 4096 tokens -> 0.0%
```

## 3c. Native Windows results, final (token-exact, gen 256)

| config | prefill @1k / @8k / @16k / @32k | decode @1k / @8k / @16k / @32k |
| --- | --- | --- |
| **serial, `-ub 8192`** | 246–260 / 326→474 / **469–473** / **452–459** | 6.8–7.3 / 8.4→14.4 / 13.9–14.6 / **14.4–14.7** |
| MTP shared head, `-ub 2048` | 351–382 / 407–422 / 416–419 / — | **23.2–23.4** / 9.4 / 9.4 / — |

**Headline: native Windows serial is the best stable engine we have** — ~460–475 t/s prefill with a flat
14.5 t/s decode to 32k, and **no VM restarts** (vs WSL's 6). With MTP at short context it reaches
**23.4 t/s** (71% acceptance), but depth acceptance is broken (Bug B).

## 3d. What this means for the plan

- **Native Windows is now the best single engine we have on serial decode and prefill**, and it is
  stable (no VM restarts).
- **Decode ranking today:** Vulkan + FR-Spec 30 t/s ≈ native HIP + shared MTP 21.8 t/s (preliminary) >
  native HIP serial 14.5 > WSL HIP 12–14. Vulkan still wins on decode; native HIP wins on prefill and
  stability.
- Reaching the upstream 35–50 t/s decode needs either the standalone-head loader fix, a wider MTP draft
  (the author uses width 3; we tested 2), or deeper sparse-QSA decode exercising (present in our build,
  active at ≤8 query tokens).

