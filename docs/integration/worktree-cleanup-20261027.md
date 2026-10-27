# Physical Strix Alloy cleanup, 27 October 2026

The [source consolidation](worktree-consolidation-20261027.md) initially kept
secondary directories for their local runtime data. This follow-up performs
physical cleanup after preservation and dependency checks.

## Retired checkouts and snapshots

Eleven old validation/export directories under `C:\Projects`, the independent
`E:\Projects\strix-alloy-clean` clone, and the October 18 snapshot directory
under `E:\strix-alloy` were removed. Their exact paths and evidence are recorded
in the companion cleanup JSON.

The removed directories contained 24,081 files and 1,289,730,968 logical bytes.
New, access-restricted preservation archives occupy 75,152,813 bytes on E:.
Every archived file was read back and verified by SHA-256. The E: clone's
633 ignored files matched the primary checkout exactly; its 179 additional
runtime/build/license files matched the existing verified backup ZIP.

Immediately around this removal, available space increased by 240,427,008
bytes on C: and 1,106,415,616 bytes on E: (about 1.25 GiB combined). These are
volume snapshots taken after archive creation; they include filesystem
allocation effects and can also reflect concurrent system writes. They are
separate from logical file sizes and net savings after preservation.

All targets were resolved against an explicit whitelist before deletion.
No reparse points were followed. A separate process/cwd/mapped-module audit
and Windows Restart Manager resource census found no users of the retired
clone and validation files. Source hashes and backup availability were
verified again immediately before native PowerShell removal.

## Voice runtime migration

The SCC Voice worktree had become active again after the initial source push.
It contained four later modified source files and a new native CPU-ASR adapter.
ASR, Bot and Native processes used its cwd, logs and Python dependencies, so
it was explicitly excluded from the first removal pass.

Those source changes were preserved in `9cda2df` and merged in `da45feb`.
Canonical Primary startup and portable regressions are committed in
`01a9233`: duplicate startup locks are avoided and native ASR gets the same
child-local fused-QKV setting on normal startup. Primary core code stays
unchanged; the old CRLF and current LF copies have identical normalized
source and AST. The full Voice test directory passes 152 tests and 36
subtests without loading a model or calling external services; HTTP fixtures
use isolated local test endpoints.

The staged Primary environment contains all 64 original distributions.
Only 6,647 previously absent files were copied (282,097,003 bytes), with
source/target hashes checked. A bounded, isolated import gate completed
without Product-path fallback, model calls, network or service operations.
The controlled cutover completed with three new, creation-identity-bound
Primary workers. Halogen and the selected TTS generation stayed unchanged.
The Native public path temporarily returned a maintenance response; all other
Funnel routes were preserved and the complete original configuration was
restored. The temporary guard exited. A further 54 pure executor tests and
188 subtests passed before the real cutover.

After the separate live release and independent dependency audit, the complete
retired Voice directory was archived: 24,114 files, 794,736,706 logical bytes,
269,579,101 ZIP bytes. Every file was read back and hash-verified. The retired
directory was then physically removed and its stale Git worktree registration
pruned. Only `C:\Projects\strix-alloy-clean` remains in `git worktree list`.
The existing relay executable was preserved under its Primary runtime path
without executing it. The desktop startup shortcut now targets Primary.
The obsolete path in the disabled retention task was rebound; the task stayed
disabled and was never run.

One preclaim validation stopped before route/service changes because a frozen
source-install receipt had later gained a publication field. Its exact original
bytes were restored; the publishing revision was retained separately. A fresh
explicitly authorized allocation performed the cutover. Failed preclaim
history and consumed staging/import evidence were preserved; no benchmark,
audio request or business action was replayed.

## Current measurements

The latest qualified Halogen engine measurements remain the
[26 October 8K/16K cohort](../benchmarks/halogen01816-natural-8k16k-20261026-evening.md).
RAW prefill/decode means are 2033.12/56.93 tok/s at 8192 actual input tokens
and 2002.08/49.63 at 16384, with 66.04%/52.68% native draft acceptance.
The report retains the separate 8K native API values, 1876.97/52.47 tok/s.
The later 72-request policy campaign promoted no replacement configuration.

The claim ledger, benchmark guide and historical journals now point to those
current results. The separate
[27 October CPU-ASR component report](../local-voice/native-asr-component-20261027.md)
records its one C-ABI fixture and one synthetic speech roundtrip; these are
not LLM prefill/decode rates or a measured NPU speedup. No performance cohort
was repeated for cleanup.

## Retained data and final checks

Models, selected voice data, drivers, firmware, BIOS, voltages and global WSL
settings are preserved. The primary checkout, separate WSL2 repository,
historical research artifacts and unrelated Hipfire directories remain.
Two stale Codex attachment directories contain only zero-byte name markers;
the app reported ownership by another task and they were not removed through
a filesystem workaround. They contain no remaining Git worktree or source.

In total, 14 directories and 48,195 files (2,084,467,674 logical bytes) were
removed. New preservation ZIPs occupy 344,731,914 bytes on E:, with their hash
manifests and maintenance-task backups alongside them. Actual free-space
snapshots after preservation and runtime migration are in the
[cleanup JSON](worktree-cleanup-20261027.json); background system writes mean
they are observations rather than exact per-file allocation attribution.
Compared with task-entry snapshots, the observed net increase is 714,768,384
bytes on C: and 751,288,320 bytes on E:, about **1.365 GiB combined**, after
the new archives and Primary dependency copies.

Post-removal read-only checks confirm Primary ASR/Native readiness and the
same healthy Halogen 0.18.16 and TTS generations. All six old Voice worker and
redirector generations are gone; a 24,114-file Restart Manager census found
no resource users before deletion. Source and documentation are published
through normal `origin/main` updates. Existing models and voice assets remain
available. Full iPhone/SDK/business-call qualification and the separate LLM
acceleration objective are not claimed by this cleanup.
