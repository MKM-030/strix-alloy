# Strix Alloy consolidation, 27 October 2026

The primary integration directory is `C:\Projects\strix-alloy-clean`, branch
`main`, remote `MKM-030/strix-alloy`. This consolidation preserves source and
development history from the primary directory, SCC Voice and the older E:
checkout. It does not promote experimental kernels or NPU paths.

## Inventory and preservation

| Location | Initial state | Integration |
| --- | --- | --- |
| `C:\Projects\strix-alloy-clean` | `e3ec21a`; local Halogen, controller and Voice changes | Source/evidence checkpoint `24a7aea`; source-pin documentation correction `96dda1d` |
| `C:\Projects\strix-alloy-scc-voice` | `0e3005f`; 61 commits outside primary plus local source/tests/docs | Checkpoint `1ff829d`, merged in `b7794e9` |
| `E:\Projects\strix-alloy-clean` | `55bb4ff`; six changed tracked files and 206 untracked files | Source checkpoint `02616de`, merged in `77a8455` |
| `E:\strix-alloy\consolidation-20261018` | Five metadata-free development snapshots | Already covered by the [18 October consolidation](worktree-consolidation-20261018.md); no later source edits found |
| Codex `gpu-draft-snapshot` and `npu-ready-embedding` directories | Empty name-marker directories; no Git checkout | Their histories were integrated on 18 October |

Before integration, complete tracked/nonignored source snapshots and all Git
refs were saved in `E:\strix-alloy-consolidation-backups\20261027T070604Z`.
The private manifest records file sizes and SHA-256 hashes. Both Git bundles
were verified. These local backups are not repository dependencies.

All 27 untracked source/evidence files from the E: checkout already matched
the primary directory. Four of its six modified tracked files also matched;
the newer primary README and launcher already contained the remaining E:
changes. The E: merge therefore preserves history with an unchanged resulting
source tree. Its 175 runtime files, build identity and three license payloads
remain local and are backed up; binaries and machine-specific assets were not
added to the repository.

The October 18 archive contains 633 files across its five source snapshots:
610 match current primary files exactly, and the other 23 match the historical
checkpoint blobs. The separate `strix-alloy-wsl2` repository and third-party
Hipfire/REV-N repositories are different projects and were not merged here.

## Resolution and compatibility

The initial committed SCC Voice and primary changes since their shared
`af7845c` base touch separate files. Their local Voice overlays overlap. Review found the
newer SCC Voice versions preserve the primary fixes and extend the responsive
runtime, readiness admission, ICE handling and managed conversation lifecycle.
Those newer versions are retained; the earlier primary versions remain in
the preservation checkpoint.

Five conflicts were resolved in `Start-QueuedGateway.ps1`, `bridge.py`,
`core.py`, `native_bridge.py` and `sdk_sessions.py`. The reviewed newer Voice
versions retain the primary fixes. Native gateway profiles remain restricted
to authenticated, pinned loopback endpoints. The deliberate removal of the
historical gateway-level German override follows the
[Gemma migration contract](../local-voice/GEMMA-MIGRATION-DE.md): caller persona,
language, history and action instructions pass through unchanged.

A PCM sample counter defect found during review is corrected: an incomplete
sample split across network chunks must not cause question audio to appear
fully drained before the final sample is emitted. Three regressions cover
split chunks, actual question ownership and interruption between generations;
all failed before the fix and passed afterward. Existing native test fixtures
are updated for current imports, readiness dependencies and exact health DTOs.
Halogen tests also retain the supported-v2 rejection and the new Deferred-Z
module in their isolated AST namespace.

The backend source hash ledgers remain unchanged by documentation updates.
All 45 pinned 0.18.15 files and 44 pinned 0.18.16 files were verified. Installed
source packages retain their preparation/qualification flags; local measured
runtime evidence does not qualify an arbitrary new installation.

## Current usage and performance documentation

