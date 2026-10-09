# native0.17.3 RAW phase clock source archive — revision 2

This is the source-only snapshot of a default-off measurement adapter for one pinned native0.17.3 engine. Real native starts and scheduling/progress clocks remain unchanged. Valid selected phase ends return native_start+RAW_delta; journaling adds CPU/syscall overhead. This provides no acceleration claim.

The original pointer-based Decode pairing failed in the live cohort: Decode began on a stack request and ended after that request moved into a heap vector. The historical cohort remains rejected. `source-archive-receipt.v1-superseded.json` preserves the original archive receipt byte-for-byte; it describes the failed revision, not the current files. The original private delivery and runtime logs remain preserved separately.

Revision 2 pairs Decode by a unique active signed request ID and exact native start. Native move construction and assignment preserve both fields through insertion, vector growth and compaction. Actual endpoint object/thread/stack and original begin_object remain visible in the journal. Prefill still requires identical object/thread/stack. Missing, duplicate, ambiguous and mismatched pairs use the original native end and reject qualification. `PAIRING_PROOF.md` and `static-pins.json` record the ownership evidence; the constructor validates 15 instruction windows, and the launcher validates 14 distinct RVA windows because one is contained in the larger Decode-end window.

Engine SHA256 is `af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`; provider SHA256 is `972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00`. The launcher pins the separately sealed revision-2 library SHA256 `176e78652589523f3d6f4e9404c0f247843f7792ec3f7056342ee60500d16e91` (17,152 bytes). The engine, provider, library, device objects, tensor captures and large disassembly are excluded.

The optional --arm-file defers pair collection until the normal lifecycle controller creates an empty owned regular0600 single-link marker after readiness. Activation records its device/inode and creates an exclusive fresh journal. Constructor pin failures exit 125 and must be terminal in the controller. Default-off and residency queries strip phase instrumentation while preserving independent preloads.

Native one-token requests skip the Decode end. A measured cohort must reach that end, and its controller must bind the complete expected request/D set and marker identity. `verify_phase_journal.py --require-deferred-arm` requires decode_pairing_version=2 and verifies complete pairs, exact integer RAW translation, stored Prefill sums, token counts, unchanged D rounding and full D coverage. Without D input, it reports instrumentation evidence only. A fresh controlled runtime result is required for qualification; this archive contains offline evidence only.

Run the hardware-free Python checks from this directory:

```text
python -B test_clock_tools.py
python -B test_decode_move_regression.py
```

The receipts record the red moved-object regression, its green result, 39 passive launcher/verifier checks, 7 actual C identity cases, 42 SHA vectors, 1,000 integer delta vectors and five invalid delta cases. Only numeric Windows host code was loaded. `source-archive-receipt.json` binds these exact source/evidence snapshots to the revision-2 private seal; controlled runtime outcomes are recorded separately.

The preparation tool retains private ELF/provider/static-reader prerequisites and Windows LLVM paths. Rebuilding at a different output path can change ELF identity; review and seal the new artifact before changing its launcher pin. Actual launch, arming and cohort closure belong to the normal controller.
