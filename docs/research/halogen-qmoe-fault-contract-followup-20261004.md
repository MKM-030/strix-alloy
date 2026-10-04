# QMoEBf contract follow-up — 2026-10-04

## Result

**Exact-caller follow-up identified a concrete activation-rank mismatch.** The
installed AMDQMoEKernel reads activation shape[2] without a rank check. The
frozen candidate supplies rank2 `[1,2560]`. A captured invocation propagated
the out-of-range third dimension into a 3.963 TiB BF16 row-copy request and
faulted inside Light's memory-copy routine. The coherent rank3 candidate is
`x/y=[1,1,2560]`, retaining router `[1,512]`. Root executed this candidate at
11:08 UTC. It passed the earlier copy boundary and failed later in the
DynamicDispatch BO path. Successful output or native performance is not claimed.

The retained OGA-style allocator holder did not repair the first-call access
violation. The available evidence establishes successful session admission and
allocator acquisition, followed by a read AV during the first invocation. It
does not establish valid output, provider attribution, native inference speed,
MTP acceptance, or a performance gain.

This analysis is source-only. No provider imports, native calls, model changes,
package installation, bank reads, or bank rehashes were performed.

## Observed attempt

Attempt directory:
`server/.local/optimization9h-20261004/qmoe-retained-admission-daf275ea3fd74e81a9990f37782612aa/`.

The trace reaches `strict_session_admission` and
`synthetic_call_0_invoke`, then cleanup/failure. The fault record is a read
`0xc0000005` at RIP `0x00007ffbdda2a541`, fault address
`0x0000045887cfeca0`. The original snapshot has 56 modules and records
`module_lookup:unknown`. No specific DLL or internal caller can be assigned from
that record.

The first router fixture chooses experts 0–9. The intended second fixture
choosing experts 502–511 was never reached.

### Subsequent root-owned negative attempts

The refreshed diagnostic
`qmoe-diagnostic-admission-758cde7a2ddd4710b02ada7ea71ab6b8` completes the
pre-call refresh (87 modules, generation2) and reaches call0. Its record now
attributes the read at zero to System32 `xrt_coreutil.dll`, RVA `0xf2186`, with
RBX0. Post-exception host resolution independently agrees. This is the same
`xrt::bo::size()+0x36` immediate boundary described in
`halogen-qmoe-xrt-fault-20261004.md`; it still does not identify the buffer role
or caller.

The Header-basename-only attempt
`qmoe-basename-admission-3b6d81d849784e9b8f75fb5e02517e5d` confirms the actual
option `halogen-qmoe-512-top10.pb.bin`, repeats successful refresh and session
admission, and fails at the same XRT RVA/readNULL/RBX0. The basename convention
did not repair the fault. Do not repeat that hypothesis with unchanged inputs.

These saved stdout/fault/admission records were inspected read-only. Hardware
was launched by root, not by this source-analysis agent.

### Exact native caller and dimensional failure

Root's bounded-unwind attempt
`qmoe-stack-admission-67b8899b9b6147e0877624740a2fd210` captures a different
immediate fault than the null-XRT cases. It is a nonnull invalid read inside the
exact pinned Light library atRVA0x2ca541. The unwind follows ORT callbacks back
to AMDQMoEKernel's method atreturnRVA0x14eb48 and then the Light hybrid wrapper
at0xe5dce. These immediate boundaries must remain distinct.

Static disassembly establishes:

1. At0x14da1b–0x14da22 the kernel fetches input0 with
   `KernelContext_GetInput` (OrtApi offset0x2d0).
2. At0x14da46–0x14da6c it obtains type/shape info and calls helper0x87760. The
   helper uses `GetDimensionsCount` (0x1e8), constructs an int64 vector of that
   count, and fills it using `GetDimensions` (0x1f0).
3. At0x14da88 it loads that vector's begin pointer;0x14da8c reads
   `[begin+0x10]`, the third dimension, without a rank check. It saves the value
   at`[rbp-0x80]`.
4. At0x14eaeb–0x14eaef that saved value becomes callback user-data field3.
   At0x14eb3b the kernel selects OrtApi offset0x890:
   `KernelContext_ParallelFor`, pointer index274 in the pinned CAPI29 header.
   The indirect call starts at0x14eb42 and returns to0x14eb48. It supplies
   callback0x151fa0, not a tensor/allocator accessor.
5. Callback0x151fa0 multiplies field3 by2 for the BF16 row-copy byte count. Its
   source row is chosen by floor(iterator/topk); its destination row comes from
   an index vector. At0x151fd4 it tail-jumps to0x2ca3c0, a memory-copy routine.
6. The exact fault instruction0x2ca541 is
   `vmovdqu ymm5,[rdx+r8-0x20]`, reading the final32 bytes of the requested copy.

