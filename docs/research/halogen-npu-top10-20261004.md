# Flash-Next selected-top10 NPU prototype — 4 October 2026

The planned sparse-expert conversion now produces a single ONNX graph for ten
selected Flash-Next MTP experts. Each graph fixes the expert IDs and accepts
dynamic router coefficients. It batches the two expert matrix operations,
SiLU/gating and the final weighted sum. Strict standalone NPU replay passed:
100 measured calls averaged 1.504985 ms versus 6.394102 ms on single-thread CPU,
with `intra_op_num_threads=1`, a 4.248615×
ratio for this synthetic expert replay. Online Halogen MTP offload and its
end-to-end gain remain unqualified. Hardware kernel fusion and the number of
NPU dispatches remain unobserved.
The conversion source is the **w4b checkpoint's q4c MTP experts**, separately
from the v2 checkpoint used in the matched GPU benchmarks. Equality of their
MTP tensors has not been established; this replay cannot qualify the v2 head.

## Implemented and checked

`scripts/benchmarks/halogen_npu_expert_onnx.py` keeps its single-expert interface
and adds selected-top10 conversion directly from the existing HGN. Its reusable
q4c decoder seeks only the required rows. The converter checks the source HGN
header/tensor table against the manifest, checks shapes and finite weights, and
records SHA-256 for decoded weights, the ONNX model and external data. Existing
model, data or receipt files are refused rather than overwritten.

The final graph inputs are `x: float32[1,2560]` and
`routing_weights: float32[10,1,1]`; the output is `y: float32[1,2560]`.
The router vector is reshaped on the host without changing its values. Earlier
nine-operator graphs accepted `[10]` and used an ONNX Unsqueeze; replay retains
that historical input format. The current graph contains eight operators.
IDs 0 through 9 are an explicit prototype choice, not observed Halogen routing.
The graph contains 196,608,000 decoded weight bytes (187.5 MiB), compared with
roughly 27.85 MB of stored q4c payload for ten selected experts. Neither the
124-GB checkpoint nor its entire MTP head is expanded. Weights remain outside Git.

Six initial focused checks passed in the guarded Windows ML Python run:
batched ORT CPU output against ten separately evaluated NumPy experts, changed
router coefficients, the preserved single-expert input contract, and sparse
q4c row decoding across a flattened expert boundary/truncated input rejection,
geometry/finite-weight validation, pre-I/O selected-ID validation, and output
overwrite refusal.
These fixtures use small matrices. They do not qualify the full head or the NPU.

The initial nine-operator generated files are under
`C:\AI\halogen-mtp-npu\top10-final-20261004`. `top10.onnx.json` records their
identities. The model SHA-256 is
`66d31647f8ee98fe37ef0abc5b7fd7110fa181dbda096c8c5c389f90e4d01532`;
external-data SHA-256 is
`dc343857119884b5d3713b6478da1f2a9cc301ca87f72311d5c49c310cdc4a08`.

## Final strict replay

The final eight-operator graph is retained in
`C:\AI\halogen-mtp-npu\top10-routing-20261004`. Model SHA-256 is
`15d6df599dfe47407b0317158629f40bfd25975d7c0bbdf142faf4da16d9cb96`.
Its external data is byte-identical to the earlier graph; both final CPU/NPU
reports have matching model, data, synthetic-input and router SHA-256 values.
Eight fixtures passed, including independent NumPy expert calculations and
CPU parity across the historical `[10]` and final `[10,1,1]` router formats.

| Final replay metric | CPU (one thread) | NPU |
| --- | ---: | ---: |
| Measured calls | 100 | 100 |
| Mean / median | 6.394102 / 6.387700 ms | 1.504985 / 1.493300 ms |
| Minimum / p95 | 6.167100 / 6.535800 ms | 1.426900 / 1.620000 ms |
| Session initialization | 4.505700 ms | 32,704.237600 ms |
| Excluded warm-up | 52.970500 ms | 3.767200 ms |
| Maximum absolute error vs NumPy | 1.396984e-08 | 2.797833e-04 |

NPU error passed the declared approximation criterion `rtol=0.03, atol=0.003`.
This is one synthetic input/router replay and does not qualify full-head or
MTP acceptance quality. The 32.704-second session initialization includes
compilation and is excluded from the 100-call wall-clock measurements.

The ORT profile contains 305 events: 101 fused Node events (one warm-up plus
100 measured calls), all attributed to `VitisAIExecutionProvider`, and 204
Session events. Session registration lists both VitisAI and CPU providers;
CPU EP and Python fallback are disabled, and no executed Node is attributed
to CPU. Retained `context.json` names one `vaiml_par_0` hardware partition,
`device=VAIML`, `deviceName=stx`, `runnerType=hw`, with both inputs, output `y`
and all eight original node-output IDs. This establishes ORT attribution and
eight-of-eight hardware-partition coverage, without an assertion about every
internal provider operation or hardware dispatch.

