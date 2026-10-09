# Independent source inspection record

Date: 2026-10-09. Scope: `validator.hip` and `oracle.c` only. The independent
reviewer `/root/normal0173_speed_scope/validation_semantics_review` supplied these
findings in messages; the source implementer recorded them here. This is an
inspection record, not a build or execution result. The reviewer performed no
builds, execution, or writes. `host.c` and `build.py` are outside this review.

No source compile blocker, scan/reduction race, aggregate-mask discrepancy,
fixture-name mismatch, or ABI defect was found by inspection.

- The parallel histogram scan reads all previous-level values before its
  barrier, then writes and reaches another barrier. The reductions are also
  synchronized. Sanitized `uint64_t` row arithmetic avoids signed overflow.
- The C-compatible 32-byte result layout and exported C kernel names look sound.
- All 50 fixture enum entries, names, and expected outcomes align. Accepted
  segment counts are sparse 1282, uniform 1536, maximum skew 1784, and final
  single expert 1280. Sparse arithmetic is `1+1+2+2+2+3+1271 = 1282`.
- The retained capacity is 1792, but the valid histogram maximum is 1784. The
  capacity fixture uses 512 x 193, sum 98816 and segments 2048; it checks capacity
  rejection alongside a failing sum. It does not represent a reachable
  independent capacity rejection after the other histogram predicates pass.
- Aggregate masks can contain more diagnostics than legacy short-circuit
  evaluation. Accepted/rejected equivalence concerns readable finite input
  arrays, not identical failure ordering.

The reviewer identified these contract limits, all reflected in `design.md`:

- Post-stage equivalence requires expected counts from an accepted histogram.
  `BN64_BAD_EXPECTED` differs from legacy for arbitrary expected arguments.
- The kernels check grid/block geometry. The host must enforce dynamic shared
  memory 0 and stream `NULL`.
- Fixed guard fixtures check first, middle, and last bytes. They cover
  boundaries, not every one of 16384 corruption positions or all thread
  residues. The post kernel's loop reads every guard byte.
- Native histogram input allocation lifetime and fixed extents need proof
  before future engine integration. Nonnull checks do not prove readability.
  GPU dereference of unreadable/stale input may differ from a failing legacy
  `hipMemcpy`; no pointer-fault or HIP-error equivalence was qualified.

No source changes were requested by this inspection. Compilation, CPU/GPU
validation, timing, error-path qualification, and live integration remain
root-owned work.
