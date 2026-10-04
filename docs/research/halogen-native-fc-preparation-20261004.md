# Native Q8 FC oracle and NPU projection preparation — 4 October 2026

The original GPU FC replay is compiled and its exclusive launch wrapper is
prepared. A projection-only ONNX candidate now includes the native decoded-weight
BF16 rounding boundary and has been built successfully. No original FC GPU
replay, candidate inference session, NPU execution, speed improvement or
acceptance improvement is established by this preparation.

The [dispatch audit](halogen-native-d-fc-dispatch-20261004.md) identifies the
actual raw Q8 kernels. The [accumulation audit](halogen-native-fc-accumulation-20261004.md)
recovers their chunk and butterfly schedule. Ordinary BLAS does not specify that
schedule, and exact DOT2 internal rounding remains unresolved. The actual native
GPU outputs therefore supply the next numerical oracle; the old ORT seed output
cannot qualify native arithmetic.

## Completed preparation

- The frozen fixture export passed and closed its owned job. It read exactly
  13,926,400 selected raw checkpoint bytes, verified the source identity before
  and after, and matched both decoded matrices to the retained external data.
  Hidden inputs are original native RMS outputs; embedding inputs remain
  CPU-prepared RMS, with native embedding RMS unqualified.
- The original M1/M4 replay compiled with GCC `-O2 -Wall -Wextra -Werror`, using
  the pinned headers and only libdl/libcrypto. Its owned compiler job closed.
  The resulting executable is
  `/home/revn/halogen-re/fc-replay-143eee1a74a048769a70d6668b441f31`, SHA256
  `fc631bcc9f8aecbf38ec457704481dea74603cead686c7da2405572d892beaae`.
- The new graph built in a CPU-only owned window. ONNX checking and immutable
  external-data checks passed; no provider/inference session was created.
  Physical/commit minima were **25.519985 / 117.491333 GiB**. The owned child
  exited0, its job closed and its reserve monitor stopped.
- Focused source review and AST checks cover the graph, probe, image wrapper and
  owned replay controller. Review fixes bind comparisons to the actual captured
  bytes, cross-check complete replay/runtime receipts and recover a container
  created during an ambiguous create timeout by exact UUID name, label, image
  and full ID. Recovery evidence is written after container removal. An
  unresolved create outcome stays failed with cleanup pending.

The built graph is
`C:/AI/halogen-mtp-npu/v2-d-prepare-20261004/d-native-projection-679839c01d074349b93f0bc3c37a26ab.onnx`,
SHA256 `9672f9b98b8b0b0efc10fadb30d0668ee9af25200681fe9b2e421dec97821291`.
Its receipt SHA256 is
`10b953f75bc7ba23195f8d5616ef6b46bb5a017bf91666ad7e96fb58a58284a6`.
Eleven nodes expose separate `e_projection[1,2560]` and
`h_projection[4,2560]`, both FLOAT values exactly widened from BF16. RMS and
seed addition are outside this segment. Original external initializer/data
bytes remain unchanged. Native accumulation parity remains unqualified.

## Admission and next execution

At the retained live observation, controller **PID10048**, run
`c5fd81b1e4cb47b3a6cd3ba1f6ead0cc`, was still ready at capacity262144. Its
authenticated health endpoint returned `ok`, the real Windows handle existed,
and Docker reported one running user-engine container. The fixture/compiler/
graph child PIDs were absent. This user server is preserved; no competing GPU
or NPU measurement was launched.

After actual process/provider/container checks establish a free GPU window:

```powershell
& 'C:\AI\runtimes\winml-npu\Scripts\python.exe' -B `
  .\scripts\benchmarks\halogen0162_fc_owned_run.py `
  --wrapper-sha256 c1120b8ca7d50c508e94affafe7bf59ed329d3d72c751b9407cf1cb4383b7542
```

The controller requires stopped serving state, free known ports, no active
container and22 GiB physical/commit admission. It retains its exact child/job,
uses a read-only pinned image and fixtures, a2-GiB cgroup,60-second Linux/
90-second Windows deadlines and a continuous18-GiB reserve. It launches exactly
four original kernels: A-embedding, A-hidden, B-embedding and B-hidden. Both
original FP32-weight and BF16-weight NumPy comparisons are informational and
remain distinct, with frozen `.002/.0002` tolerances.

The native projection probe then requires both outputs to pass12 balanced CPU
calls against those actual GPU words. NPU initialization requires the same
source/model/data/input/oracle/dependency bindings and a successful CPU receipt.
NPU `.03/.003` tolerances remain frozen; strict hardware partition and execution
proofs are required. Full D/head/history/native verification, useful NPU
integration and actual non-repetitive260K-input qualification remain open.

There is no new throughput row. The latest regular8K stock cohort remains
1866.537 prefill /48.423621 MTP decode tok/s /60% acceptance at262144 capacity;
the131,099-token sampled input remains1248.2 /33.90 /85%. Capacity and occupied
input, and greedy and sampled workloads, remain separate.

Machine-readable seals and retained window receipts are in
[the preparation evidence](halogen-native-fc-preparation-20261004.json).
The last official update check remains17:30:56UTC, next due19:30:56UTC. The
extended-goal heartbeat is ACTIVE. No installed driver, BIOS, voltage, model or
global WSL setting was changed.
