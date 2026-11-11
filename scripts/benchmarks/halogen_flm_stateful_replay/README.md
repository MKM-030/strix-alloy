# Finite FLM 1.0.12 stateful NPU replay

This source package reproduces the finite state save/restore component's protocol and exact offline comparator. It provides no live producer, IPC transport or Halogen integration. The [recorded result](../../../docs/benchmarks/halogen0201-stateful-npu-20261111.md) has zero differing BF16 words across 129 states / 32,001,030 values. That proves the tested always-restore path, not an engine speedup.

## Files and CPU tests

- `stateful_host.cpp`: the byte-identical measured Windows AMD64 C++ host. It uses the coherent FLM 1.0.12 headers and versioned C state API.
- `stateful_tools.py`: offline validation and full-row comparison. It checks finite BF16 values, lowest-index greedy ties, input authority, complete trajectories, forced-fixture separation and QPC chronology.
- `test_stateful_tools.py`: 13 generated CPU fixtures. They need no private captures, model, compiler, DLL, device or API.

```powershell
python -B -m unittest discover -s scripts/benchmarks/halogen_flm_stateful_replay -p 'test_*.py' -v
```

The comparator uses the unchanged exact-word criterion from [the growing replay package](../halogen_flm_growing_replay/replay_tools.py). Matching greedy IDs alone never relax word equality.

## Native protocol and boundary

Use one coherent FLM 1.0.12 SDK/runtime with its matching import libraries, token kernels and MSVC runtime. The measured build used AMD64 MSVC 14.44, C++20, `/Zc:__cplusplus`, `/MD`, `/O2` and `/fp:precise`. `FLM_USE_HRX` must remain undefined. The inherited XRT `DISABLE_ABI_CHECK=1` flag does not prove general C++ ABI compatibility. Static payload-import checks also do not establish complete Windows API-set closure or behavioral ABI compatibility.

Native construction, compilation, invocation and resource ownership belong to the existing controlled runner. Nothing is built or invoked on Python import. Models, proprietary runtime binaries, input captures and native outputs are not included here. Import-linked DLLs can load before `main`, even for `--help`; `--run` is not a no-load safety boundary.

The executable interface is:

```text
stateful1012.exe --run reference MODEL_DIR BUNDLE_ROOT INPUT.json REFERENCE.json

stateful1012.exe --run scenario MODEL_DIR BUNDLE_ROOT INPUT.json SCENARIO.json
```

Run fresh processes sequentially, using the same pinned input and unique outputs. Require 22 GiB physical/commit headroom before entry and retain 18 GiB during execution. Use the owned-child deadline and cleanup controls; do not automatically repeat a failed run. Keep the normal GPU server ready afterwards.

Both modes seed 512 authoritative tail IDs and commit 128 recorded target IDs through local context 640. The scenario creates a library-owned state, saves with `kv_from=0`, proposes up to three IDs, consumes at most two speculative inputs, restores the entire snapshot and appends only the true next target ID. Owned logits are restored separately. The state is freed through the same API before engine destruction. Forced fixtures at steps 0/15/16 test zero/partial/full agreement; they are excluded from prediction-quality scope. Every branch, including the full-match fixture, restores: retained-success optimization is not implemented or qualified.

The state API's byte counts are estimates. Forward timings include native processing and CPU logits ownership/argmax. State read/write intervals and row-file writes are separate. None is measured Halogen tok/s or arrival before target demand.

## Offline comparison

```powershell
python -B scripts/benchmarks/halogen_flm_stateful_replay/stateful_tools.py --compare REFERENCE.json SCENARIO.json --output FRESH_COMPARISON.json
```

Each report must have its adjacent `.rows` directory with 129 complete 248,070-value BF16 snapshots. The comparator checks all values under the original zero-different-word criterion, reconstructs greedy IDs, reconciles natural next-ID counts and validates state read/speculation/restore/append ordering. A mismatch remains a failed comparison; no tolerance is widened.

## Measured source provenance

The canonical C++ file and tests are byte-identical to the measured private preparation. The comparator differs only at `ROOT=HERE.parents[4]` → `ROOT=HERE.parents[2]`, locating this repository from the public package. Normalized AST equality confirms that all validation and comparison behavior remains unchanged.

| Artifact | SHA256 |
| --- | --- |
| Measured and canonical `stateful_host.cpp` | `3f1eeebf6984853a98e8c37cd31dba5f082ef403838cb46bede0b8564250518d` |
| Canonical `stateful_tools.py` | `e9b5aa3792d7e8745f8b1e8a2ad3a313efb92519434a53189e7d79932fb05900` |
| Measured and canonical `test_stateful_tools.py` | `529f529868ecb7847af0e8673c9e194315cd62f41c8c4407c443aa0793d9a100` |
| Retained measured private `stateful1012.exe` | `bf86ea460a6188e02fd81baaf009c9924c34c8069328ec1d36d25d469ea03336` |

No native rebuild or replay was performed for this relocation. Exact provider identities, component costs, state-size estimates, forced/natural scopes and limitations are retained in the [numeric result](../../../docs/benchmarks/halogen0201-stateful-npu-20261111.json). Offline 66/128 next-ID agreement is not native MTP acceptance. Full-engine gain remains unmeasured.
