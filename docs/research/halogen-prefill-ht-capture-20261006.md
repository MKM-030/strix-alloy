# Frozen ordinary Prefill QKV capture, 2026-10-06

The one-request capture completed and preserved the frozen natural 16,384-input,
128-output-token response exactly. It supplies reusable original GPU inputs and
output for a finite component comparison. No component speed, Prefill tok/s,
Decode tok/s, acceptance change or NPU benefit is measured by this capture.

The default-off observer selected one layer-0 ordinary DeltaNet QKV operation,
M8192/N10240/K2560, store16/variant4616/mode4. It recorded original weight
preparation followed by the original library GEMM on stream0. Preparation's
launch was `(20,80,1)` with block `(512,1,1)`, caller RVA `17ecd6a`; the library
received original X as B and original Y as both C and D. The complete pipeline
comparison must therefore include original preparation on every stock call.
The independent route audit is in `halogen-prefill-ht-stock-route-20261006.md`.

All 13 exported files, 222,853,318 bytes in total, were rehashed by root against
the completed inventory. The selected packed payload is 13,107,200 bytes;
X is 41,943,040 bytes and reference Y is 167,772,160 bytes. Ten bounded allocation
queries, two device synchronizations and five device-to-host copies make this
an intrusive observation. Its 28.391-second request wall is excluded from
serving performance. The response SHA256 is
`bc179b2873f085833dbd1ec05e9aba7703957dfafafdab71bba3d3cfb2f32e4d`.

The first stock-restoration admission expired below the unchanged 44-GiB
physical threshold, before launching a controller. The same coordinator's
normal recovery subsequently met 44-GiB physical/131-GiB commit admission for
60 seconds and restored stock at context262144, arena/chunk8192, Cache Off,
MTP2/PLD3,3. Controller26820, run `11df605c7494474d880efa4f47e0b1b5`, was
ready with zero active requests and remained open. No reserve was relaxed and
no foreign process or global WSL setting was changed. The preserved coordinator
result is `passed=false` because it retains the first admission failure;
`captured=true`, `original_ready_open=true`, `recovery_pending=false`, and
the continuous reserve guard has no errors. Minimum physical reserve was
29.220 GiB; minimum commit reserve was 121.185 GiB. Current identities must
still be verified before a later lifecycle action.

The next comparison has independent native-HT and bounded prepared-original-W
arms. The latter retains 50 MiB of original prepared GPU weights for this
selected descriptor and leaves Halogen's whole-trunk policy disabled. Exact
raw Y preservation is required before timing; no borrowed or widened tolerance
is permitted. Only a component win justifies a comparable serving cohort.

GPU is the concrete acceleration candidate. CPU manages bounded metadata and
qualification. NPU provides no supported equivalent packed-HT or GPU-memory
boundary here. The cache does not add physical memory or separate weights
onto the NPU. It may remove repeated GPU Prefill preparation; Decode and
acceptance improvements remain unproved.

Machine-readable evidence and raw receipt links are in
`halogen-prefill-ht-capture-20261006.json`. The full acceleration goal remains
unachieved.
