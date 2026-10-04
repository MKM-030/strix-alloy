# ROCr idle polling candidate — 5 October 2026

Two threads in the preserved Halogen engine each consumed approximately one
CPU core during a separate 167.634579-second idle interval. The exact installed
HSA library has the no-event polling loop without AMD's merged backoff. A
narrow backport is prepared against its exact source pin. No private library
has yet been built or loaded, and no token-rate gain is claimed.

The normal frozen control measured **1253.224684 prefill / 42.418748 MTP decode
tok/s / 60.0% acceptance**, at 8192 actual input and 128 output tokens. Its
[CPU/paging report](halogen-cpu-paging-control-20261005.md) records zero engine
`read_bytes`/`rchar`, engine major-fault and swap deltas in those request
bookend intervals. The idle observation is distinct from inference and
does not establish the cause of the historical throughput gap.

## Exact installed provenance

- HSA SHA256: `1961df7d395b62d9b7c0086e0a247a02d0e97129eb9d8b28acb0e0a597e819f5`;
  4,887,129 bytes; SONAME `libhsa-runtime64.so.1`.
- ROCm SDK 7.14.0; TheRock commit
  `418cd5f63abb7a604bad5874cd7b2e29334e640f`.
- Unpatched rocm-systems source pin
  `2b22ab0195cc1461cd9abf3b969e9dd7c10af350`.
- `AsyncEventsLoop` starts at ELF RVA `0x112510`, size `0x162f`.
  Its unfinished no-event path at `0x1132dc` jumps directly to another scan at
  `0x112aa1`, with no sleep or yield. A separate vtable relocation identifies
  `BusyWaitSignal::EopEvent`, which returns a null event.

These are source and static binary findings. The live hot threads were not
attributed through instruction pointers or stack sampling.

## Prepared intervention and bounds

The [official AMD fix](https://github.com/ROCm/rocm-systems/pull/7898), merge
`46558b7af4dc79b8b8014619c1afdb82db079a9f`, adds a polling nap from 20 us,
doubling to a 2-ms ceiling when interrupts are globally unavailable and a
200-us ceiling for mixed interrupt-capable batches. It resets for each new
wait batch and leaves the separate kernel-completion BusyWaitSignal path
unchanged. The linked [WSL issue](https://github.com/ROCm/librocdxg/issues/60)
is supporting upstream evidence, not a measurement on this machine.

The retained [backport patch](../../scripts/benchmarks/patches/rocr-2b22ab0-async-poll-backoff.patch)
adds only three insertion sites to the pinned runtime plus the official
56-line helper: two files, 93 added lines. Its SHA256 is
`ead910aaf82bb7ace5bf59ad288f4ae5d620feefa32d594221832878de93f745`.
`git apply --check` passes against the freshly fetched source; no application
to installed source or library occurred.

The root-owned [source fetcher](../../scripts/benchmarks/halogen_rocr_private_source_fetch.py)
completed 436 files / 8,573,428 bytes, excluding the unused test trees. Every
payload matched its pinned Git blob SHA and extent. The six-worker download
finished in 66.96 seconds with exit 0, all owned jobs closed, monitor stopped,
and no cleanup pending. Physical reserve stayed at least 27.451530 GiB and
commit headroom at least 119.906799 GiB. Raw source and receipts remain in the
ignored private directory; they contain no model payload.

The [small component probe and plan](../../scripts/benchmarks/halogen_rocr_poll_backoff_probe.md)
are prepared offline. Qualification requires installed stock, source-built
stock and patched candidate in the same pinned image. Source stock and the
candidate must use the same compiler, dependency bytes and flags; only their
comparison isolates the patch. The original static hsakmt graph and dynamic
WSL bridge must remain intact. SDK compiler and bundled sysdeps are preferred
over changing installed runtime or driver components.

The necessary checks are actual loaded-library hashes, unchanged original RMS
BF16 outputs, bounded kernel latency, idle CPU, callback progress, ABI and
dependency compatibility. Any later live token-rate comparison needs its own
admitted engine window. A 2-ms polling ceiling can add callback observation
latency; reduced idle CPU alone is insufficient to claim faster decode.

The colleague server remains open, with native GPU prefill/MTP and no NPU/cache
candidate loaded. No driver, BIOS, voltage or global WSL setting changed. The
full optimization goal remains active.