Saved registers are sourceRDX`0x1fb4cdb0000`, sizeR8`0x3f6913c4bc0`, and
faultaddress`0x5f1de174ba0`. The arithmetic
`RDX + R8 - 32 == faultaddress` holds exactly. R8 is4,357,533,486,016 bytes,
corresponding to an interpreted hidden dimension2,178,766,743,008. The requested
copy is3.963 TiB; it is not a valid2560-element BF16 row.

The matching PE unwind ranges are `[0x2ca3c0,0x2caa2d)`,
`[0x14d990,0x14f550)`, and`[0xe5d80,0xe5e1f)`. This evidence gives a concrete
minimal candidate: change activation/output metadata, host shape checks and
allocations coherently to rank3 `[1,1,2560]`, retaining all bank/weight/activation
attributes and router `[1,512]`. The generic eager converter's rank2 pattern
does not establish that this closed NPU-only QMoEBf method handles rank2.

## Minimal discriminating changes, in order

### Executed rank3 correction

Root-owned attempt `qmoe-rank3-admission-61e998509c8d4f86b39aaf6ef3bee0fb`
uses the same frozen bank, provider, allocator holder and attributes. Its first
invocation records a null read at XRT `0xf2186`. The bounded unwind identifies
DynamicDispatch return RVAs `0x56a7a5` and `0xc7cac7`, followed by Light
`0x151ccd`, `0x14eca0`, and `0xe5dce`. This establishes a later call chain than
the rank2 invalid-copy return at `0x14eb48`; it does not establish valid device
execution or identify the missing BO role without further caller analysis.

Normal native receipt and counters remain null after the exception. No call
returned, output hashes or completed-call timings are qualified, and the
profile is empty. Child terminal exit `0xc0000409` is distinct from captured
AV `0xc0000005`. Owned Job closure, latch release and final sealed ORT integrity
all passed. Minimum physical/commit headroom was 43.3727/198.7775 GiB, safely
above the 18 GiB floor. Do not repeat this unchanged candidate. Raw artifacts
are bound by the [resumed-attempt ledger](halogen-qmoe-resumed-attempts-20261004.json).

### Exact padded-N output-buffer failure

The rank3 trace resolves the missing BO role. Light `0x151870` passes a
nonempty output-address vector and an empty output-BO vector to DD's
address-based `mladfmatmulbias::execute`. The address comes from
`xrt::bo::address()` plus an offset; it is not a proved CPU pointer. The
captured DD return at `0xc7cac7` belongs to the post-kernel depadding path.
Pinned `mladfmatmulbias.cpp:920–931` runs that path when `wait` is true and
logical N is smaller than kernel N, then unconditionally accesses
`outputs[0].sync()` and `outputs[0].map()`. The empty BO vector explains the
null read through helper `0x56a790` into XRT `bo::size()`.

The captured Light return `0x14eca0` identifies FC1, before SwiGLU; FC2's
corresponding return is `0x14ee38`. FC1 logical N1280/padded N2560 triggers
this path; FC2 logical N2560/padded N3072 would also trigger it. Source permits
address-only buffers when selecting kernel addresses, but the depadding path
does not handle that case. This is a concrete caller/implementation mismatch,
not an allocator-lifetime or IoBinding hypothesis.

The smallest fully exact K/N control found in the retained M1/G32 kernel
inventory is hidden2880/intermediate2880: FC1 `(2880,5760)`, FC2
`(2880,2880)`. Proper zero-padding/cropping could preserve the original
2560/640 expert arithmetic, but dense work increases about5.06 times and a
512-expert bank grows substantially. It is not a qualified speed candidate.
The next practical correction is to provide an actual output BO at the right
sub-buffer offset in an isolated companion path, with shape and memory
semantics preserved. No installed provider or driver has been patched.

The next discriminating change is selected from this exact BO caller chain,
before expanding the historical top-k/router/pool hypothesis matrix below.

The exact-caller rank3 correction above now takes priority over the earlier
hypothesis list below. Do not launch top-k/router/bank variants before observing
that coherent candidate.

1. **Header path convention — tested without repair.** Change only `external_data_file` from the
   absolute Header path to `halogen-qmoe-512-top10.pb.bin`, retaining the exact
   `model_root`, graph, bank, inputs, and other options. AMD's pinned published
   GPT-OSS configuration supplies a Header basename. This is a cheap alignment
   with a known working convention; it is not evidence that absolute paths are
   prohibited. Root first retains the absolute path for its controlled refreshed
  module diagnostic.
2. **Top-k scheduling.** Change k10 to k4 while retaining the 512-expert bank and
   Qwen geometry, with a coherent top4 input fixture. No public inspected source
   documents a QMoEBf top-k bound. Success would implicate an unsupported k10
   path, without proving real-model quality or acceptance.
