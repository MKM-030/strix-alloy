# Count1 embedding-only component — 5 October 2026

The paired stable projection's hidden CPU failure does not decide the separate
embedding branch when the native hidden GPU path remains intact. This sibling
retains the embedding branch exactly and supplies a component for a prospective
early token producer. It implements no producer hook, live substitution,
publication, dynamic batch, overlap or speed admission.

The [transformer](../../scripts/benchmarks/halogen_npu_early_embedding_graph.py)
selects the original nine embedding nodes and two embedding weight descriptors
from the sealed stable graph. The same existing external file is reused; its
unused hidden weight sections are not graph initializers. There is no hidden
input or computation. The unchanged arithmetic is four FLOAT MatMuls and
`((HH+HL)+LH)+LL`, followed by the original BF16 RNE/FLOAT boundary.

The normalized input boundary is one finite BF16-widened FLOAT row
`e_norm[1,2560]`. Fresh input preparation calls the pinned stable
`split_operand(e_norm, -1, np)`, returning `e_high[1,2560]` and
`e_low[1,2560]`. Output is `e_projection[1,2560]` on the BF16 lattice.
The producer may supply this boundary after separately proving its native
row/RMS lineage. This component does not itself qualify that producer.

The [probe](../../scripts/benchmarks/halogen_npu_early_embedding_probe.py)
reuses the sealed comparison, retained-output, timing, reserve, profile and
hardware-context methods. Its narrower fixture loader opens only the embedding
A/B normalized rows and original GPU embedding outputs, without the paired
loader's hidden rows or CPU hidden reference computation. Four warmups and
eight measured calls alternate the same sealed A/B inputs. CPU tolerance is
unchanged at `.002/.0002`; a passed, same-source, same-model embedding-only CPU
receipt is mandatory before NPU initialization. The failed paired CPU schema
cannot satisfy that requirement. NPU tolerance remains `.03/.003`, graph
optimization is explicitly disabled and all nine dynamic outputs must have
strict hardware/STX placement with CPU fallback disabled.

Root alone builds and executes assets in a coordinated current-server-idle
window with its owned deadline and 22/18-GiB admission/reserve guard. This source
does not authorize concurrent GPU inference. Supported safe Windows fabric
control and observed held state remain separate prerequisites before overlap.
No unsupported override or speculative overlap assumption is used. Component
latency includes fresh split preparation/diagnostic hashes, input copies and
`session.run`; it excludes producer/gather/RMS, compilation, post-validation,
live transport and GPU scheduling. It is never converted into token throughput.

| Source or dependency | SHA256 |
|---|---|
| Embedding-only transformer | `8b6d30944dce5028eab068646f43031e809b376f32e669d69ba0461d804f0338` |
| Embedding-only probe | `73438c84a0ad931813d53c7051f333f939adb463a1238666e024505920d12e69` |
| Stable transformer | `94438473e7b1084818515b6c8308b86dc1f24a48cee05fa68e0b1f3c48636566` |
| Stable probe helpers | `2ba71370edddd8d772111a16a985a90e02396066e6d88d04686acccbfa6b2558` |
| Original native probe | `7d1f51fd254389906c66b3ce44117fbe889b38b73861d192e4965893f6b0d9b0` |
| Reserve/profile/context helpers | `f5214bfc4c4a24ccfec7a708fcd90b919d05c1f0dfa8bf79eaa3bab6b5cf18a3` |
| Bounded JSON helper | `43eeebe26cbc0312832dd65a756c030380e13c964e47363c31f5598cb6a2697f` |
| Stable model | `77e704f65f2d04a35379360e65cf13919cbb02747656bc7675991254d60a0c0f` |
| Stable receipt | `7abfe3723b74fe3728644e0a727662b9903a9a68bb8906ac4967923d4d6d653b` |
| Stable shared weight file | `61ccb018d6855f1d189c39a22554bfaf82f1a31e95a7cd8b745042f7798b906f` |
| Frozen FC fixtures | `ae61a7924d985b1fd35e5d87eabd47736dbf20b91958bd5d7003dcf1cdb84f11` |
| Original native FC replay | `2fb0f6a198581156e430301064acef3e41d10a99e0a0cd06ab5ae9a16b8ed5fb` |

Builder CLI uses `--source-stable-projection`, `--stable-projection-receipt`,
`--stable-projection-receipt-sha256` and a fresh same-folder `--output`.
Probe CLI uses `--model`, `--projection-receipt`, its independently supplied
`--projection-receipt-sha256`, `--transformer-sha256`, `--fc-fixtures`,
`--fc-fixtures-sha256`, `--native-fc-replay`, `--native-fc-replay-sha256`,
`--provider cpu` and a fresh `--report`. NPU adds the verified `--ep-dir`,
passed `--cpu-gate` and its independently supplied `--cpu-gate-sha256`, with
`--provider npu` and a fresh report/cache folder. There is no wire, late-cut or
batch CLI. BLAS/OpenMP thread variables remain 1.

The source author parsed the files and ran two standard-library contract checks:
hidden dependency rejection and failed/paired/wrong-tolerance CPU receipt
rejection. These checks import no ONNX, numerical runtime or provider and read
no model/tensor/engine payload. An independent source review found no actionable
gate, hidden-dependency or cleanup issue at the source identities above.
Root built the released graph successfully under an owned clean guard, then
executed the CPU and NPU diagnostics below. The source author performed no
payload, provider or model execution.