The plugin's internal profiler emitted an `EndProfiling` error saying it had
no event to provide. The ORT Node profile above remains valid; device-cycle
timing and internal kernel attribution are unavailable. The successful cache
retains `context.json` and its `.rai` archive, rather than a loose frontend
`offload_map` report. No final AIE-100% map is claimed from a missing file.

All four stages exited 0 and their owned jobs closed. Provider unregister,
DLL-directory close and bootstrap shutdown succeeded. Physical-memory and
commit-headroom minima were 46.165653 and 200.909649 GiB, with no guard or
cleanup error; the GPU controller remained stopped and idle. All 18 immediate
artifact hashes in `result.json` match retained bytes. Final measured source
identities are builder `900a4deb32b86a48c6c132bf1326a3174bc5ef11482fd88b98005d0c40a4b722`,
tests `09c4407b1f47e690379c1a5261553028db319df71d873c800b1a5af7142751f7`,
and raw runner `82a2fe1650db85c871b0fbb4513419182b386f57340b6c5a4c99b44455e65b41`.

## Initial replay and compiler failure

Real-weight CPU replay passed with ONNX Runtime 1.25.2 and only
`CPUExecutionProvider`. It used synthetic input and router coefficients with
100 measured calls after one excluded warm-up. Maximum absolute error against
ten separately calculated NumPy experts was `1.3969838619232178e-08`.

| CPU replay metric | Result |
| --- | ---: |
| Mean / median | 6.375072 / 6.368850 ms |
| Minimum / p95 | 6.124100 / 6.515800 ms |
| Session initialization | 4.856800 ms |
| Excluded warm-up | 54.182900 ms |

The installed-provider NPU attempt reached compiler lowering but did not
complete within its 600-second deadline. Its generated command supplied
`-Xpreproc=-load-vfs -Xpreproc=C:\PROGRA~1\WindowsApps\`, without a DLL filename.
Peano reported `Cannot load DLL` and `Failed to load VFS`, followed by two
`pm_reload_analysis*.cc` compilation failures. No final NPU replay report,
numerical result or inference latency was produced. The zero process exit code
recorded after owned-job teardown is cleanup evidence, not inference success.

Preliminary compiler evidence identifies eight of nine ONNX operators in
`vaiml_par_0`: both MatMuls, three Muls, Sigmoid, Split and ReduceSum.
`Unsqueeze -> routing_column` is unsupported; its shape operation has 20
reported OPs and supplies `[10,1,1]` router coefficients to the AIE partition.
The frontend `offload_map` is AIE `88.888893%`, CPU `11.111107%`, while the
partition map is AIE 100%, CPU 0%. These are operator assignment reports,
not measured time fractions. ORT attribution exclusively to VitisAI would
establish provider placement but would not prove every internal operation
executes on NPU.

The preliminary summary names float32 model data and bfloat16 device data.
Kernel debug configuration also names `GemmBfp16` with
`dtype=bfloat16, enable_bfp16_wts=1`, and BF16 Mul/ReduceSum arguments.
This is evidence of selected compiler lowering, not a completed execution or
full-head precision qualification. It is consistent with AMD's documented
[automatic float-to-BF16 compilation flow](https://ryzenai.docs.amd.com/projects/WinML/en/latest/model_deployment.html).

All four owned jobs closed. The physical-memory minimum was 46.164165 GiB;
the commit-headroom minimum was 201.315166 GiB. The 18-GiB guard reported no
error, cleanup reported no error, and the GPU controller remained stopped
with no active request. Raw reports, compiler cache and logs are retained in
the directory above; provider-generated root signatures were identified by
timestamps and hashes and preserved in its `cwd-artifacts` directory.

## Current provider and Halogen seam

The installed Windows ML VitisAI package is
`MicrosoftCorporationII.WinML.AMD.NPU.EP.1.8_1.8.75.0`.
Its initial `NOT_READY` state meant installed but absent from the calling
process's dependency graph. `ensure_ready_async()` returned SUCCESS/HRESULT 0,
and explicit Python ONNX Runtime registration enumerated an AMD NPU device
(vendor 4130, device 6128), separately from the CPU and DirectML GPU devices.
No package download, driver, BIOS, system PATH or WSL setting change was needed.
This follows the [Windows ML provider state/registration procedure](https://learn.microsoft.com/en-us/windows/ai/new-windows-ml/initialize-execution-providers).

Actual Halogen 0.16.2 `flash_serve` SHA-256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`
matches the repository pin. Static inspection finds internal
`HALOGEN_TAP_FROM_SCAN` and `HALOGEN_MTP_PREFILL` strings, but no legacy
`--drafter-taps`, `--drafter-hidden`, `--drafter-ingest-bench`,
`--drafter-round-bench`, `state-export`, `state-import` or `mtp_draft` seam.
Absence of strings is supporting evidence, not proof about every internal
function. The supported entrypoint's NPU path serves separate small models;
it does not expose Flash-Next target state or accept external MTP drafts.
The existing WSL adaptation lacks the native Linux NPU device path.

