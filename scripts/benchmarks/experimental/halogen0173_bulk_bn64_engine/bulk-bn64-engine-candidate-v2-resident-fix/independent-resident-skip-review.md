# Independent v2 resident-query constructor review

Reviewed 2026-10-09 by `/root/prefill_new_mechanism_scope/window_inventory_review` at root's request. This receipt covers only the source delta excluding the entrypoint's resident-size query from adapter activation. Root owns compilation, hardware, APIs, lifecycle and the next engine cohort.

- Reviewed v2 source: `adapter.c`, 19006 bytes, SHA256 `714b90cf716a0ed2b82deb949394ff4154798a0fadd6c421c39aadd7e3c8c24d`.
- Compared sealed v1 source: `../bulk-bn64-engine-candidate-v1/adapter.c`, SHA256 `1168a01f8ffd7346f6b63144b4b1f28e8801c15bc84ecaa56c5364961dba7da7`.
- A complete source diff contains only the new `resident_query()` helper and its early call in `initialize()`.

The retained 0.17.3 adapted entrypoint invokes `${_hg_flash_serve:-/usr/local/bin/flash_serve} --resident-gib "$HALOGEN_CHECKPOINT"` in `ckpt_facts()` (`backends/halogen-wsl2-0.17.3/.local/entrypoint-wsl.sh`, line 492). The new guard matches that exact first argument. It locates argv[0]'s NUL in a bounded 128-byte read of `/proc/self/cmdline`, then compares argv[1] against the complete `--resident-gib` string including its terminating NUL. Similar prefixes and suffixed arguments do not match. Later checkpoint arguments need not fit the buffer once this complete argument is present.

The positive read length bounds `memchr`; the located NUL makes `used` no greater than the bytes read; and the remaining-length check precedes `memcmp`. Open/read failures, empty reads and incomplete argv[0] or argv[1] leave the previous constructor path in place. Interrupted reads are retried, the temporary descriptor is closed, and `initialize()` restores its saved errno on either path. No command-line contents are printed or logged.

The skip follows the existing exact opt-in and executable-path checks and precedes both executable/object hashing and exclusive audit-log creation. Therefore this recognized query leaves `configured` false and `fd`/`memfd` at their initial -1 values; it cannot claim the serving process's audit log or emit a process summary into it. The normal `--ck` serving invocation retains the prior hash checks and activation sequence.

Registration, launch eligibility, host ABI, allocations, guards, memory-copy checks, transaction rollback and teardown code are unchanged from sealed v1. The prior bounded ABI/transaction review remains evidence for those unchanged sections; this review does not establish compilation or runtime activation.

Conclusion: no outstanding concrete source finding in the reviewed constructor delta. The source addresses the identified resident-query log-claim mechanism and is ready for root's build and runtime verification. No source edits, imports, tests, builds, APIs, process/GPU queries or lifecycle actions were performed by this reviewer; only this receipt was added to the new v2 directory.
