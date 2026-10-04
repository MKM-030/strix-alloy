# Live Halogen MTP input capture — 4 October 2026

The exact 0.16.2 head tap captured 32 complete entry/exit pairs from a live v2
8192-input / 128-output greedy story request. The output SHA-256 matches the
corresponding stock serial and MTP outputs. Original head execution and the
engine's verifier/rollback remain authoritative. This establishes a usable
input/state boundary; it does not implement NPU substitution or a speedup.

The [research tap](../../scripts/benchmarks/halogen0162_mtp_tap.c) gates the
engine file, function bytes, executable mapping and complete prologue before
installing its trampoline. The head function starts at RVA `0x17db310`, ends
at `0x17dc289`, and has SHA-256
`132f2da76d86694ffe5f120d61e304e57c685f3db72935c6d5e61bf7b0d5cc20`.
The observed ABI is `int32_t head(model*, int32_t *tokens, int32_t count,
int32_t start_position)`. The tap always calls and returns the original head.

Arming happens after service readiness and prompt calibration. Each capture
retains token IDs, the final input residual row as raw u16[10240], and 768-byte
recurrent state before/after execution. One FP32 vocabulary-logit vector is
retained. Numeric BF16 interpretation is not established by the raw-u16 copy.
The first observed call has count 8192; later calls include repeated start
positions, so the capture preserves the speculative state transitions rather
than assuming every head call advances the target position.

There are 131 regular exported files totaling 1,762,257 bytes. The frozen
prompt hash is `0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1`;
output hash is `0fbe27247d33d2829aa90b66964ff3bb946679be7ce79b379e2555f60ec74fa6`.
The direct service model name differs from the gateway alias, so request-JSON
hash equality is not claimed. All retained timing is intrusive and excluded
from performance comparisons.

The initial coordinator ended before arming because its parent had not called
`service.r.configure()`. The engine remained live under its original guard.
The root resumed that exact PID/run/container using a stable Windows process
handle and verified creation identity, then captured/exported and requested
normal shutdown. Both attempts remain retained; the initial failed receipt is
not relabeled. Parent configuration is now initialized in the coordinator.

The successful resume proves original cleanup and RAM recovery. Physical and
commit minima were 22.6209793 and 113.3460464 GiB, above the 18-GiB floor.
Artifacts are retained under
`server/.local/optimization9h-20261004/mtp-tap-resume-d20a7077972049538940fe6b95bf62c7`.

| Artifact | SHA-256 |
| --- | --- |
| Tap C | `15b8ad03de83bb436eb6344138e406652d70bb45fffd4650612ac68aa6af4fd0` |
| Tap shared object | `9df241ac54717f60477ce732faa54f3b1509a963e23eb3bd7eda824cfb254fb8` |
| Fixed launcher | `f02115d2752e4c057e9481d230a5ef0f42fb9be2dca89d7791959d0e923f39b1` |
| Successful result | `abceb2782b1542c8ad15bc9d1a1e05381b48d97b9f7d21b78f0c2d8c4f108866` |
| Entry/exit pairs | `1779e5bae7d5f7e32ae96f87559a44b7e4c9aeff375e628590e9ade6d68bec1e` |
| Terminal recovery | `04a113d5cc011a710c291abc82faee2b34d5b8456361002a28361c6575ae6bf1` |

Expert IDs, routing coefficients and the post-attention MLP input are absent
from this head capture. A separately identified MLP seam is being prepared to
measure those values. No expert-set cache hit rate or full NPU MTP result is
inferred from this trace.
