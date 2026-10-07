# Real NPU → WSL GPU handoff, 7 October 2026

The fresh Windows VitisAI producer and the original Halogen `k_embed_gather`
consumer now complete a real staged handoff. The binary-pipe implementation
removes per-row DrvFS publication and readback from the timed exchange. Twelve
alternating frozen A/B outputs pass the unchanged component tolerance in each
version, and all twelve GPU readbacks equal the actual newly produced NPU bytes.
The NPU has not been substituted into the serving engine.

| Measured component scope | File transport v1 mean | Binary pipe v2 mean | v2 median | Binary pipe v3 mean |
|---|---:|---:|---:|---:|
| NPU `session.run` | 1.629 ms | 2.470 ms | 0.956 ms | 1.331 ms |
| Publication/pipe through GPU acknowledgment and readback | 9.437 ms | 2.211 ms | 1.971 ms | 2.423 ms |
| Complete diagnostic staged handoff | 16.933 ms | 6.348 ms | 4.426 ms | 6.134 ms |

The subsequent v3 run adds a checked direct kernel-PID observation before HIP,
preserving the same binary row transport. All twelve fresh rows again passed.
Its means are 1.331 ms NPU execution, 2.423 ms exchange, and 6.134 ms complete
diagnostic handoff. This identity change is not a further throughput improvement
claim. Physical reserve stayed above 40.190 GiB and commit reserve above
195.630 GiB in the v3 component run.

The complete diagnostic path decreased **62.51%**; the exchange scope decreased
**76.58%**. These are sequential component observations, not a matched serving
throughput experiment. The v2 NPU mean includes a 19.069-ms outlier, which remains
in the result. Four NPU warmups are excluded and twelve fresh calls retained per
version. Both use the same frozen graph, inputs, provider, pinned serving image,
HIP/DXG libraries, original gather, 5120-byte BF16 rows, destination poisoning,
event completion, exact D2H verification, and 37 checked HIP copies. Model/kernel
setup and root release barriers are separate. GPU first-row behavior is retained.

V2 writes its FP32/BF16/readback artifacts after the row exchange and consumer
cleanup. That diagnostic recording still costs 9.969 ms per row on average;
moving it out of the exchange does not make the total diagnostic work disappear.
Neither transport is zero-copy or a production overlap implementation.

The complete hardware-only VAIML/STX partition and disabled CPU fallback receipts
are retained. ORT profiling contains sixteen VitisAI-labeled node events covering
the four warmups and twelve rows. The provider's `EndProfiling` callback logs an
empty-event-container error: complete EP-specific device profiling is **not**
claimed. The original NPU tolerances remain `rtol=.03, atol=.003`; the component
passes them, while the native GPU projection differs in 858/847 BF16 words for
A/B. Exact transfer parity does not imply native arithmetic word parity or
whole-head equivalence.

There are no new measured serving Prefill tok/s, Decode tok/s, or acceptance
values from these component tests. The native scalar E/M1 projection's retained
device mean is only 0.153 ms. A synchronous 6.348-ms replacement cannot be
presented as useful engine acceleration. A useful future integration needs an
independent early-preparation window and a faster consumer; the failed ready64
integration must not be repeated under a new name.

## Copy attribution

The fresh v2 ETW trace decodes 67,641 events and records 350 native Copy spans.
The native node metadata query binds physical adapter 0/node 1 to engine type
Copy. Allocation-lifetime receipts retain 22 observed consumer-origin transfer
associations touching 18 subsequent System Copy DMA spans. Installed image/PDB
writer evidence is being checked for exact allocation and parent-queue aliases.

The v2 captured guest process ID is 5214, whereas the visible system-proc chain is
979→914→1. The latter does not prove the kernel's initial-namespace PID. A new
ephemeral BPF filter on a private socket demonstrated this distinction directly:
the same probe had visible system PID 1284 and kernel PID/TGID 1591. The helper
also succeeded inside the pinned image with only `CAP_BPF` added and no GPU
device/model mount. It attaches to its own socket, closes its FDs, and makes no
global tracing, namespace, driver or WSL configuration change. V3 records this
direct kernel ID before HIP initialization; historical guest 5214 is not
retroactively relabeled.

**The fresh v3 capture closes that identity gap.** Observed kernel PID/TGID 2302
matches captured Dxg guest 2302 in VM `e26026b2-5f6f-485e-a66a-dfa3c90d0e56`.
The separate visible chain is system-proc 926→distro 861→container 1; birth 4549,
boot ID, exact executable/header hashes, pre-HIP QPC enclosure and checked closed
probe references agree. Its loss-free 62,406-event trace retains 339 physical
adapter 0/node 1 Copy spans, 78 attested consumer Compute queue records, and 22
qualified consumer allocation origins (seven fills, eight context initializations,
seven discards). No consumer Transfer50 was observed during the measured row
window. Zero Copy DMA spans are attested to that consumer; this does not make the
remaining spans foreign by default or equate 37 HIP copies with Copy-engine load.

The same-named DMA/queue/submit-sequence chains now have concrete native writer
evidence. Allocation-fill events can precede failure/retry status checks, so
build-attempt association is kept distinct from committed DMA membership and
exclusive PDH occupancy. There is no blanket exemption for System PID 4.

The final reviewed attribution uses
`component-attribution-native-kernel-reviewed.json` and
`component-native-kernel-reviewed-summary.json`. Its image-specific native
writer evidence proves allocation and queue aliases, while explicitly rejecting
successful-fill commitment from a pre-status-check event. An independent review
checks all 62,406 records, 8,799 retained source references, four identity
receipts, helper hashes and QPC conversion. The positive scopes stay 78 attested
consumer Compute records and 22 allocation origins; the 339 Copy spans remain
without attested exclusive consumer ownership. This component capture cannot
retroactively qualify a serving-engine PDH interval.

## Evidence

- Raw v1: `server/.local/optimization9h-20261004/real-handoff-15ce20218f854c5b862db86bcce14436`.
- Raw v2: `server/.local/optimization9h-20261004/real-handoff-v2-1559059fb91c48c1a063fa96814a4940`.
- Raw v3 and native identity/attribution receipts: `server/.local/optimization9h-20261004/real-handoff-v3-22915da8997c4a0891fe2c9fee7e3f84`.
- Structured measurements and raw receipt hashes: [halogen-npu-wsl-handoff-20261007.json](halogen-npu-wsl-handoff-20261007.json).
- Sources: `halogen_npu_wsl_handoff_v1.py`, `halogen_npu_wsl_handoff_v2.py`, `halogen_npu_wsl_handoff_v3.py`, their native consumers, and `halogen_handoff_capture_worker.py`.

The reviewed transport regressions pass (five v1, eight v2, three v3). The attribution
analyzer's focused regressions pass. This milestone qualifies component
production/consumption; the full acceleration objective remains active.

## Serving restoration

After v3, the unchanged HistoricalStock restoration observed resident WSL for
ten minutes without qualifying 44 GiB physical and 131 GiB commit headroom for
60 seconds. No server was launched by that attempt. A single owned conditional
watcher now waits for genuinely changed resident headroom, then uses the normal
visible Windows PowerShell 5.1 lifecycle. It does not relax admission, repeat
the component tests or launch a competing engine. Final ready/open status must
be checked from the live continuation receipt before it is reported.
