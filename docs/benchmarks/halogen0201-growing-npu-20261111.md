# Growing NPU proposer: actual native component result

The new growing-context path passed its native numerical comparison on 11 November 2026. All **32,001,030 BF16 values** match the direct sequential reference exactly across 129 states, without relaxed tolerances. Its offline next-ID agreement is **66/128 = 51.56%** on the recorded target sequence. This establishes a working NPU component, **not native MTP acceptance or a measured Halogen speedup**.

| Native component observation | Growing candidate | Direct sequential reference |
| --- | ---: | ---: |
| Seed 512 IDs through owned logits, ms | 425.0998 | 427.6518 |
| Authoritative one-ID append through owned logits, mean ms | 22.3904 | 22.2825 |
| Appends | 128 | 128 |
| Initial / final local context | 512 / 640 | 512 / 640 |
| Complete shared-vocabulary values at every state | 248070 | 248070 |

These are in-process Windows QPC operation times, including native-library processing and the CPU copy/argmax that owns the logits. Row-file writing is timed separately and excluded. They are not pure NPU kernel timings and are not converted into engine tok/s. [Numeric summary and evidence](halogen0201-growing-npu-20261111.json), [prospective protocol](halogen0201-growing-npu-plan-20261111.md).

## What changed

The retained typed FLM 1.0.7 Qwen3.5-0.8B NPU engine receives the exact last 512 prompt IDs once. It then appends only actually recorded target IDs through context640, preserving its recurrent history. `ready_one()` reads already owned logits; it does not consume a speculative prediction or rebuild the 512-token seed after a wrong guess. Each proposal is read before that step's target ID is supplied to the NPU. All128 predicted IDs and all owned words/context lengths are checked.

Candidate and reference run in separate fresh native processes, sequentially. The reference performs the same clear, seed and authoritative forward sequence directly. Every full shared-vocabulary row is finite-scanned, its lowest-ID greedy result reconstructed, and its bytes compared independently. Both processes exit0 after about six seconds. This repairs the new growing path's qualification boundary; it does not declare the historical sequential-versus-full-prefill discrepancy repaired. The separate hidden-projection accuracy scope remains unchanged.

The input is one exact non-repeated 8192-token document family, with128 outputs captured from the paired2048 target warmup. This is distinct from the promoted paired8192 output trajectory. There is no 16K native-ID teacher family in this component. Offline agreement does not include the cost or correctness of real publication, scheduling or GPU acceptance.

## Actual ownership and providers

The helper is compiled from the sealed typed source, exact matching headers/import libraries and unchanged original build options. Twenty-two CPU tests pass. The actual loaded Qwen DLL, Q4NX DLL and System32 XRT paths/hashes match the selected inputs. The current XRT driver/library is retained; no model, driver, global PATH, BIOS, voltage or WSL setting is changed. The static PE inspection covers13 payload modules/935 imported symbols; Windows API-set contracts and internal OS dependency trees remain explicitly outside its complete static proof. A duplicated descriptive v1 helper hash in the preparation remains stale; effective source pins and the actual v2 PE report agree, as the independent review records.

Root owns both child process handles, with22/22 GiB entry admission,18/18 GiB runtime reserve, a120-second deadline per pass and no automatic retry. All four GPU admission receipts pass. Minimum observed reserves are22.6824 GiB physical and114.1357 GiB commit. The GPU server retains controller44072/backend16432 and the exact paired8192 profile/run, ready on8840 after both jobs. No resident NPU helper or live producer remains enabled.

Independent final audit SHA256: `4c7ec659e16b97e41f1709c72a641572e73ac86e9df92e9940dfe6958c38c255`. All raw rows, logs, module observations and comparison receipts are preserved locally. NPU-prefill tok/s, NPU-decode tok/s, native acceptance, target-readiness and full-engine benefit remain null.

## Next implementation boundary

The [ideal three-ID consumer](halogen0201-external-oracle-20261111.md) benefits from ready future tokens. This new count-one predictor still needs an authoritative append before its next prediction; the current consumer queries near target publication, and multiple accepted target IDs arrive in bursts. The 22.39-ms append therefore does not prove arrival before demand. Native opening can reuse a cached head prediction, so there is no guaranteed GPU-compute window to hide it.

Do not connect this component unchanged to the future-trajectory oracle wire. A real consumer must bind each replacement to its exact committed prefix, reject stale data and fall back immediately. Supported stateful lookahead/restore in a coherent FLM1.0.12 runtime and possible vectorized authoritative catch-up are the next source-supported candidates. Any benefit still requires actual readiness evidence followed by a full engine on/off comparison. The normal server uses the [measured paired8192 configuration](halogen0201-normal8192-20261111.md); the full acceleration goal remains open.

## Published implementation

[Canonical source and instructions](../../scripts/benchmarks/halogen_flm_growing_replay/README.md)
include the typed native component, sequential reference, exact comparator,
authority protocol and static PE inspection, with 39 passing CPU tests.
Independent review confirms that relocation changes only paths. Root's rebuild
has identical executable code/data/unwind/relocation sections; the complete
files differ only in COFF and mirrored debug timestamps.
[Build comparison](halogen0201-growing-npu-source-equivalence-20261111.json).
The measured private binary and all earlier frozen evidence remain intact.