The [main README](../../README.md), [managed endpoint guide](../../server/README.md)
and [ServiceNow guide](../integrations/halogen-servicenow.md) now distinguish
the explicit 0.18.16 `MeasuredText32K` preset from the bare launcher's older
0.18.10 `Current4K` defaults. The measured text preset uses 32K capacity,
8K prefill chunk/arena, adaptive gate 0.90, PLD `3,3`, Cache Off, Thinking Off,
Vision Off and prefetch off. Console content tracing remains opt-in.

The [latest natural 8K/16K report](../benchmarks/halogen01816-natural-8k16k-20261026-evening.md)
retains its RAW/API clock caveat. RAW phase means are 2033.12 prefill / 56.93
decode tok/s at 8192 actual input tokens and 2002.08 / 49.63 at 16384, with
66.04% and 52.68% native head acceptance. At 8K the native API instead reports
1876.97 / 52.47 tok/s. No benchmark was repeated as part of consolidation.

The [native policy campaign](../benchmarks/halogen01816-native-policy-campaign-20261026.json)
contains 72 completed requests, 18 excluded warmups and 54 measured requests.
Neither confidence gate 0.95 nor 0.85 nor PLD `3,7` qualified for promotion.
The NPU and trained-proposal prototypes remain separate, unqualified source.

## Validation and final disposition

The source merge is `b7794e94854578137c887586f5391a065b1439fe`. No local branch
tip remains outside its history. Both secondary source checkouts were advanced
without rewriting history to this integrated source. Their local dependencies
and runtime payloads remain in place; no disk-space saving is claimed.

| Final validation | Result |
| --- | --- |
| Server and controller | 174 tests passed |
| Native Voice, isolated module runs | 905 tests across 62 modules passed; two real-VAD/model modules excluded |
| Voice bridge/client | 99 tests passed |
| Native start / additional start fixtures | 171 + 3 tests passed |
| Voice Studio | 124 tests, no failures, five platform/privilege skips |
| Voice profiles / optional Omni contracts | 19 + 39 tests passed |
| JavaScript / ServiceNow source contracts | 81 tests in 14 files passed |
| GUFO / retained Halogen controls | Broad run: 825 tests, initially three failures/eight errors; affected reruns: 124 tests with two skips and no remaining failures |
| Source pins / Git integrity / whitespace | 45 + 44 pins verified; connectivity and diff checks passed |

The broad GUFO failures were test environment/path assumptions: historical
sibling artifacts, the pinned installed interpreter versus a venv redirector,
child `PYTHONPATH` and actual guardian process identity. Production admission,
identity checks and hash pins were retained. The long unchanged finite-phase
suite was not repeated after test-only corrections. Six GUFO checks remain
excluded or unavailable: two Windows symlink privileges, one Linux compiler,
one WSL shell fixture and two transport tests that require the serving port
to be closed. PyTorch-dependent research tests and Go relay tests were not run
because those test toolchains are absent; no GPU/NPU cohort was run.

A transient Windows `OSError(22)` occurred while overwriting synthetic JSON in
the native-start fixture. The isolated test and subsequent complete diagnostic
and unmodified runs passed. Its cause is unconfirmed; no retry, skip or product
workaround was introduced. Studio retention tests now use their own temporary
runtime folder rather than the real completed-campaign marker. Three PCM
regressions and an independent 59,049-sequence counter invariant check passed.

Private models, credentials,
dependencies and runtime evidence remain outside Git. No driver, firmware,
BIOS, voltage or global WSL change is part of this consolidation. Physical
checkout removal and disk-space savings are reported separately from source
integration; retained runtime directories must not be treated as disposable
merely because their source history has been merged.

Authenticated read-only checks confirmed Halogen 0.18.16 API/engine agreement
and healthy 8840/8731 endpoints after the separate authorized normal restart.
The measured text profile remains online for ServiceNow. The full acceleration
objective remains unachieved. The repository publication is a normal update
of `origin/main`; the [machine-readable consolidation record](worktree-consolidation-20261027.json)
contains checkpoints, validation scope and backup hashes.