This blocker also has primary-source support: the
[0.16.2 deployment repository](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/AGENTS.md)
states that the engine is closed source and the public tree contains deployment
code. Its [NPU interface](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md)
supports the listed small-model architectures and their qualified fine-tunes;
it does not provide an arbitrary Flash-Next MoE head interface. A wrapper-only
change cannot add the missing native callback or exact rollback contract.

## Reproduction and qualification boundary

Use the already installed application runtime; no setup or download occurs:

```powershell
$Py = 'C:\AI\runtimes\winml-npu\Scripts\python.exe'
& $Py -B .\scripts\benchmarks\halogen_npu_expert_onnx.py `
  --hgn C:\AI\models\halogen-flashnext\qwen38-flash-next-w4b.hgn `
  --manifest C:\AI\halogen-mtp-extracted\manifest.json `
  --expert-ids 0,1,2,3,4,5,6,7,8,9 --out C:\AI\halogen-mtp-npu\NEW\top10.onnx
& $Py -B -m unittest discover -s scripts/benchmarks/tests `
  -p test_halogen_npu_expert_onnx.py -v
& $Py -B .\scripts\benchmarks\halogen_npu_expert_onnx.py `
  --check-model C:\AI\halogen-mtp-npu\NEW\top10.onnx `
  --provider cpu --reps 100 --report C:\AI\halogen-mtp-npu\NEW\cpu.json
```

The same replay CLI accepts `--provider npu`. Run that stage only in the
coordinated NPU-only window, with the GPU engines stopped and the existing
18-GiB physical/commit process-owner guard. The replay does not supervise its
own process or provide an allocation reservation. It refuses acquisition of
missing providers, selects the actual VitisAI NPU device, disables CPU EP and
Python session fallback, and requires exclusive VitisAI profile attribution.
Compiler partition reports must also be inspected for internal host operations.
Numerical tolerances are recorded separately: CPU `rtol=3e-5, atol=3e-6`,
NPU approximation `rtol=0.03, atol=0.003`. These thresholds do not establish
the compiler's actual execution precision. NPU tolerances are a prototype screening
criterion, not full-model quality qualification.

The isolated provider-path retry is retained in
`C:\AI\halogen-mtp-npu\top10-copyep-20261004`. Optional `--ep-dir` first checks
the complete file set and every file's size/SHA-256 against the active catalog
directory. The unchanged installed provider's 12 files (737,444,241 bytes)
were copied to `C:\AI\halogen-mtp-npu\npu-ep-1.8.75-20261004`; the copy manifest
SHA-256 is `649a90d988b29c7dd4f8b1b57da902d435fb406db13d5a1cc18086907afa83a1`.
The retry retained WinML bootstrap, used a fresh compiler cache and the same
nine-operator graph. Compilation succeeded with a complete VFS DLL argument,
`C:\AI\HALOGE~2\NPU-EP~1.75-\ONNXRU~4.DLL`. Strict session initialization then
refused the graph's required CPU EP assignment, ending the NPU stage after
34.742359 seconds with exit 1. All owned jobs closed; provider unregister,
DLL-directory close and bootstrap shutdown succeeded. Physical/commit minima
were 46.259178/201.000767 GiB with no guard or cleanup error. Seven fixtures and
the repeated CPU replay passed; its mean/median were 6.354415/6.349700 ms,
and the numerical error and graph/data/input/router hashes matched the first run.

The attempted module sampler recorded 18 snapshots and one WinError 18, without
any observed provider module path. Module placement is therefore unavailable.
The launched runner's startup receipt recorded SHA-256
`a26ecce4defaba2c4f8661fa26bc61a268c5259723321dd0fc1b629033245c31`.
Its on-disk pathname was edited after launch during a coordination race; the
exact launched bytes are preserved separately as
`run_top10_copyep_guarded_launched_20261004.py` with that matching hash.
That pathname will not be reused for a run.

This changes a process's provider path without changing the installed package,
driver or system PATH. No NPU numerical result or latency was produced.

The final bounded refinement moved only the unsupported router reshape
outside ONNX, preserving the weights and arithmetic. Its fresh guarded run is
`C:\AI\halogen-mtp-npu\top10-routing-20261004`, with the final source and a
separately reviewed runner. The original nine-operator graphs and reports stay
available. The final runner omits the unavailable module sampler and preserves
the independent 600-second stage deadline. It passed all four stages as
reported above.

The measured NPU latency and 4.25× single-thread CPU/NPU ratio apply only to this
selected expert replay. No complete-head, Halogen PP/TG or online MTP speedup is claimed.
Session initialization/compilation is not steady-state
inference latency; the replay records warm-up and measured calls separately.

Remaining integration work is concrete: supply actual dynamic top-10 selection,
add attention/shared-expert/hyperconnection/lm-head work, preserve exact target
and drafter state across rejection, and add a supported Halogen export/import
interface. Only then can the planned MTP priming and decode replacement be
tested end to end. A separate small model or an auxiliary chat sidecar does not
supply that state contract.
