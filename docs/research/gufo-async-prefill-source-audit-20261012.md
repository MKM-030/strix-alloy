Secondary lead only: this is not the repository linked by the user's resolved Reddit shortlink.

Read-only source audit of mikealanni/gufo fork-enhancements pinned to afe7adee5b4acec5af6be73fd3f8169059bf9b8f (2026-10-12T01:30:45Z). No hardware work or code execution.

README reports 1698 GPU-only versus 1821 GPU+NPU tok/s (+7.2%) at 16384-token prefill, 1783 at 32768, and 1637 for served 40k cold tokens. It states greedy equality on 30 long prompts plus a copy task. These are author-reported results; the inspected source demonstrates the mechanism, not an independently reproduced benchmark or full numerical equivalence.

Mechanism: NpuGemm is one persistent XRT hardware context/kernel with fixed 4096x2560x1024 shape and max four hardware runs in flight. GPU HIP host callbacks enqueue a worker after GPU staging; GPU independent work follows; a later callback waits. hipHostMallocMapped pages are imported into XRT, with XRT sync operations but no normal-mode CPU memcpy. The isolated diagnostic mode copies private buffers.

Offload scope: six 1024-row ssm_in z slices over 36 linear-attention layers, eight query/gate slices (16 heads) over 12 attention layers, two shared-expert gate/up matrices (640 valid rows padded to1024) over48layers. Loader supports Q8_0 dense tensors only. Activation, weight and output staging uses v8bfp16ebs8: one shared exponent plus eight signed8-bit mantissas in9bytes. It is not ordinary INT8 quantization or proof of bitwise equality.

Wait locations establish real overlap: z completes between GDN scan and gated epilogue; attention query/gate completes after GPU K/V preparation and before their first consumer; shared-expert up/gate completes after routed experts and before shared-expert SwiGLU/down. Conditions require non-speculative wide prefill and token count divisible by4096; ordinary batch1decode does not take these branches.

Compared with our prior B1 embedding consumers (~41.6vs32.54decode tok/s; NPU projection1.850msvsGPU0.487ms), the reusable idea is a large independent prefill side projection with deferred synchronization and transfer elimination. It does not revive the serial B1 consumer. Closed-source Halogen0.18.1 would need an engine/backend extension; these Gufo environment variables do not configure Halogen.

Kernel source is 32 AIE cores (8x4), tiles128x64x128, with K hardwired2560; generic arbitrary GEMM replacement is not supported. README/docs describe fabric-clock/power prerequisites because concurrent GPU/NPU can hang; no such changes were attempted.

Primary pinned sources:
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/README.md
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/docs/NPU.md
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/src/models/qwen38_flash_next/kernels/rocm/npu_gemm.hpp
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/src/models/qwen38_flash_next/kernels/rocm/npu_gemm.cpp
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/src/models/qwen38_flash_next/kernels/rocm/device_model.cpp
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/src/models/qwen38_flash_next/kernels/rocm/executor.cpp
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/src/models/qwen38_flash_next/kernels/rocm/kernels.hip.cpp
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/tools/npu/n32_core_placed.py
- https://github.com/mikealanni/gufo/blob/afe7adee5b4acec5af6be73fd3f8169059bf9b8f/tools/npu/mm_bfp_mixed.cc
