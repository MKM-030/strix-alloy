# Experimental native Windows rank-table readers

This is an additional, default-off performance candidate for the already qualified native Windows Hipfire port. Root completed its CPU fixtures and real product-crate compile check; no enabled full-engine cohort has run. The preparing agents made no hardware or model calls. Gemma's current service is not changed.

The deployed baseline is `hipfire 0.4.3 (ddee82c74649; detached)` with the offered-draft counter patch and the existing eleven-file Windows port. Its warm Natural16K cohort averaged 1,240.2 pipeline prefill and 26.53 MTP decode tok/s. The public latest release checked on 2026-10-19 remains [v0.4.2.1](https://github.com/warpfront/hipfire/releases/tag/v0.4.2.1), published October 14; replacing this October 17 beta with that release is not a demonstrated speed update. The existing native rank/ABI/memory port needs no compatibility rewrite.

## Candidate and evidence

The rank store currently owns one synchronous `std::fs::File`. Its existing 16-to-256 scoped row-reader threads all call `seek_read` through that file object. Microsoft documents that synchronous file-object I/O is serialized across threads. Rust 1.99.1 routes this operation through `Handle::synchronous_read` and `NtReadFile` with an explicit offset. Offsets preserve byte correctness while sharing the kernel synchronization object.

The candidate gives concurrent rank reads independently reopened synchronous file objects. [ReOpenFile](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-reopenfile) operates from the existing open handle. Microsoft's [file-object explanation](https://devblogs.microsoft.com/oldnewthing/20140711-00/?p=523) confirms that it creates independent file position and synchronization while referring to the same underlying file. This avoids reopening a potentially renamed or replaced pathname. `DuplicateHandle` and `File::try_clone` do not provide this separation.

No retained native cohort contains `ple fetch:` or `ple_wait` timing. The saved final cohort uses the requested 8,192-row chunk, fully resident experts, warm file cache and no background PLE worker. The serialization mechanism is established from source and OS semantics; its contribution to actual prefill or decode time is unknown. The first tile may wait on PLE reads; later lookahead can overlap them with GPU work. Summing fetch durations would therefore overstate a possible engine gain.

Primary references:

- [Microsoft synchronous file-object serialization](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/nf-ntifs-ntcreatefile)
- [Rust 1.99.1 Windows file implementation](https://github.com/rust-lang/rust/blob/1.99.1/library/std/src/sys/fs/windows.rs)
- [Rust 1.99.1 synchronous read implementation](https://github.com/rust-lang/rust/blob/1.99.1/library/std/src/sys/pal/windows/handle.rs)

Do not add `FILE_FLAG_OVERLAPPED` while retaining `seek_read`: this Rust implementation requires a synchronous handle and can abort if its operation remains pending. This candidate uses neither overlapped I/O nor a new asynchronous framework.

## Configuration and ownership

`HIPFIRE_WINDOWS_PLE_READERS` is read exactly once by each rank-table `open_table` call, before the embedded rank is read.

- Unset or numeric `1`: retain the original `File` and exact existing read path. No file is reopened and no pool lease or lock is taken for a read.
- Numeric `2` through `64`: eagerly create exactly that many independent synchronous read-only file objects using `ReOpenFile`. The existing anchor remains open, so the handle ceiling is the selected reader count plus one anchor.
- Empty, non-Unicode, signed, whitespace-containing, non-decimal, zero or greater-than-64 values: fail model admission with the actual startup error. Leading zeroes are accepted as decimal values. The candidate does not silently substitute a valid value.

Reopened access is `GENERIC_READ`; sharing is the existing standard-file-compatible `FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE`. Flags are zero. This preserves buffered reads and avoids combining a cache-hint experiment with the concurrency experiment; `FILE_FLAG_RANDOM_ACCESS` is supported but is not added here. No write, no-buffering, POSIX, mmap, GPU or private API is introduced.

The bounded pool owns all reopened `File` values. Each `read_pack` first performs its original range check, then leases one file for the full existing exact-read loop, including interrupted or partial reads. The pool mutex is held only while checking a file out or returning it; synchronous I/O runs after the lock is released. A condition variable bounds concurrency when existing scoped threads outnumber pool entries. RAII returns the file after success, error or unwinding. Dropping the store closes its idle file objects; the normal borrowed store lifetime prevents it from being dropped while a read lease exists.

All rank/header/hash checks, offsets, 90-byte Q4LM rows, 16 KiB run coalescing, decode arithmetic, cancellation points and existing exact-read EOF/overflow behavior remain in the product. The module supplies ownership only. The non-Linux nowait path still reports `WouldBlock`; Unix source and cache workers are unchanged. The experimental raw environment value is not a new TOML key. The normal launcher clears unrelated HIPFIRE overrides, so a root-owned experiment must explicitly pass it to the candidate daemon; no launcher is changed to enable it.

## Exact apply scope

`windows-rank-readers-ddee82.patch` applies **after** `native-windows-ddee82.patch` and the offered-draft counter patch, against the already qualified source. It modifies only `crates/hipfire-runtime/src/ple_hot_store.rs` and adds `crates/hipfire-runtime/src/windows_rank_readers.rs`. The added module is byte-identical to the standalone `windows_rank_readers.rs` in this directory. It is imported only under `cfg(windows)`.

The required pre-patch `ple_hot_store.rs` SHA256 is `0b3598c99890d89041bfb8db37a5cf02b989245c3b95e5fdad098e74f22fdb86`. Verify this pin before applying, and use `git apply --check` on the root-selected isolated source copy. This is not a patch for pristine ddee82, the v0.4.2.1 release, arbitrary upstream master, or the retained E: source in place.

The normal eleven-file patch, its manifest, `Start.ps1` and `Build.ps1` remain unchanged. The normal wrapper performs its own fixed source checks and immediately builds; it does not apply this extra patch. Root must use a separate isolated source/build/output path for this experiment. Do not edit the normal manifest to admit the candidate or replace normal binaries with its output.

## CPU verification handoff

`standalone.rs` imports the same module and uses only Rust standard-library code plus the module's explicit Kernel32 link. It refuses compilation on non-Windows. Its fixtures generate small temporary files; they do not read model files, load HIP, allocate GPU memory, query providers or start a server. The checks cover strict bounds/default parsing, the exact original handle at count one, independent cursors, same-file identity after a rename and pathname replacement, concurrent byte-correct reads with bounded leases, EOF/read-error recovery, and lease return on unwinding. Concurrency assertions concern ownership and byte correctness, not timing or a fabricated token rate.

Root compiled the fixture with the installed Rust1.99.1 x64/MSVC toolchain using `rustc --edition=2021 --test standalone.rs`, then ran it with `--test-threads=1`. All four tests passed. A separate offline `cargo check --release --locked --offline --target x86_64-pc-windows-msvc -p hipfire-runtime --lib --jobs 2` passed against an isolated copy with the product patch applied. No inference target was executed. [Source pins, commands and observed memory reserve](verification-20261019.json) retain the results and the corrected staging-only failure before Cargo started. The original source and current Gemma run remained unchanged. No prefill, decode or acceptance value follows from these CPU checks.

On the isolated product copy, retain the existing CPU cases under `ple_hot_store::portable_table_tests`, including partial EOF/error offsets/overflow, concurrent exact rank bytes and invalid rank/truncation, plus `external_rows::tests::rank_ordered_table_store_decodes_like_row_ordered_descriptors`. Later native product checks must exercise count 1 and a selected enabled count in separate processes so the once-at-open environment semantics are respected. No GPU-labelled tests are required to establish this module's file ownership.

Only a later root-owned full-engine A/B on the same frozen workload can establish prefill/decode benefit. Keep model/PLE bytes, MTP K2, n-grams off, inline-q8, sequence capacity, cache/reset semantics and host reserve rules fixed. The existing `HIPFIRE_PLE_HOT_DEBUG=1` can expose large-fetch rows/read counts and elapsed time for diagnosis; those trace times are not pure I/O or exposed `ple_wait` and are not throughput evidence. A CPU concurrency result cannot justify serving promotion or synthetic tok/s conversion.
