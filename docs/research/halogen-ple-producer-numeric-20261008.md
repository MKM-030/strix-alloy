# PLE producer: actual weights and bounded numerical comparison

The original v2 checkpoint contains raw BF16 layer-1 PLE projections: key
`[10240,2560]` at byte 1700831936 (50 MiB), and value `[2560,2560]` at
1753322496 (12.5 MiB). Fresh original header and directory hashes bind their
names, extents, storage format and directory descriptors. The static CPU
decoder audit supports BF16 widening. The captured 120-byte runtime descriptors
contain pointers and bookkeeping, not those matrices. Full runtime alias/copy
lineage and full row order remain separate questions.

A bounded CPU probe compared eight frozen token rows and 64 distributed output
columns per branch against the captured original-GPU outputs. Input and weights
were widened to FP32, multiplied, then rounded to BF16 using round-to-nearest,
ties-to-even. The CPU tolerances stayed `rtol=0.002, atol=0.0002`.

| Projection | Values | Tolerance failures | Different BF16 words | Maximum absolute error |
|---|---:|---:|---:|---:|
| Key | 512 | 0 | 1 | 0.0000152587890625 |
| Value | 512 | 0 | 0 | 0 |

Interpreting the same raw weight words as FP16 failed every compared value in
both branches. The probe read 655,360 selected weight bytes and 245,760 native
input/oracle bytes. Its owned guard also checked complete frozen native tensor
hashes before and after the child. It did not reread the full 62.1 GiB checkpoint.
The child exited zero, the owned job closed, and minimum available physical and
commit memory were 25.227 and 114.932 GiB respectively.

The preserved first attempt failed before payload arithmetic because Windows
pathname `lstat` and opened-handle `fstat` report different `ctime` values for
this UNC file. V2 compares the retained handle identity with fresh `fstat` and
checks each API's own identity before/after. Every hash, identity field and
tolerance is preserved; no threshold was relaxed.

This is a numerical subset, not complete M8192 parity, NPU execution, an early
producer or a serving benchmark. Future NPU tolerance remains `rtol=0.03,
atol=0.003`. Full weight export and graph preparation are the next bounded CPU
step. No Prefill, Decode or acceptance improvement is claimed. The independent
decode audit found no new justified allocator or lookup-cache mechanism.

Fresh active-path verification confirms the authorized startup allowance of
35 GiB physical / 131 GiB commit for both installed versions. Runtime reserve
remains 18/18 GiB. Gateway, backend and visible console identities match the
saved server, and authenticated health is ready on port 8840. No restart or
inference request was needed for that verification. Starts above the configured
floor do not establish sufficiency at exactly 35 GiB.

The companion JSON pins the raw numerical result, execution and static
provenance receipts, failed first attempt, and current server verification.
