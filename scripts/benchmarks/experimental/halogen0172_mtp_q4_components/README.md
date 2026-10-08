# Halogen 0.17.2 MTP Q4 component prototypes

These isolated experimental kernels are disabled in serving. They reconstruct
the pinned native Q4 computation with unchanged codebook rounding, BF16 dot2
order, FP16 scales, group FMAs and XOR reduction. No model payload, credentials,
native engine code object, or raw captured queries/logits are published here.

`query_lds.cpp` cooperatively stages the raw 5120-byte query in quarter-major
LDS. `query_lds_lut_batch.cpp` also batches the sixteen code-pair LUT loads.
Both require the explicit compilation define `HG0172_Q4_QUERY_LDS_ENABLE=1`.
`query_global_lut_batch.cpp` retains batched LUT reads but uses the original
raw query packs from global memory, with only the 1024-byte LUT in LDS. It
requires `HG0172_Q4_QUERY_GLOBAL_LUT_ENABLE=1`.
Their standalone symbols and resource metadata differ from the original
descriptor; none can replace the native registration without a separate
reviewed integration.

`component_host.c` compares the first symbol against the original native module
on the retained private partial asset: 15 heads, 32033 core and 2538 tail rows.
The batched comparison changed only `CANDIDATE_SYMBOL` to
`halogen0172_q4_query_lut_batch_v1`; the direct-query comparison uses
`halogen0172_q4_query_global_lut_batch_v1`. Root independently verified source, module
and input hashes. The input directory must contain exactly `blob.bin` and the
30 fixed query/logit files. Its packed input preserves all native values and
row strides but does not reproduce the live engine's allocation/cache layout.

Each head has one excluded warmup and three alternating AB/BA measurements.
GPU events include both projection launches, LUT/query preparation and the
barrier. File I/O, initial module setup, H2D copies and output readback are
outside those brackets. Every row is checked bitwise on every warmup and
measurement. Guards and resource cleanup are checked; no tolerance is relaxed.

The Windows device-only build used the installed TheRock SDK
`therock1151-10.2.0a20260930`, gfx1151, code object v6, `-O3 -fno-fast-math
-ffp-contract=off`, and its explicit `lib/llvm/amdgcn/bitcode` path. Root reviewed
the unbundled ELF metadata, descriptor FP modes and emitted instructions.
The C host was compiled with `gcc -std=c11 -O2 -Wall -Wextra -Werror -ldl -lm`
inside the existing WSL environment and executed with a bounded lifetime in
the existing idle engine container. The stock server was preserved throughout.

Results and interpretation are in
`docs/research/halogen0172-mtp-q4-kernels-20261009.md` and its JSON evidence.
Component milliseconds are not engine token rates or MTP acceptance.