## Executed CPU and NPU component gates

Root's same-candidate strict CPU gate passed before the isolated NPU window.
Both completed one session and all twelve alternating calls. Every repeated
output hash was stable; changing A/B inputs changed the result. All returned
values were finite FLOAT with shape `[1,2560]` on the BF16 lattice. CPU uses
`.002/.0002` and NPU uses `.03/.003`, without changing the original native GPU
oracle. The paired hidden CPU failure remains preserved and unrelated to this
embedding-only receipt.

| Provider and input | Values outside original tolerance | Different native BF16 words | Maximum absolute error | Output SHA256 |
|---|---:|---:|---:|---|
| CPU A | 0 | 0 | 0 | `f9f271db4fbeab9ecf6a8825abe2212f9a02a48955d7b24daa3b231d2c575826` |
| CPU B | 0 | 1 | 0.0000019073486328125 | `929855e9dc6591276fabed003f9d6a9eb8bf6eed1ec30cf2fd1b8e4555390306` |
| NPU A | 0 | 858 | 0.00390625 | `a4f4c7f1cd763d83d60997bfb1f3a61bd9060e316e9af8d1555956fa26662ce2` |
| NPU B | 0 | 847 | 0.001953125 | `0d4c79922fee49164d067fab433678ccf6c5ac682b8daeafeaa232d32ceec6c1` |

The CPU profile proves 108 CPU-only node events: nine nodes times twelve calls.
The NPU context proves all nine required dynamic outputs in one hardware/STX
partition, with only `e_high/e_low` inputs and the two embedding weight
initializers. CPU fallback is disabled. Its execution profile records twelve
VitisAI events and no CPU node. This is tolerance agreement on frozen inputs,
not exact native word parity, arbitrary producer rows, logits, proposals or
acceptance qualification.

| Isolated component | Mean session execution | Mean input preparation/copy diagnostics | Mean complete diagnostic call |
|---|---:|---:|---:|
| CPU | 2.2468875 ms | 1.3064875 ms | 3.553375 ms |
| NPU | 0.9674 ms | 1.137375 ms | 2.104775 ms |

CPU session initialization took 64.4195 ms; NPU initialization including its
cold compilation took 24385.9021 ms, approximately 24.386 seconds, outside the
per-call means. The earlier original GPU `0.4871700625 ms` host bracket measures
both resident embedding and hidden FCs and an event wait with a different
scope. It is not an embedding-only matched engine control. Neither bracket is
converted into token throughput or an overlap budget. These isolated component
observations establish no live NPU benefit.

| Executed artifact | SHA256 |
|---|---|
| Embedding-only model, bound by root's receipts | `562a5de0f53aa8d271fca4ba239e8ded2def734f760680ef546dd94c7fcfeb07` |
| Model receipt | `5ce966af3b6fcb92b54dcd75d99650411e09dedc5310af040221ac399f930a77` |
| [CPU receipt](../../server/.local/optimization9h-20261004/early-embedding-cpu-f246105cf64f4461992703308f0ef0b7/cpu.json) | `f25400937c473fedc126d3e3d4d6d422229f4a0cd218e5ef34cd0798faa3c6aa` |
| [CPU owned result](../../server/.local/optimization9h-20261004/early-embedding-cpu-f246105cf64f4461992703308f0ef0b7/result.json) | `457810293496a3333be193de5374450dfc94fb2c3da34ff743e6d20e29289c0f` |
| CPU profile | `7de237be03fcac18eba5814277aa23c1b3bd9989d8d62c1f379a5e71e4e22b20` |
| [NPU receipt](../../server/.local/optimization9h-20261004/early-embedding-npu-d29ea291e8e344ee8e8a2bb3726562e2/npu.json) | `6f4bb9fe244d0c5b2ebaa5af8627bc037c27d5b6b93fab1b32b2a9596c66b444` |
| [NPU owned result](../../server/.local/optimization9h-20261004/early-embedding-npu-d29ea291e8e344ee8e8a2bb3726562e2/result.json) | `92169d5da12360e05a1557c1b2f850d67645ff6b515bdccb90cf15f61574acb1` |
| NPU profile | `a784d67fdb5d6df258ec2a601fa55aa9d629c70da019b6202bca758da3f06447` |
| NPU context | `cc02741cd9859066a44ecd8c37cd7d8b2c7950f2c1b5f7348d589b600316ff63` |
| Reviewed NPU provider library | `95fb8d62d424f400a2f5f4e9f4d1ac1affdb35dd8c3309e85339010f50307352` |

Both owned results record passed, exit 0, jobs closed, monitors stopped, no
errors and no pending cleanup. NPU provider unregister, DLL-directory close and
bootstrap shutdown are all true, with no reserve-guard error. Minimum physical/
commit headroom was 27.085461/119.711555 GiB for CPU and
26.525074/119.190556 GiB for NPU. Root preserved the existing original GPU
server. All integration, overlap, full-MTP, acceptance and acceleration claims
remain false. Safe supported fabric control, actual early publication and a
matched full-engine NPU-on/off result are still required; the current 0.16.2
NPU-induced token-rate delta is unknown.
