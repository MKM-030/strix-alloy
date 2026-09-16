# Halogen in production on Windows — working configuration and the Flash-Next fix (2026-09-13)

Founder requirement: **use Halogen no matter what**, find a production way on Windows, and shrink the
model if needed. Status: **Halogen 27B is live as an OpenAI-compatible service on Windows.** Flash-Next
needs one carve notch more, with the arithmetic below.

Working directory for all of this: `C:\Projects\REV-N\.revn-data\orchestrator\` (scripts) and the WSL
home (`/home/revn`).

---

## 1. What is running now (verified)

```
engine : /home/revn/halogen-re/halogen --checkpoint qwen3.8-27b-p1w4d-d2.hgn --serve --port 8730
api    : /home/revn/halogen-re/root/halogen/tools/serve_api.py --engine 127.0.0.1:8730 --port 8731
```

Measured startup at the **8 GB carve**:

```
checkpoint: registered 35.9 GB in 61.2 s (0.6 GB/s, Mapped|ReadOnly)
serve: prompt cache 65.3 GB AUTO (73.9 GB free after the mapped checkpoint), 4 x 262144-token entries
serve: drafters — mtp available, dflash2 available, default serial
serve: listening on 127.0.0.1:8730 — 64 layers, ctx 262144, greedy batch-1
{"object":"list","data":[{"id":"halogen-qwen3.8-27b",...}]}
```

End-to-end OpenAI call (5.4 s round trip, correct answer):

```
POST /v1/chat/completions {"model":"halogen-qwen3.8-27b", "messages":[{"role":"user","content":"What is the capital of France?"}]}
→ "The capital of France is **Paris**."
```

Decode modes (measured, 32 tokens, greedy):

| Mode | Prefill (5 tok) | Decode |
|---|---:|---:|
| serial | 388 ms | 9.4 t/s |
| MTP | 731 ms | 10.3 t/s |
| **DFlash2** | **179 ms** | **17.1 t/s** |

**Launcher:** `halo-27b-serve.sh start` / `stop`. The engine and front-end are detached (`setsid nohup`),
so they survive the launcher exiting. The shim `hipshim.so` is **required** (it supplies the
`hipHostRegister` fallback that WSL/DXG lacks).

---

## 2. THE key discovery: the carve direction is inverted

You were right that WSL can use far more memory than the carve. Concretely, on this box:

| Budget | What it is | At 8 GB carve |
| --- | --- | ---: |
| Windows-visible RAM | 128 − carve | **119.6 GB** |
| WSL VM RAM (`.wslconfig memory=`) | what Linux processes see | **104 GB** |
| GPU device pool | `64 + carve/2` (Vulkan/HIP) | **67.7 GiB** |

Halogen *pins* the checkpoint (locked, non-swappable, GPU-addressable). At 8 GB carve the engine
pinned **65.60 GiB of trunk successfully** — because the pin comes from WSL host RAM, which is huge.
At 64 GB carve the same pin was **refused** ("MemAvailable 45.92 GiB"), because Windows RAM had shrunk.

So: **smaller carve → more host RAM → pinning works.** This is the opposite of the GGUF/Vulkan path,
which needs the big carve. That is why 8 GB is the right set for Halogen and was wrong for the GGUF.

---

## 3. The Flash-Next fix

At 8 GB the trunk pins (65.60 GiB) but the **quality overlay (2.4 GiB) is refused**: the pool is
67.7 GiB and 65.6 + 2.4 = 68.0 — **0.3 GiB short**.

| Carve | Device pool | Trunk+overlay (68.0) | Host RAM for pinning |
| ---: | ---: | --- | ---: |
| 8 GB | 68 GB | **0.3 GB short** | 120 GB ✅ |
| **16 GB** | **72 GB** | ✅ **4 GB headroom** | 112 GB ✅ |
| 24 GB | 76 GB | ✅ 8 GB headroom | 104 GB ✅ |
| 32 GB | 80 GB | ✅ 12 GB headroom | 96 GB ✅ |

**Recommended: 16 GB** — the smallest carve that clears the trunk + overlay, while leaving host RAM
(~112 GB) far above the ~82 GiB the pin guard requires. 24 GB is the safer choice if Flash-Next's
working-memory/scratch also needs pool space.

> One caveat measured today: after a *successful* Flash-Next pin, a second engine's registration can be
> refused until the WSL VM is fully restarted (`wsl --shutdown`). Start **one engine at a time**, and
> restart WSL before switching models.

### Why Flash-Next refuses at 8 GB — the registration budget

Repeated attempts show a second, subtler limit than the pool size: the **DXG `hipHostRegister`
registration budget behaves like a Windows-driver-lifetime resource**. Observed sequence at 8 GB:

| When | Engine | Result |
| --- | --- | --- |
| First run after the 8 GB reboot | Flash-Next (65.6 GiB) | **pinned 65.60 GiB** ✅ (barely, pool 67.7) |
| Later runs (same boot) | Flash-Next | `refused to register 66.11 GiB … after 1.75 GiB` ✗ |
| Later runs (same boot) | Halogen 27B (35.9 GiB) | **registers reliably** ✅ |

So at 8 GB, Flash-Next is *exactly at* the pool edge and only the first post-reboot registration
succeeds. Two independent fixes:
1. **Give Flash-Next headroom:** set the carve to **16–24 GB** (pool 72–76 GB), which clears trunk+overlay
   (68.0 GiB) by 4–8 GB and removes the edge condition.
2. **Guarantee a clean registration:** reboot Windows before starting Flash-Next, and run it **first**
   (before any other Halogen engine).

A deterministic shim (`hipshim3.c`) was built to force every large buffer down the mapped-pin path, but
the engine's *file-registration* loop hits the driver cap regardless — so the shim cannot manufacture
budget the driver will not grant. The pool/carve fix is the real one.

---

## 4. Shrinking the model / "deactivating what we don't need"

You asked about the pruning ideas from the Reddit threads (drop scientific/research capability, shrink
to fit). Here is what is actually possible, in order of how much size it recovers:

### 4a. What the engine already excludes (free, no work)
- **The 47.7 GiB n-gram table is NOT resident** — it is paged from disk through the file cache. The
  engine's own line says so. So the "115 GiB" checkpoint only needs ~68 GiB resident already.
- **`HALOGEN_CK_OVERLAY_SKIP=<regex>`** — the engine can skip overlay tensors matching a pattern
  ("overlay: SKIPPING N tensors matching /…/, the base's copies run"). Skips are **quality-reducing**
  (the overlay exists to buy back 5–9% perplexity), but a partial skip can shave a few hundred MB.

### 4b. Expert pruning (the real lever, needs a rebuilt checkpoint)
Flash-Next is a **512-expert MoE**; the routing gate (`mlp.gate.weight [512, 2560]`) is BF16 and tiny,
but the experts (`mlp.experts.*` at ~1.4 GB/layer) dominate the 65.6 GiB trunk. Most experts never fire
for our domain (NPC dialogue, German, world-state) — that is exactly the `Jab1718/Moe-slices` finding
(keep the experts that fire, align counts to multiples of 16 for GEMM).

**Caveat, verified from the format:** the engine validates tensor names **and dimensions** — it expects
`kExperts=512`. So you **cannot simply delete experts** from a `.hgn`; the router would index past the
histogram (the engine refuses rather than corrupt). A pruned Flash-Next therefore needs the engine to
support a smaller `kExperts`, or a **rebuild via the chlorine converter** (see §5).

### 4c. The practical shrink: use the 27B instead when 115 GB is not the point
The **27B Halogen is the same engine family at 35.9 GB** and it is working now. If the goal is "run the
Halogen kernel in production", the 27B delivers it today at 17.1 t/s (DFlash2) with 262k context and a
65 GB prompt cache — on the 8 GB carve, beside the other models.

---

## 5. Building a smaller/custom Halogen model (the long path)

Documented in full in `halo-custom-model-build-guide-20260912.md`. Summary for the shrink use-case:

1. Take the Flash-Next tensor spec (1198 tensors, `qwen4exp`, 512-expert MoE — captured via
   `hgn-inspect.py`).
2. Train/prune a base, then **repack with `chlorine-server/converter/hgn-convert.py`**. The open
   converter supports `bf16/f32/f16/i32/i64` + simple `fp8r`/`q4c` — **not** `i4l`, so a self-built file
   is lower-precision than Peonist's unless `i4l` is implemented (software work, validated against the
   chlorine engine's own kernels).
3. Load it in `flash_serve`; validate with the German bake-off before trusting it.

This is the only way to genuinely "shrink the model" for the Halogen kernel — the shipped 4-bit is
already the deliberate precision floor.

---

## 6. Recommended production posture on this machine

| Role | Engine | Carve | Status |
| --- | --- | --- | --- |
| **Halogen 27B (OpenAI service)** | `halogen` + `hipshim`, ports 8730/8731 | **8 GB** | ✅ **live now** |
| **Halogen Flash-Next** | `flash_serve` + `hipshim2`, port 8730 | **16–24 GB** | needs the carve notch; trunk pins, overlay 0.3 GB short at 8 GB |
| Flash-Next GGUF (comparison) | `myhacsint` Vulkan, port 8090 | 64 GB | measured: 201 t/s prefill, 22 t/s decode, MTP 100% |

**Rule of thumb discovered:** *Halogen wants a small carve (host RAM for pinning); llama.cpp/Vulkan
wants a large carve (device pool for the tensors).* They are mutually exclusive on one 128 GB box.

### To use Flash-Next on Halogen
Set **16 GB** dedicated graphics memory, reboot, then:
```bash
bash /mnt/c/Projects/REV-N/.revn-data/orchestrator/halo-fe-trunk.sh   # trunk-only variant, or
# edit it to enable the overlay (remove HALOGEN_CK_OVERLAY=none) for full quality
```
Given the measured progression (trunk pins cleanly at 8 GB; overlay is 0.3 GB short), 16 GB should
complete the load. I have not been able to verify the final Flash-Next tok/s yet because that needs the
carve change plus a reboot — it is the one remaining measurement.
