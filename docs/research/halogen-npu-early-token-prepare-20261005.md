# Early token embedding lineage gate — 5 October 2026

The retained assets permit a bounded token14367 preparation fixture. They do
not yet qualify its Q4C-to-native-table conversion. The new
[raw capture source](../../scripts/benchmarks/halogen0162_raw_embedding_capture.c)
and [offline validator/preparer](../../scripts/benchmarks/halogen_mtp_early_token_prepare.py)
make that missing dependency directly testable. The capture was not compiled
or executed by its author; the preparer's later metadata-only RMS qualification
binding was checked using the standard library against sealed JSON. Only
ordinary sources and retained JSON/text metadata were read by this audit.
Root alone owns payload reads, compilation and accelerator work.

This is not the rejected late normalized cut or a paired D graph. The capture
is a diagnostic native oracle at the late head's raw-gather return. A later
producer would begin from already known host tokens before trunk work. No early
runtime producer, batch publication, transport or NPU graph is implemented.
The full hidden path remains on the GPU. There is no useful-overlap/speed claim.

ROOT subsequently compiled the capture with GCC `-O2 -Wall -Wextra -Werror`
in an owned CPU job. The 40,360-byte ELF has SHA256
`33073dfe3c7f396aff1e50e431253f032d035a89f4194f528977faa62beac486`;
the source is `a16afefb35db8affd5f4373b68a44341d830323acd928e7f153a29c8005c9cce`.
The job exited 0 and closed; physical/commit minima were 27.270/119.983 GiB.
No library was loaded or accelerator called. The metadata-only preparation
also completed using the existing WinML Python, with plan SHA256
`df07680f0e9ff1002ce24cecac616ae913f33ac8b18225c15497e7d77e1e92e0`.
The initial base Python attempt lacked ONNX; no package was installed.

Independent source review confirms the ABI/call ordering. Running still
requires an owned launcher, actual allocation-extent evidence and independently
verified mapped capture/HIP/ROCr and checkpoint identities. Pointer arithmetic
and syntactically valid hashes alone cannot supply that provenance.

The exact retained lineage is:

| Stage | Source and boundary |
|---|---|
| Token | Host head argument, Count1/token14367; device IDs `*(model+0x730)` |
| Checkpoint row | `embed_tokens.weight`, Q4C store5/variant2, `[248320,2560]`, offset322560, size357580864; selected ranges: codebook322560/64B, row codes18712384/1280B, FP16 scales320470944/160B |
| Native table | Loader call `0x1770a3d -> 0x17edf00`, result stored `model+0x4f0` at `0x1770a42`; variant2 conversion branch `0x17ee50d..5d9 -> 0x17d2e50`. Numerical equivalence to the CPU decoder remains unproved |
| Gather | Original identity `0x18d5b40`, launch `0x17db449`, return `0x17db44e`; unchanged native table BF16 words to `*(model+0x6c8)` |
| Embedding RMS | In-place original identity `0x18d5160`, launch `0x17db517`; width2560/groups1, raw gamma `*(model+0xae8)`, FP32 gamma+1, epsilon bits `0x358637bd`, original product order and BF16 RNE |
| Gamma asset | `mtp.pre_fc_norm_embedding.weight`, raw store0 BF16, checkpoint offset65185026944/5120B; selected decoded `weights.data` offset52428800/10240B; raw-word hash `04c4a570850e06f2d8913da8220d54d4c7f87db6eb6d45480b938e8ba41d6a86` |
| Embedding FC | Descriptor `model+0x908`, normalized `model+0x6c8`, output `model+0xb00`, N=K2560; source `mtp.fc_embedding.weight`, Q8 store7/variant0, offset65164116864/6963200B; retained decoded `[out,in]` data at0/26214400B |

All native addresses come from the retained host/shader audit; no new engine
binary was read. Checkpoint SHA256 is
`71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`;
engine SHA256 is
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
The existing original-gather cache replay copies cached projected FC outputs
with a synthetic zero index. It supplies no original checkpoint-table oracle.

The capture is adapted from the frozen hidden-RMS tap
`4d612044fb5e84932726d8a4568d2ca3bd463832eeab875376d7c286c8640603`.
It checks the whole engine file, full mapped head hash, known head caller and
the exact 29-byte gather call sequence at `0x17db435`, including the original
launch and return. Count1/token14367 alone reserves one sample. Original head
and launch execute once, including observer failure paths. After a successful
gather launch, one successful device synchronization and one synchronous5120B
D2H copy finish before the native caller can enqueue in-place RMS. No device
allocation or tensor write is introduced. One fixed host row is retained, and
activation/records/complete plus that row are exported after the request. The
total cap is6 files including the two triggers and131072 bytes. Other tokens
and counts forward without capture.

Root must use a fresh exclusive owned process, immutable checkpoint/table,
qualified device allocations/context, no other head/launch interposer, pinned
HIP/image and the existing22-GiB admission/18-GiB reserve/deadline guard. Pointer
arithmetic is not allocation-lifetime proof. Installation is constructor-time,
not concurrent hot patching. The user's current engine is never loaded with
this candidate or restarted by these files. An absent capture mode is inert.

After independent source review, the concrete root CPU command is:

```powershell
& 'C:\AI\runtimes\winml-npu\Scripts\python.exe' -B `
  'C:\Projects\strix-alloy-clean\scripts\benchmarks\halogen_mtp_early_token_prepare.py' `
  --prepare-only `
  --source-sha256 228657fea31f01c345978d125803b87f62df14f4450d83247f6f63afb791d114 `
  --gather-source-sha256 a16afefb35db8affd5f4373b68a44341d830323acd928e7f153a29c8005c9cce `
  --plan 'C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004\early-token14367-rms-qualified.plan.json'
