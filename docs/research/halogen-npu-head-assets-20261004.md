# Bounded v2 head assets: CPU preparation evidence

The reusable q8g64 reader and the new HT reader now allow streamed preparation
of attention/HC and shared vocabulary weights without materializing complete
matrices. The head exporter resolves HT `lm_head.suh` and `lm_head.svh` from
the cryptographically bound full tensor table. It never substitutes the input
embedding for the output head.

This is **CPU asset preparation**, not an NPU provider, a complete MTP head,
or a live acceptance/speed result. HT decoding matches the recovered 0.15.0
NumPy reference; equivalence to the current 0.16.2 engine remains unproved.

## Completed bounded real reads

After the regular 8K GPU matrix completed with normal cleanup, root verified
stopped engines, free API ports and at least 22 GiB physical/commit headroom.
Only root opened the existing v2 checkpoint for this asset window. Both
metadata-only prepared plans were independently hashed before extraction.

| Selection | Selected source payload | FP32 output | Output SHA256 |
|---|---:|---:|---|
| Attention Q, rows 4–7 | 10880 B | 40960 B | `9e12f8916b7610e326782d14cc1b8a53ee40533c9b628e28281956310eac6c7c` |
| HT lm-head, rows 128–255 | 169216 B | 1310720 B | `c65148b577e38bbc8a0aa4d6a859a1f5c123f11c28da5e182a73ec9c5865a1ff` |

The HT source total is one 163840-byte packed group, the 5120-byte complete
input-sign vector, and 256 bytes of selected output scales. All decoded values
were finite. Native checkpoint identity, metadata/header/table hashes, reader
sources and lineage receipts remained unchanged. Final file sizes and hashes
were independently checked against receipts; writer locks and partial files
were absent. Minimum observed physical availability was 50.251 GiB; minimum
commit headroom was 208.114 GiB.

Local artifacts remain under
`C:\AI\halogen-mtp-npu\v2-head-assets-20261004-postreboot`.
Prepared-plan SHA256 values:

- Q rows: `3bd11b076d6964bc523468aa5e51be269cb4b9f192b0eed4fd4cae905480b5ee`.
- HT rows: `83f5268efc74afd2459800394125b284e7748a73b06db760b5d0567f1fbab4e7`.

## Retained implementation and checks

`scripts/benchmarks/hgn_q8g64_slice.py` exposes bounded `decode_rows()` without
running its CLI at import. `hgn_ht_slice.py` reads complete aligned 128-row
groups, finite signed output scales and +/-1 input signs, with a 64-MiB output
cap. Its Apache-2.0 license and attribution accompany the adapted source.

`halogen_npu_v2_head_assets.py` requires explicit tensor selections and defaults
to a 256-MiB total output cap, 8-MiB tiles and 64-MiB estimated workspace. HT
tiles are rounded down to multiples of 128 rows. Its scratch estimate includes
the tile, selected source bytes, twelve group-sized FP32 scratch arrays and
8 MiB of cached-table/library allowance. Source pins include the HT decoder,
NOTICE and LICENSE. A sealed plan, unchanged lineage and verified source
identity are required before reading payload; only verified output receives a
final data name and completion receipt.

Nine focused HT fixture checks passed, including an exact independent
decoder-AST comparison for a 256×256 matrix and its second 128-row group.
Two exporter/q8 fixture checks passed, covering nonzero Q8 rows and HT planning,
decoding, source ranges and the older reference hash. BLAS thread count was one.
Independent source reviews passed; a scratch-budget concern was corrected
before real extraction. No broad test suite or accelerator/provider execution
was performed in this step.

Reviewed exporter SHA256:
`582e292581cc85b06be9af86e82af5bdc694a6a277cfbc416ae7a11e3343a870`.
HT reader SHA256:
`4e0c72fdf63d8e1c12ed90c11f9400aa65ee3f531a9157a8257d6ebb899bd3c7`.

The complete NPU head still requires attention/history execution, native
numeric/state interpretation, routing/shared experts, vocabulary projection,
accepted-prefix state replay and a qualified target-verifier integration.
These extracted row subsets satisfy none of those live-runtime gates by
themselves. The full optimization goal remains active.
