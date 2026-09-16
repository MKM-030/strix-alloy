# shared-mtp-fit-report.md — handover v2, Priority 2 / B1

**Question (handover):** diagnose the "shared-MTP / large-ubatch load failure" and the portable HIP
improvements around it.

**Verdict, two separate findings:**

1. **The shared-MTP failure is a `--fit on` preflight defect, and it is now reproduced exactly.**
   With the shared MTP head attached, `--fit on` measures the sidecar as a standalone model, which
   throws `qwen4exp requires ctx_other to be set`, after which fit logs *"failed to measure the memory
   of the extra model, fitting without it"* and proceeds **with no allowance for the draft context at
   all.** This fires at every ubatch (2048/8192/16384), so it is not ubatch-specific — the large
   ubatch is just where the resulting under-reservation would overflow. The root cause is
   fork-specific and *different* from the upstream `path_model_shared` fix (see below).
2. **The older "Bug A" (`-b/-ub 8192` + draft → `invalid vector subscript`) does NOT reproduce** on
   the current binary. All four arms (ub 2048/8192, draft/no-draft, ctx 49152) loaded and reached
   `listening`; only the fit-on arm failed, and for reason (1). So "large ubatch breaks the draft
   load" is, on today's build, really finding (1) plus a stale prior report.

## Evidence — fit-on failure (reproduced)

`kernel-work/reproduce-b1-shared-mtp-fit.ps1` (model + shared head, `--fit on`, ctx 32768):

```
[fiton-ub2048]  fit=on ub=2048  b=2048  -> ready=True  fitWarn=True
[fiton-ub8192]  fit=on ub=8192  b=8192  -> ready=True  fitWarn=True
[fiton-ub16384] fit=on ub=16384 b=16384 -> ready=True  fitWarn=True
[fitoff-ub2048] fit=off ub=2048 b=2048  -> ready=True  fitWarn=False
```

The warning line in every fit-on arm:

```
E llama_init_from_model: failed to initialize the context: qwen4exp requires ctx_other to be set
                        (this warning is normal during memory fitting)
W operator(): failed to measure the memory of the extra model, fitting without it:
              failed to create llama_context from model
```

`kernel-work/reproduce-b1-bugA.ps1` confirmed the separation (ctx 49152):

| arm | ub | draft | fit | result |
| --- | ---: | --- | --- | --- |
| a-ctx49152-ub2048-draft | 2048 | yes | off | ready (draft loaded) |
| **a-ctx49152-ub8192-draft** | 8192 | yes | off | **ready (draft loaded)** — Bug A does NOT reproduce |
| a-ctx49152-ub8192-nodraft | 8192 | no | off | ready |
| fit-ctx32768-ub2048-draft | 2048 | yes | **on** | **fails: `requires ctx_other`** |

## Root cause (source, ours)

`common/fit.cpp:~52-64` — the memory probe loads each model with `no_alloc` + `LLAMA_LOAD_MODE_NONE`
and then creates a context:

```cpp
llama_model * model = llama_model_load_from_file(path_model, mparams_copy);
...
llama_context * ctx = llama_init_from_model(model, *cparams);   // <-- throws for our shared head
```

`src/llama-context.cpp:155-161` requires `ctx_other` whenever a qwen4exp model is missing
`tok_embd`/`output` — which is exactly the shared head (our `gguf-census.py` shows it has neither
`token_embd.weight` nor `output_norm.weight`):

```cpp
if (model.arch == LLM_ARCH_EAGLE3 || model.arch == LLM_ARCH_DFLASH || model.arch == LLM_ARCH_QWEN4EXP) {
    if (model.tok_embd == nullptr || model.output == nullptr) {
        if (params.ctx_other == nullptr) {
            throw std::runtime_error(model.arch_name() + " requires ctx_other to be set ...");
        }
        cparams.ctx_other = params.ctx_other;
    }
}
```

Our fork borrows the shared tensors through **`ctx_other`** — `src/models/qwen4exp.cpp:605-607`:

```cpp
ggml_tensor * tok_embd_w = layer.nextn.embed_tokens ? layer.nextn.embed_tokens : model.tok_embd;
if (tok_embd_w == nullptr) {
    tok_embd_w = qwen4exp_shared_model(cparams, model, "token_embd.weight").tok_embd;
}
```

So the draft context can only be created with the **target context** present. During fit the target
has not been loaded yet (`common/common.cpp:1304` runs fit *before* the target load at line 1329), so
the probe has no context to hand over and the draft measurement always fails. `common/fit.cpp:225`
then degrades — *"the extra model is optional, fit the main model alone rather than giving up"* — and
`dmds_extra` stays zero, so the draft's weights, context and `n_ubatch`-scaled compute buffer are
never counted. Since fit's compute term scales with `n_ubatch`, a large `-ub` is where the missing
allowance overflows device memory.

## Relationship to the upstream fix (`10bb3cff8`)

Upstream's fix adds `path_model_shared` / `mparams_shared` to `common_fit_extra_model` and points the
sidecar's `mparams.model_shared` at a `no_alloc` metadata load of the target, so the loader's
`borrow_shared_tensor` resolves the omitted names. **Our fork does not use `model_shared` at all**
(no such symbol exists in `src/llama-model-loader.cpp`); it borrows via `ctx_other` during graph
build. So upstream's patch is the right *idea* but not directly applicable — porting it verbatim
would not compile. The equivalent fix for us is to give the draft probe a target context: measure the
target first (it is already being measured in the same function), then create the draft context with
`cparams.ctx_other` set to it. Bounded, but not a one-liner; and it only matters if we want `--fit on`.

## Practical status / recommendation

- **Production is already safe**: we launch with `--fit off --load-mode none` and size `-c/-b/-ub` by
  hand, which skips the broken probe entirely. This is why our runs work.
- **Do not switch to `--fit on`** with the shared MTP head until the probe is taught to pass
  `ctx_other`; otherwise the draft is silently unaccounted and load may OOM at larger `-ub`/ctx.
- **Bug A is stale** on the current binary; the earlier report's `-b/-ub 2048` restriction is no
  longer required for *load* reasons. (Whether ub 8192 is still worse for decode/prefill is a
  separate, legitimate question — see B3.)
- Portable HIP improvements are catalogued in `source-manifest.md` (B2). The highest-value item is
  **PR26 (recurrent rollback slots for MTP)**, which our fork **already contains** and which must be
  preserved across any future upstream merge.

## Artifacts

- `kernel-work/reproduce-b1-shared-mtp-fit.ps1`, `reproduce-b1-bugA.ps1`
- `kernel-work/gguf-census.py` (proves the head omits `token_embd`/`output_norm`)
- `kernel-work/results/b1-repro.json`, `b1-bugA-repro.json`, `b1-*.err`, `b1a-*.err`