```

It opens only sealed source/JSON files. It reads no table, asset tensor,
checkpoint, engine or provider. Source-review edits require fresh independent
source pins. Root's separate compile stage may run this inside its existing
pinned image with a fresh owned output mount:

```sh
gcc -O2 -Wall -Wextra -Werror -shared -fPIC -fno-optimize-sibling-calls \
  /candidate/halogen0162_raw_embedding_capture.c -ldl -lcrypto -pthread \
  -o /result/libhalogen0162-raw-embedding-capture.so
```

A new root launcher/controller binding remains required; this document is not
permission to bypass owned-process admission. Activation requires
`HALOGEN_MTP_RAW_EMBEDDING_CAPTURE=gather14367-v1`, explicit wireD and a fresh
`HALOGEN_MTP_RAW_EMBEDDING_CAPTURE_DIR=/tmp/alloy-mtp-raw-embedding-<32hex>`.
The root controller publishes exclusive0600 `armed` containing
`gather14367-v1-ready\n`; after the owned request returns it publishes `harvest`
containing `gather14367-v1-harvest\n`. A Count1/token14367 invocation must
actually occur; no-sample failure is missing input, not numerical disproof.

The smallest disconfirming observation is one changed BF16 word among the2560
captured raw words versus retained token14367's CPU-decoded BF16 row, hash
`af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374`.
The offline `--export` mode requires the sealed plan, capture directory,
independent activation/records/complete hashes, fresh output directory and an
independently hashed root provenance receipt. Its provenance schema is
`halogen0162.raw-embedding-owned-provenance.v1`; the source's
`required_provenance` dictionary lists exact checkpoint/model/process/source,
cleanup and allocation-lifetime bindings. Root also supplies actual compiled
capture and HIP hashes. These observations cannot be manufactured from the
capture pointers alone. A mismatch retains `raw-gather-gate.json` and stops
before RMS/FC.

Only a matching raw oracle permits materialization. The preparer reuses pinned
BF16/RMS APIs, verifies the raw gamma words unchanged, reproduces frozen e-FC
input hash `97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892`,
rounds decoded e-FC weights to BF16 before tiled CPU FP32 MatMul and applies
the output BF16 boundary. It screens against the retained actual original GPU
A embedding-FC output under unchanged `.002/.0002`; NPU `.03/.003` is retained
without executing a provider. It reads only e-FC/gamma/one embedding-row
regions, rechecks selected hashes before publication, and never reads a hidden
tensor.

A subsequent JSON/source audit found an already executed original embedding
RMS qualification in the owned October 5 ROCr component window
`alloy-rocr-component-16a35be771404bd7a7ac3d1b43526528`. The stock original
shader used width2560/groups1, raw gamma and aliased input/output, with eight
warmups and 64 measured calls per frozen row. Its A raw-input hash
`af284c0101ac76b7562b3d9e19cfc6721266f282358d8f313a09b961435ee374`
produced normalized hash
`97079c27ab56da44c2ab29780c856be79803d402caf754acfbf7d187fbe34892`;
B raw-input hash
`e14b7e6b5bd1a53d1e0c26d0eb9d2356728668a89a2e591707c463cc1e2b01b4`
produced normalized hash
`8104e72375af48ab130c04b01fe68399e1d6c84951f9aa45c67a54b7d00db6ce`.
Both outputs repeat exactly and match the sealed NumPy/ORT RMS references.
The probe binds the original engine, its byte-identical embedded shader and
mapped HIP/ROCr identities; its owned process exited 0, closed and was removed.
The outer window passed without contamination or pending cleanup. The
[accuracy audit](halogen-npu-accuracy-audit-20261005.md) seals those receipts.

This qualifies the original embedding RMS boundary on the two supplied frozen
CPU raw rows. It does not qualify native Q4C table conversion or native gather:
neither row in that replay came from the newly proposed original-table capture.
The preparer now validates the sealed probe, stock-owned, outer-owned and
fixture JSON/source identities in a metadata-only binding. Both the plan and
export receipt carry `frozen_input_native_embedding_rms_qualified=True` and
the exact receipt bindings. The field
`original_native_embedding_rms_observed_by_this_export=False` distinguishes
this existing qualification from the current CPU export, which executes no
GPU. Its source SHA256 is
`228657fea31f01c345978d125803b87f62df14f4450d83247f6f63afb791d114`;
the original preparer and plan receipts remain preserved. The baseline binding
passed and 13 independent dispatch/hash/runtime/repeat/ownership/cleanup drifts
were rejected using only standard-library JSON/source checks. No new fixture,
tensor, model or provider was opened for those checks.

Root subsequently ran the final metadata-only preparer in a 45-second guarded
owned CPU process. The fresh plan is
`server/.local/optimization9h-20261004/early-token-metadata-refresh-0ac16816f0fd4c11a609d2d0632656e0/plan.json`,
SHA256 `77b41fcec8b5d9e9aef48f07e85ce4edb154083e4e78a465a196b49d3950492b`.
Its sibling `result.json`, SHA256
`5c65ce0d75b2d5efaee3e61c19e4fb6c0922d68a22d1da691d52eaf13fc0790b`,
records passed, exit 0, closed job and no errors. Minimum physical/commit
headroom was 27.664047/119.566479 GiB. Payload bytes read were zero; no GPU
or NPU call occurred and the user's engine was preserved. The original plan
`df07680f0e9ff1002ce24cecac616ae913f33ac8b18225c15497e7d77e1e92e0`
remains preserved, while the new plan carries the qualified frozen-input RMS
binding with the unchanged CPU/NPU tolerances.

RMS/rsq and DOT2 are not emulated bit-exactly, and one raw token match would not
establish general-table qualification. The exact native raw-gather gate,
actual early publication and timings of L/W/G remain later gates.
