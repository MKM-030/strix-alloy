# Next mechanism: no justified narrow implementation yet

Existing evidence does not justify another synchronization or launch interposer for material prefill/decode gain. Root reports the scalar cohort produced 52 successful substitutions, zero immediate errors and 4/4 output parity; before/candidate prefill was 1215.98/1235.17 tokens/s and decode 43.81/43.23 tokens/s, with the restored stock bookend still pending when this assessment was requested. The long scalar wait did not translate into an established serving gain.

The single independent compute lead is the repeatedly adjacent **MoE routing and routed int4 projection chain**:

| Return RVA | Kernel descriptor RVA | Exact ELF registered operation | Diagnostic calls | Host-inclusive ms |
| --- | --- | --- | ---: | ---: |
| `0x17d5cc6` | `0x18f43a8` | `k_route_topk_w_grp<2>` | 2688 | 5.863686 |
| `0x17d3d39` | `0x18f42f8` | `k_i4r_rows_gl_o<1>` | 2688 | 5.468117 |
| `0x17d3e59` | `0x18f4300` | `k_i4r_rows_fl_o` | 2688 | 6.024174 |

The exact three-launch sequence occurs 2688 times in both captured requests, all on stream zero, thread 87, result zero. This makes the staged MoE operation a concrete target for future GPU compute work. It does not establish that the operations can be fused: routing determines expert selection, and the trace retains neither kernel arguments, launch dimensions, live buffer extents nor GPU completion times. Static registration identifies these kernels; it does not prove their full arithmetic or dependency compatibility.

Names are bound through exact ELF registrations: descriptor `0x18f43a8` at registration `0x1875e19`, name RVA `0x394b1`; descriptor `0x18f42f8` at `0x1874d91`, name RVA `0x20e16`; descriptor `0x18f4300` at `0x186ca09`, name RVA `0x3aa2e`. Each calls `__hipRegisterFunction@plt` with the same device function/name string. The latter two launch stubs are bounded 273-byte functions starting `0x17d3c30` and `0x17d3d50`; they forward twelve argument pointers and popped launch configuration to `hipLaunchKernel`. They are not operations that can be merged by simply skipping a launch.

An implementation would need the complete native MoE operation source and an operation-level replacement preserving top-k selection and ties, weighting, int4 decoding, both projection stages, precision, tensor extents, scratch ownership and stream order. Such a replacement might reduce intermediate traffic or device dispatch cost. No source-supported GPU saving ceiling or end-to-end expected gain is available from the retained evidence, so this is **a compute lead, not a ready implementation recommendation**. Do not implement a three-call capture/replay or substitution based only on these addresses.

The only quantitative ceiling established here concerns observed host intervals: all three calls total **17.355977 ms, 0.181642%** of the 9555.117690-ms diagnostic. That is an optimistic ceiling for eliminating every observed host interval in this triple, before replacement overhead. The first two submissions alone account for **11.331803 ms, 0.118594%**; a fusion retaining the final submission would target that portion. All 49,725 observed launches total only 118.834770 ms (1.243677%). Any material benefit must come from changed GPU work or dispatch behavior, not a claim that host submission dominates. No genuine prefill/decode boundary was provided, so the chain is not relabeled as one phase.

The two observed device synchronization sites also do not justify another wait-removal attempt. `0x17f1c97` has 113 calls/360.696839 ms and is immediately followed in static code by a four-byte D2H copy returning at `0x17f1cc2`, then a CPU load of that result at `0x17f1cca`. `0x17f8952` has 58 calls/2276.463904 ms after model/output helper `0x17f2560` and `hipGetLastError`; its later branch may D2H-copy output at `0x17f8a00`. These are completion/result boundaries, and their intervals include real upstream work. Removing a fence can move that wait without removing work.

Conclusion: **no justified next narrow optimization from this census and ELF alone**. If complete native MoE source becomes available, the one mechanism above warrants a whole-operation GPU implementation and matched serving qualification. Otherwise, stop this branch of source-only work. No retired ready64, native-page, quartet or scalar path is proposed for rerun.

Evidence: existing `hip-host-direct-census-20261008/host-census.bin` SHA256 `57c11ac1f904c3fc28175844ebf7d8e850fb6fd1351c420117f21de2dc8fe0fb`; retained exact 0.17.2 ELF SHA256 `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`. Bounded CPU-only replay and static inspection; no hardware access, sources installed, build, lifecycle action, live request or root-state edit.
