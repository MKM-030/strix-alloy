# Draft-head training harness: Phase 1 built and verified (2026-09-15)

Companion to `draft-head-training-plan-20260915.md`. That doc set the plan; this one records the first
concrete artifact — the data harness that produces teacher-forced training pairs from our own trunk.

## The head's input contract (read from the fork, not assumed)

`src/models/qwen4exp.cpp::build_nextn` defines exactly what the MTP head consumes. Per position `k`:

```
h_norm[k] = rms_norm(h[k-1]) * nextn.hnorm    # trunk hidden after position k-1, 4 hyper-conn streams
e_norm[k] = rms_norm(embed(t_k)) * nextn.enorm
concat[k] = [e_norm[k] ; h_norm[k]]           # [2*n_embd, hc, tokens]
res       = eh_proj @ concat                   # the head's own block
... one attention layer + MoE FFN ...
logits[k] = output.weight @ (hc_head_mix(res[k]))
```

So the training example at index `k` is:

- **input**  `(h[k-1], tokens[k])` — the trunk hidden *one position back*, plus the embedding of the token
  being fed at `k`
- **target** `tokens[k+1]`

This is the EAGLE/MTP shift-by-one and it is why the speculative driver does
`memcpy(batch.embd + 1*n_embd, h_tgt, row_bytes * (n_tokens-1))` — it shifts the target hidden right by one.

## The harness: `llama-hidden-dump`

New repo tool (`tools/hidden-dump/hidden-dump.cpp`, ~330 lines). It is **read-only**: no graph changes,
no weights written, no product contact. It reuses the fork's existing staging API
(`llama_set_embeddings_nextn` / `llama_get_embeddings_nextn_ith`) — the same tensors the spec driver
already reads, so it cannot diverge from what the head actually sees at inference.

Why a dedicated tool and not a server patch: the fork already exposes the hidden states. Adding a
`--dump-hidden` flag to the server would have been more invasive for the same result.

**Outputs** (prefix from `--out`):

| file | type | meaning |
| --- | --- | --- |
| `<prefix>.tokens` | int32 `[n_tokens]` | token ids in order |
| `<prefix>.h` | fp16 (or fp32 with `--fp32`) `[n_tokens, n_embd_out]` | trunk hidden after each position |
| `<prefix>.json` | manifest | n_tokens, n_embd_out, dtype, window, corpus, contract |

**Corpus handling:** consumed in non-overlapping windows; the KV cache is cleared between windows
(`llama_memory_clear(data=true)`) so every window has full left context equal to its own length — matching
a fresh sequence at inference, which is what the head sees when drafting.

**Usage:**
```bash
llama-hidden-dump -m MODEL.gguf -f corpus.txt --out PREFIX \
    --ntokens 65536 --window 2048 [-c 2048] [-b 2048] [-ngl 99] [--fp32]
```

## Verification (this is the part that matters)

A harness that silently produces wrong pairs is worse than none, so the smoke test checks sizes *and*
content, not just "it ran".

Built and run on the Ornith MTP model (small, has a nextn block, fast to load):

```
hidden-dump: 512 tokens, n_embd_out=2048, window=256, fp16
hidden-dump: wrote results/hd-smoke.{tokens,h,json}  (2 MiB hidden)
```

| check | result |
| --- | --- |
| `.h` size vs `n*d*2` | 2 097 152 == 2 097 152 ✅ |
| finite / NaN | all finite, no NaN ✅ |
| degenerate (all-zero) | 0 / 1 048 576 zeros ✅ |
| rows differ across positions | L2(row0,row1) = 142.3, L2(row0,row-1) = 157.8 ✅ |
| token stream | 256 unique tokens from the corpus ✅ |
| manifest | present with the contract string ✅ |

The build path is proven on both backends: WSL/ROCm (`build-hip`) and native Windows TheRock clang 24
(`build-therock`), via `build-win-hidden-dump.ps1`.

**Windows-specific bug found and fixed during bring-up.** The first Windows build exited with
`0xC00000FD` (stack overflow) in ~2 s, before reading any argument. Cause: `main` held the corpus read
buffer as a **1 MiB stack array** (`char buf[1 << 20]`); Windows' default stack *reserve* is 1 MiB, so the
frame overflowed on entry. It passed on WSL only because WSL's default stack is 8 MiB — a classic
"works on the other platform" trap. Fixed by moving the buffer to the heap (`std::vector<char>`).
Lesson for the training tools to come: **never put a large local array in a Windows `main`**.

## What is left before training

1. ~~Run the dumper on the PROJFIX trunk~~ — **done, see below.**
2. **Reproduce the existing head's acceptance through the harness** before training anything. Feed the
   dumped pairs through the current head and check it reproduces the ~75% acceptance we measure at
   inference. If it does not, the harness contract is wrong and training would bake in the error. This is
   the cheapest correctness gate and it should be done first.
3. Then Phase 2 (train) per the plan doc.

## PROJFIX dump: done and verified

The real target trunk, native Windows, clang 24:

```
hidden-dump: 8192 tokens, n_embd_out=10240, window=2048, fp16
hidden-dump: wrote results/projfix-hd.{tokens,h,json}  (160 MiB hidden)
```

`n_embd_out = 10240` = 4 hyper-connection streams × 2560 — the head's declared input width, as expected.

| check | result |
| --- | --- |
| `.h` size vs `n*d*2` | 167 772 160 == 167 772 160 ✅ |
| finite / NaN | all finite, no NaN ✅ |
| degenerate | 10 / 83 886 080 zeros (0.00001%) ✅ |
| stream spread | per-stream std 0.20–0.92 — **four distinct streams, not collapsed** ✅ |
| rows differ | L2(0,1)=49.4, L2(0,2047)=75.1, L2(0,8191)=68.3 ✅ |
| token stream | 2059 unique, ids in [1, 241853] ✅ |

This is the first training-ready artifact: 8192 teacher-forced `(h, token)` pairs from **our** trunk and
quant, not someone else's.

## Windows bring-up bugs found (both fixed)

1. **Stack overflow at `main` entry** (`0xC00000FD`). A 1 MiB stack array overflowed Windows' 1 MiB
   default stack *reserve*; it passed on WSL only because WSL's stack is 8 MiB. Moved to the heap.
2. **Output-buffer overrun** (`GGML_ASSERT(offset + size <= ggml_nbytes)`). `common_params` defaults
   `n_outputs_max_per_seq = 1`, so the embedding output buffer was sized for one row while the unmasked
   nextn copyback reads all `n_tokens`. Fixed by sizing `n_outputs_max`/`n_outputs_max_per_seq` to the
   window and marking every token as an output.
3. **Double-free in teardown** (`0xC0000005`) — I freed ctx/model that `common_init_result_ptr` also
   owns. The dump file was already closed and complete, which is why the 8192-token run verified clean
   despite the non-zero exit. Removed the manual frees; the next run (`projfix-hd2`, 2048 tokens) **exits
   0 cleanly**.
4. **Unescaped Windows path in the manifest** — backslashes broke JSON parsing. Now escaped; the manifest
   parses (`json.load` → `n_tokens=2048, n_embd_out=10240, fp16, window=2048`).

**Lesson for the training tools to come:** on Windows, never put a large local array in `main`, and always
check the exit code against the artifacts — a teardown crash after a successful write is still a crash.

## Honest status

- The harness is **verified on both a proxy model and the real PROJFIX trunk**, on both backends.
- The acceptance-reproduction gate (step 2 above) is **not done** — it is the next action and the one that
  would invalidate everything downstream if skipped.
- No training has happened. The lever-B (architecture shrink) loader work is untouched.