3. **Router type.** Change the graph and host allocation/filling together from
   FLOAT to BF16. AMD's eager converter accepts both types; FLOAT is therefore
   not a demonstrated schema violation. A BF16 success would isolate an
   installed-provider path difference. Reinterpreting a FLOAT pointer as BF16
   would be invalid and would confound the result.
4. **Pool or whole-bank extent.** If needed, construct a consistent 32-expert,
   k4 control at the same Qwen geometry. A success would confound expert count
   and total bank size. Only if that branch warrants it, a 368/369-expert boundary
   can distinguish a potential signed-32-bit whole-bank extent issue.
5. **Geometry support.** Generic DD packer admission is not QMoEBf runtime
   support. A bounded official GPT-OSS hidden/intermediate 2880 geometry control
   can distinguish model geometry support after the cheaper branches. Preserve
   logical K/N attributes: AMD's converter stores logical attributes while
   packing padded matrices.
6. **Activation branch.** A synthetic zero-bank variant changing only alpha,
   beta, and limit to the official GPT-OSS values (1.702, 1.0, 7.0) can test a
   parameter-dependent provider branch. It cannot establish correct Qwen
   semantics or draft quality.

Stop expanding the matrix when a change supplies discriminating evidence.
Repeated holder-lifetime variants and package/bank rehashes do not discriminate
the remaining hypotheses.

## What the sources establish

- The AMD eager QMoE converter accepts router FLOAT and BF16 and wraps activation
  and output as BF16. The local two-dimensional `[1, hidden]` activation is not
  inherently invalid under that converter.
- AMD's packing pipeline replaces original weight/scale/bias/zero-point inputs
  with same-dtype empty tensors and appends `.packed.qexperts`.
- The packer retains logical K/N metadata while using padded physical geometry.
  Do not change the attributes to padded sizes as an assumed repair.
- `MAX_NUM_EXPERTS=3` in the inspected converter counts FC input groups. It is
  not an expert-pool limit.
- Header Tensor offset and size are UINT64; shape is INT64. The 2,986,344,448-byte
  bank is representable. No serialization overflow is demonstrated.
- `max_npu_buffer_size=0` matches the QMoE converter branch: that maximum is
  updated for `.packed` NPU weights, not `.packed.qexperts`.
- The official supported-model table lists GPT-OSS-20B as MoE, with 32 local
  experts and top4 from its original model configuration. It does not qualify
  Qwen's 512-expert/top10 geometry. This is support-scope evidence, not a proven
  kernel limit.
- Standard SwiGLU alpha1/beta0 with interleaved gate/up rows is consistent with
  the upstream ORT schema. This does not prove AMD's closed QMoEBf implementation
  accepts every upstream attribute combination.
- The affine helper explicitly changes `[gate;up]` rows into
  `[g0,u0,g1,u1,...]` before INT4 preparation. A zero bank cannot distinguish row
  order or activation arithmetic. A later small nonzero distinct gate/up fixture
  is needed only after a call first returns valid output.

## Static extent calculations

Current expert stride: 5,832,704 bytes (64 KiB aligned).

| Experts | Total bank bytes | Relation to INT32_MAX |
|---:|---:|---|
| 32 | 186,646,528 | below |
| 256 | 1,493,172,224 | below |
| 368 | 2,146,435,072 | below |
| 369 | 2,152,267,776 | above |
| 512 | 2,986,344,448 | above |

Expert369 is the first expert whose base offset exceeds INT32_MAX. The first
failed fixture uses experts0–9, so selected-expert offsets above2GiB cannot alone
explain that first failure. Whole-bank allocation or extent narrowing remains an
unproved provider hypothesis.

## Fault collector source review

Finite source review of `halogen_qmoe_fault_capture_refresh.c` and
`halogen_qmoe_retained_allocator_diagnostic.c` found no actionable concurrency
or C ABI defect. The nonblocking writer gate excludes snapshot mutation and
file closure while the handler operates; the handler does not acquire the
lifecycle lock. Snapshot publication uses Interlocked operations. The callback
is the retained DLL's `DWORD __cdecl(void)` export. The receipt asserts size88
and QPC field offsets64/72.

The snapshot remains best effort: DLLs loaded after refresh can still yield
`module_lookup:unknown`. The implementation records that limitation rather than
inventing attribution. This review does not qualify compilation, callback
execution, or provider behavior.

## OGA ownership and CPU arena comparison

OGA0.14 `generators.cpp`59–68 creates and registers a CPU arena in the
environment before EP setup. This differs from the standalone helper. However,
ORT1.29 `inference_session.cc` adopts registered environment allocators only
when `session.use_env_allocators=1`, with default0. The inspected OGA
RyzenAI/general session-option/model paths do not add that flag. ORT's
`SessionState::UpdateAllocatorsWithEnvAllocators` replaces allocator entries by
OrtDevice. Adding an invented environment-adoption flag could therefore replace
the provider's RMM CPU/default allocator with an ordinary CPU allocator. It is
not an established repair.

