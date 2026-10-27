# Halogen steady-window proposer implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans task-by-task. Preserve test-first evidence.

**Goal:** Make the measured private GPU graph replay mechanism usable when the
actual prefix position, anchor embedding and committed context advance.

**Architecture:** A new default-off private wrapper owns fixed-shape inputs for
the long-context common-block-end window. Its captured operations read a GPU
prefix scalar, so absolute RoPE positions change without graph recapture. It
calls the existing five QueryLayer forwards, final norm and complete selector.
It does not authenticate or publish native proposals.

**Tech Stack:** Existing passive Python/PyTorch modules, explicit CPU fixtures
and future Root-only ROCm CUDAGraph qualification.

**Spec:** The design section below and the existing trained-proposal plan.

## Design and ruling

The completed original-head component measured13.28-14.22ms eager versus
12.21-12.43ms captured, but those graphs froze the prefix. Task4 of the existing
trained-proposal plan requires useful device execution. Root selects one
fixed long-window graph because8192-token workloads already fill that window;
per-position graph caches would retain unnecessary resources. Short contexts
keep the existing eager API. These are Root implementation decisions under
the user's continuing autonomous optimization authorization.

For block B in4/8, N=2048-B committed rows are visible. Refuse prefix P<N,
P>262144-B, or context not ending exactly atP with startP-N. Existing source
window is then entirely visible, including query KV; every row uses the same
2048-key noncausal window. Never silently pad/crop/rewrite a supplied context.

Allocate owned embeddings[B,2560], K/V[5,N,8,128], anchor int64[1], prefix
int64 scalar and static offsets0..B-1 on the explicitly selected device. CPU
fixtures are supported without any CUDA call. On GPU require a caller-owned
stream on that exact device; caller must establish all model-setup and input
producer dependencies. Copy private inputs and replay on that same stream.

Inside the parameterized compute, positions=prefix+offsets, then use precisely
the existing FP32 frequency/einsum/cos/sin/BF16 materialization order. Construct
the existing Layout and call layer.forward in the original sequence, followed
by existing _norm and selector.propose. No head quantization, vocabulary crop,
dot/reduction reordering or tolerance change. Do not change graph.py,
partitions.py, producer.py or their previously measured source pins.

Prepare validates host metadata and IDs (ordinary anchor0..248076), never
reads a device scalar, and copies into owned buffers. It first invalidates
prior local readiness so a failed update cannot replay a stale round. Successful
prepare grants one private eager/replay consumption. Capture warmups never
grant publication and capture requires fresh prepare before public replay.
Captured output tensors alias graph storage and expire on the next compute.
Their completion and immutable/native publication belong to the caller.

The module supplies no GEN authority, native prefix proof, weight provenance,
stream completion proof, engine integration, learned acceptance or speed claim.
Close drains the wrapper's own stream before releasing its captured storage;
retired/failed state cannot be replayed. No import-time Torch, device access,
files, threads, downloads, serving change or GPU allocation.

## Global constraints

- Root alone controls hardware/server lifecycle; no GPU/NPU/WSL calls by agents.
- Human-authorized Voice window: no model restarts, profile changes or hardware
  tests. CPU/source implementation continues; no large model payload/test load.
- New files only: scripts/research/dflash2_gpu/steady_proposer.py,
  test_steady_proposer.py, STEADY-PROPOSER.md and source provenance.
- No commits/push or edits to foreign controller/voice changes.
- CPU tolerance remains rtol0/atol0; CPU fixtures cannot qualify GPU capture.
- Keep physical/commit reserve18GiB; CPU fixtures must stay small enough not
  to interfere with the22GiB Voice request admission.

## Review focus

- Advancing positions at2044/8192/260000 actually changes RoPE and matches the
  original QueryLayer.layout exactly for BF16/FP32, blocks4/8.
- Context chronology and length are exact, no semantic zero padding or crop.
- Preparation/replay order is one-shot; invalid update invalidates old inputs.
- Mutable outputs/capture warmups cannot be mistaken for immutable proposals.
- Source stream/event/setup ownership remains explicit; CPU path never touches
  CUDA and GPU state is never implicitly initialized by import or validation.

## Task1: Private persistent inputs and parameterized computation

- [x] Write absent-module RED plus bounded exact layout/state tests first.
- [x] Implement owned steady inputs and long-window validation.
- [x] Implement same-stream eager/capture/replay wrapper with dynamic prefix.
- [x] Compare all newly computed layout tensors against original layout with
  unchanged zero tolerance at boundary/high positions; no full trained weights.
- [x] Test state refusal, buffer independence, same storage over updates,
  invalid metadata and passive import. Do not claim complete model parity from
  substituted routing fixtures.
- [x] Record CPU memory/runtime, pins, scope and explicit remaining GPU test.

## Task2: Root qualification after the shared hardware window is released

- [x] Independent code review and bounded CPU verification.
- [x] Use the existing pinned full trained GPU proposer and original head,
  actual setup dependencies and private context fixtures. Check eager versus
  replay at multiple advancing P with changed anchor and committed context.
- [x] Compare exact outputs and latency; reject unsafe/nonbeneficial variants.
- [ ] Only afterward join real native owner/capture/publication and run the
  frozen full-engine cohort. This source implementation is not that result.

## Root continuation, 26 October

Task1 source is implemented and independently reviewed. The final CPU suite
passes10 tests after a test-first correction from a contiguous Boolean mask
to the original expanded-row stride(0,1). Four frozen dependency pins remain
unchanged. CPU fixtures still do not qualify trained GPU arithmetic.

Ruling: The shared Voice hardware window was explicitly released. The first
targetHIP-to-hostTorch experiment was refused before any child because the
loaded-server entry reserve was below22GiB. Root will test the unchanged4KiB
transport with the verified normal engine stopped and a sleep-only holder of
the exact same image/runtime mounts, then restore normal visible serving.
This avoids changing a memory threshold or a serving profile. It establishes
only owned-runtime transport; actual engine feature publication remains open.

The steady trained GPU check may share this controlled offline window only
after independent source review. It has its own component receipt and finite
owned child, and cannot establish engine token rates or learned acceptance.
No commit/push is permitted while foreign controller/voice edits coexist.
