# Native stock-observer installer: retained development status

The default-off Linux startup installer core is now independently source-reviewed
and builds as a linked DSO. It has not been loaded into Halogen. There is no
installed native read authority, token proposer, outcome connection or serving
gain. The ordinary Halogen server remained ready and unchanged during this work.

Sources and limits are in
[the installer description](../../scripts/benchmarks/halogen_pld_nohit/NATIVE_FRAME_INSTALL.md)
and [independent review](../../scripts/benchmarks/halogen_pld_nohit/INSTALL_REVIEW.md).
The companion [JSON](halogen-pld-installer-status-20261006.json) pins exact sources,
build receipts and emitted inspection. No source from the unrelated FC/NPU files
was changed or included.

## Build and correction

Root built the four exact-basename objects and linked one DSO with C++20/O2,
warnings as errors, PIC, separate code, eager binding and RELRO. Compilation and
linking passed. Static inspection found a real parser defect: a valid ordinary
observer FDE has payload length 16, while a redundant check required 17. The
source was corrected to retain the already sufficient minimum payload length 13
(17 total bytes). The original receipt and library remain retained.

Only the changed installer C++ source was recompiled for the repair; the other
three objects were reused after exact hash checks. The corrected DSO is
`55ce07fb50ac3a38c6c4025e8b601c4086a5e3553d308b62585a2cabeb07336b`.
All owned Windows build jobs closed. No harness, DSO loader, engine entry,
GPU/NPU request or lifecycle action was executed. The two build windows observed
minimum physical reserves above 30.8 GiB and commit reserves above 122.6 GiB,
with sample gaps below 0.267 seconds. These are observations of the short builds,
not new start-admission evidence.

## Exact emitted inspection

The corrected object's copied island at `0x3000..0x7000` is byte-identical to the
first linked island. Its source LOAD ranges are RX code, R data/frames, RW
configuration and RW observation; startup code would publish the copied version
as RX/R/R/RW. No LOAD or GNU_STACK is RWX. None of the 66 dynamic relocation
destinations enters the island.

All emitted direct branches and RIP-relative references in its actual code
range `0x3000..0x3179` remain inside the island, including relay-to-observer CALL,
relay-to-stock-pad JMP, configuration, MXCSR and observation references. The one
stock-pad rel32 sentinel remains deliberately unpatched in the template. The
actual native entry branch and stock continuation require startup publication;
no template was executed.

Root parsed the three copied PC-relative FDEs from the real `.hgn_nohit_ro`
bytes, not the unrelated ordinary `.eh_frame` dump. The ranges are relay
`0x3000..0x3122`, observer `0x3130..0x3167`, and stock pad `0x3170..0x3179`.
The decoded relay CFI has 76 state/advance records and returns to native
`RSP+0x2680`; observer uses ordinary `RSP+8`, and the pad retains native saved
caller offsets. This is exact static CFI inspection, not an executed unwind or
signal test.

## Remaining connection and accelerator assessment

A real guarded startup caller is still absent. It must qualify each admitted
native entry, including the unconditional first 264 stack bytes saved before
the relay's lower-bound check. Native state, applicable signal/CPU migration and
kernel/loader/CET conditions remain unqualified. The
[host-publication audit](halogen-pld-host-publication-20261006.md) now closes the
bounded host-only backend interval at source, with five empty optional model
hooks and exact caller binding. Birth/reset installation, full-prefix
acknowledgement and the concrete read/outcome issuer remain separate work.

CPU executes this control/copy path and adds overhead. GPU remains on the native
target continuation. NPU has no work here. The component changes no target
Prefill operation and selects no drafts; every new Prefill, Decode, acceptance,
capture latency, producer readiness and serving-gain value remains null. The
[multiple-draft assessment](halogen-multi-draft-feasibility-20261006.md) and
[Strata source study](strata0140-halogen-source-assessment-20261006.md) identify
the next bounded acceleration questions without claiming a measured benefit.