The exact registration-only alignment is representable with public CAPI29:
CreateArenaCfgV2 with keys `max_mem`, `arena_extend_strategy`,
`initial_chunk_size_bytes`, `max_dead_bytes_per_chunk`; values0 and three
size_t(-1); then CreateAndRegisterAllocator using default-allocator memory info,
before registering Light. The current evidence does not justify it as a
null-BO remedy before caller attribution.

OGA's RyzenAI `interface.cpp`25–55/155–168 stores the retained holder allocator,
allocates and frees through it, and treats CPU/device pointers as identical.
Its wrapper adds no explicit `xrt::bo` ownership or hidden initialization call.
Normal `Tensor::CreateTensor` uses that allocator just as the helper's
CreateTensorAsOrtValue does. The helper keeps its RMM-backed x/router/y values,
allocator, and holder alive through Run. No premature host-side release is
visible. OGA's State::Run uses the direct Run API with OrtValue arrays; the
helper uses IoBinding. That is a concrete API-path difference, not evidence
that IoBinding causes the current fault.

## Bounded static Light landmarks

Static analysis of the already pinned Light PE, without loading it, found:

- AMDQMoEKernel RTTI type descriptorRVA0x3e9990, complete-object locator0x390360,
  and vftable0x3682e0.
- Method entry0x14d990 occupies `[0x14d990,0x14f550)` and has two confirmed
  direct-IAT bo::size calls at0x14e453 and0x14e6a5. Both pass the address of a
  stack object (`lea rcx,[rbp+0x170]`). They cannot be selected as the actual
  caller from the fault record alone.
- QMoEFC1/FC2 error-message xrefs identify initialization-related function range
  `[0x14bce0,0x14d419)`. Other vftable entries include0x151fe0 and0x14f550.
- The PE imports RMM objectretain/release, buffer_from_unmanaged,
  buffer_make_resident, and platform_xrt_copy_underlying_bo. These identify
  available ownership/conversion operations, not the specific failed buffer.

The preexisting 97 Light bo::size callsites remain nonunique. The exact native
unwind caller is required before tracing a particular BO creation branch.

## Sources

Local pinned AMD sources under
`server/.local/optimization9h-20261004/qmoe-source-only/`:

- `ryzenai_onnx_utils__passes__llm__eager__qmoe.py`
- `ryzenai_onnx_utils__passes__llm__add_npu_weights__qmoe.py`
- `ryzenai_onnx_utils__transform__hybrid_llm.py`
- `ryzenai_onnx_utils__passes__normalize_qmoe.py`
- `ryzenai_onnx_utils__passes__llm__jit.py`
- `ryzenai_onnx_utils__proto__external_data_pb2.py`
- `llm_ops__mladfmatmulbias__matmulbias_tiling__matmulbias_tiling.cpp`

The inspected ONNX Utils1.8 wheel SHA256 is
`48a6e544d81208f8fecb9a5e1b5249da7bd1ee7ab212f093039e5f80085a6fd1`.

Primary public sources already inspected:

- [Pinned AMD GPT-OSS config](https://huggingface.co/amd/gpt-oss-20B_eager_rai_1.8.0_npu_16K/resolve/bcbb238a3e7e1c11fcac9850bde957e34eb51ebd/genai_config.json)
- [Original GPT-OSS model config](https://huggingface.co/openai/gpt-oss-20b/raw/main/config.json)
- [OGA0.14 GPT-OSS builder](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/python/py/models/builders/gptoss.py)
- [AMD supported LLM list](https://ryzenai.docs.amd.com/en/main/llm_list.html)
- [ORT1.29 MoE schema](https://github.com/microsoft/onnxruntime/blob/v1.29.0/onnxruntime/core/graph/contrib_ops/contrib_defs.cc#L1351-L1422)
- [ORT1.29 CPU MoE activation implementation](https://github.com/microsoft/onnxruntime/blob/v1.29.0/onnxruntime/contrib_ops/cpu/moe/moe_cpu.cc#L512-L532)
- [OGA0.14 global environment setup](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/generators.cpp#L59-L68)
- [OGA0.14 RyzenAI ownership](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/ryzenai/interface.cpp#L25-L55)
- [OGA0.14 tensor allocation](https://github.com/microsoft/onnxruntime-genai/blob/v0.14.0/src/tensor.cpp)
- [ORT1.29 session initialization](https://github.com/microsoft/onnxruntime/blob/v1.29.0/onnxruntime/core/session/inference_session.cc)
- [ORT1.29 allocator replacement](https://github.com/microsoft/onnxruntime/blob/v1.29.0/onnxruntime/core/framework/session_state.cc)
