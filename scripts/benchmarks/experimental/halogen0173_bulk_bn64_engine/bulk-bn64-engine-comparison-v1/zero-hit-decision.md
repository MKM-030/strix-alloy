# V1 zero-hit diagnosis and bounded v2 mechanism

2026-10-09. Source-only review of retained artifacts. No hardware, API, lifecycle, build, test, analyzer execution or sealed-file edit was performed by this scope.

## Observation and disposition

The full four-request candidate window completed, but both `candidate-audit-before.jsonl` and `candidate-audit-after.jsonl` contain only `enabled_pinned_0173` followed by `process_summary`, with started/committed/rejected/rolled_back/failures all zero. The process summary already existed before warmup while the serving engine remained alive. The candidate manifest opted in with the readonly adapter mount and this preload chain:

`/candidate/libhalogen0173-v2-preflight.so:/candidate/hip-register-private-rw.so:/candidate/libbulk-bn64.so`.

These records do not qualify an active native64 engine comparison. Visible output/acceptance parity and the candidate-labelled native rates cannot demonstrate a BN64 effect when no transaction was observed. Preserve the completed v1 window; do not repeat it to manufacture hits.

## Exact source mechanism

The actual generated entrypoint is `backends/halogen-wsl2-0.17.3/.local/services/69d90663906b45bab8a0b3fffb0f7789/entrypoint-service.sh`. Its source order is:

1. `all` mode calls `need_ckpt` at line1411.
2. `need_ckpt` calls `check_sidecar` and `check_ngram_table` at lines565/567. `check_sidecar` and `check_ngram_table` invoke `ckpt_facts`.
3. `ckpt_facts` executes `${_hg_flash_serve:-/usr/local/bin/flash_serve} --resident-gib "$HALOGEN_CHECKPOINT"` at line492. This is a short query using the same pinned executable as serving.
4. Only afterward does `all` mode start the long-lived engine with first argument `--ck` at line1415.

Docker's candidate environment applies to the entrypoint and is inherited by the resident query. That query has no `env -u` removal. For actual serving, `ENGINE_ENV_U` at lines925..934 removes only the listed front-end HALOGEN flags; it leaves `LD_PRELOAD`, `ALLOY_BULK_BN64_ENABLE` and `ALLOY_BULK_BN64_LOG` present. The manifest and launcher therefore supply both helper and serving processes with the same exclusive `/tmp/alloy-bulk-bn64.jsonl` path.

V1 `initialize()` requires the exact `/usr/local/bin/flash_serve` executable and its exact engine/object hashes before opening the log with `O_CREAT|O_EXCL`. Thus API Python, the shell and the lease supervisor cannot create the enabled record. The earlier pinned `--resident-gib` helper can enable the adapter, claim the log and emit its destructor summary without any HIP launch. The later `--ck` serving process encounters the existing log, its `open()` fails, and it leaves `configured=0`. In that state the registration and launch wrappers pass through; the rejected counter also stays zero. This explains the observed two-row audit without requiring an incorrect native descriptor, caller pin or module-launch hypothesis.

The existing stock event review (`../gpu-event-attribution-20261009/runtime-evidence-review.md`) records ordinary `hipLaunchKernel` calls, no module-launch records, and bulk GU/DN native paths. The 0.17.3 inert host map likewise pins direct `hipLaunchKernel@plt` calls. Source inspection finds no `hipLaunchKernel` or `__hipRegisterFunction` export in the earlier preflight/private-RW source layers. These are supporting facts; this zero-hit log is not a live symbol-binding trace. The log itself has no PID/argv, so identifying the completed helper remains a source-supported diagnosis rather than a PID-tagged runtime capture.

## Minimal separate v2 source

Root authorized `../bulk-bn64-engine-candidate-v2-resident-fix/`, preserving sealed v1 originals. V2 adapter SHA256 is `714b90cf716a0ed2b82deb949394ff4154798a0fadd6c421c39aadd7e3c8c24d` (19006 bytes), derived from v1 SHA256 `1168a01f8ffd7346f6b63144b4b1f28e8801c15bc84ecaa56c5364961dba7da7`.

The only adapter delta is a bounded128-byte `/proc/self/cmdline` reader and a constructor skip for exact argv[1] `--resident-gib`, including the terminating NUL. The skip occurs after existing opt-in/executable checks and before hashes, log claim or configured state. Actual serving argv[1] is `--ck`; unknown or unreadable arguments retain v1 behavior. Every serving hash/RVA/descriptor/ABI/capacity/guard/rollback instruction remains unchanged. No new kernel or memory admission gate is introduced. `constructor-delta.patch` records the complete source diff.

An independent read-only constructor review found no outstanding source defect and wrote `../bulk-bn64-engine-candidate-v2-resident-fix/independent-resident-skip-review.md`, SHA256 `19fc71eefd285b457c4ffe4a2d83e0e2b1b671e1176ad8555aa70e562c379824`. V1 source/map/review/README originals were checked byte-unchanged when copying. Root owns any v2 build and engine trial; this source change supplies no execution, numerical or gain claim. The existing restored stock after window can serve as the next before reference under root's decision, without an unnecessary repeated before cohort.
