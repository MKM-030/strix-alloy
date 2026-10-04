# Real v2 layer48 QMoE bank: prepared source only

`scripts/benchmarks/halogen_qmoe_real_pack.py` prepares a streamed conversion of
all 512 routed experts from the qualified native v2 checkpoint. Source SHA256:
`b74d76c4082d447285f55a1af41e8f28ec85a4bd35b5ce1535553eed6fe004d1`.
Only a stdlib AST syntax parse was performed during preparation; the source
was not imported or executed. No weight payload, decoder, packer, provider,
device, test or numerical fixture was run. This is not a completed real bank.

The existing Windows `qwen38-flash-next-mtp-extracted.hgn` and downloaded
`qwen38-flash-next-mtp.hgn` do not supply a retained canonical full-v2 payload
qualification. Neither is used. The converter instead reuses the pinned
`halogen_npu_v2_sparse.expert` reader and `hgn_q4c_slice.decode_rows`, with the
complete v2 integrity receipt, native identity and qualified header/table.

## Frozen dependencies and construction

- Windows CPython 3.12 interpreter:
  `C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe`, SHA256
  `4d6f5f81a4bca11191c4c7c6b43632694d0a4ce74e068619d8fdc161d469859a`.
  Its existing NumPy installation is required; no dependency is installed.
- Metadata receipt:
  `C:/AI/halogen-mtp-npu/v2-metadata-20261004/mtp-metadata.json`, SHA256
  `4159d1ddb9094907ba82b62940777317d9bc89e4c7a8cb881809ecb17912e3cb`.
- `backends/halogen-wsl2-0.16.2/.local/v2-integrity.json` and `machine.json`
  are pinned byte-for-byte by the new source. They bind
  `\\wsl.localhost\Ubuntu-24.04\home\revn\halogen-models-native\qwen38-flash-next-v2.hgn`
  to the complete checkpoint SHA256
  `71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`.
  The 66,687,678,432-byte checkpoint is not rehashed; its qualified native
  device/inode/size/mtime/ctime and small metadata are checked before and after.
- Existing AMD 1.8 staged package:
  `server/.local/optimization9h-20261004/qmoe-dd-stage-8bba3dba41e94053bb9196b918c2456f/payload/ryzenai_dynamic_dispatch`.
  The acquisition receipt, extension, `dyn_bins.dll` and `dyn_bins.zip` are
  independently pinned. Extension SHA256:
  `38814ad69d2233758b76bf82db922f2e674c0d01aace756ace066135cbf4aaab`.
  Installed DriverStore `xrt_coreutil.dll` hash and actual loaded path must
  match the earlier successful official offline packer contract.
- The q4c decoder, sparse reader, metadata reader, affine converter, prior
  pack probe, graph builder and host-memory helper have immutable source
  pins. Helper modules execute the checked source bytes rather than cached
  `.pyc` files. All input pins are rechecked before a completed receipt.

Each expert reads three bounded windows per matrix: codebook, codes and
padded scales. FC1's `[gate;up]` rows explicitly become
`[g0,u0,g1,u1,...]`; FC2 retains linear down rows. The existing affine
converter supplies approximate unsigned INT4 codes, FP32 scales, packed
zero points and zero bias. The exact official pack argument order and
attributes match `halogen_qmoe_pack_probe.py`.

Each pack must return FC1 logical/padded K/N 2560/1280→2560/2560 and 4,198,400
bytes, or FC2 K/N 640/2560→768/3072 and 1,597,440 bytes. The 36,864-byte FC2
tail gives a 5,832,704-byte aligned expert stride. The real 512-expert bank is
2,986,344,448 bytes (2.78125 GiB), in expert index order.

The converter writes `expert-diagnostics.jsonl` with every source window,
decoded/reordered/affine/packed hash, affine error diagnostic and host timing.
It flushes both outputs every 8 experts (46,661,632 bank bytes), performs
complete output SHA256 readback, rechecks the source identity and all pins,
and only then renames the `.partial` bank and publishes a passing receipt.
Cooperative failures retain partial bytes and a failed receipt; existing
evidence is never overwritten. Hard termination can prevent the child receipt
from being written; the parent guard must retain its lifecycle evidence.
No resume or automatic retry is provided.

## Future root-owned command

Only root may run the construction after the synthetic admission decision.
The external guard must create a fresh child directory, enforce exclusive
runtime ownership, monitor the 18 GiB physical/commit floor, own the Windows
job and impose a hard timeout. This source flag alone is not a parent guard.
The following array is the exact child argv payload for that guard; this
preparation did not launch it:

```powershell
$realPackDirectory = Join-Path 'C:\Projects\strix-alloy-clean\server\.local\optimization9h-20261004' ('qmoe-real-pack-' + [guid]::NewGuid().ToString('N'))
$realPackCommand = @(
  'C:\Users\Marcel\AppData\Local\Programs\Python\Python312\python.exe', '-B',
  'C:\Projects\strix-alloy-clean\scripts\benchmarks\halogen_qmoe_real_pack.py',
  '--root-owned-admission', '--expected-probe-sha256',
  'b74d76c4082d447285f55a1af41e8f28ec85a4bd35b5ce1535553eed6fe004d1',
  '--report', (Join-Path $realPackDirectory 'pack.json'),
  '--bank', (Join-Path $realPackDirectory 'qmoe-real-layer48.bin'),
  '--maximum-seconds', '1800'
)
```

A successful `pack.json` has exactly two FC aggregate rows and the real-bank
fields required by the frozen `halogen_qmoe_graph.derive_geometry`. It records
`synthetic=false` and `packed_gate_up_layout=interleaved`. The existing graph
builder can consume that receipt in the same directory using its normal
`--pack-receipt`, `--proto-source`, `--output` and `--top-k 10` arguments; this
source preparation creates no graph or Header.

The total source read extent is 1,426,128,896 bytes, including repeated
codebooks and padded scales; total decoded FP32 work is 9.375 GiB over time.
Only one expert's matrix is retained, with a 13,107,200-byte largest decoded
matrix and an explicit second copy for FC1 row ordering. Array working
storage is tens of MiB rather than the whole decoded bank. The child requires
1 GiB above the 18 GiB floor before importing NumPy/native dependencies and
128 MiB above the floor before each matrix. Native allocations and OS file
cache are not bounded by those array sizes; the external guard remains
necessary. Output requires the bank plus 64 MiB free disk margin.

Runtime is unmeasured. Earlier 20-expert sparse decoding took about 5 seconds,
which extrapolates to about 128 seconds for 512 experts; prior FC packing adds
about 39 seconds at unchanged per-expert costs. Affine quantization, hashing,
flushes, readback and cache state are additional. A planning range of 5–20
minutes is provisional; the cooperative deadline defaults to 30 minutes and
the root guard must enforce its own hard termination.

This approximate bank still requires real operator admission, routing and
arithmetic checks, native activation/scale semantics, state isolation,
commit/discard handling, target verification and live draft acceptance and
speed measurement. Diagnostics exclude DD BF16-scale rounding and NPU
arithmetic. No full-MTP or performance claim follows from bank construction.
