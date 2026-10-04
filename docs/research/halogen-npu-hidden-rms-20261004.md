# Native D hidden-RMS comparison preparation

The matched native capture tools are implemented, reviewed and compiled. The
hardware capture and its CPU comparison have **not run**. This preparation
establishes no NPU integration, arithmetic parity, acceptance gain or speed gain.

The [previous D preparation](halogen-npu-d-prepare-20261004.md) retains its failed
CPU screen: 109/76 final BF16 word differences for A/B, with the first observed
hidden-RMS differences at 2/4 words. Its tolerances and failed result are unchanged.
The next observation compares the native boundary using the same captured input
and gamma, instead of assuming either the NumPy or ORT reference is authoritative.

The new [observer](../../scripts/benchmarks/halogen0162_mtp_hidden_rms_tap.c)
requires explicit and observed D wire mode, count1, the pinned engine and forward
function, and the exact hidden-RMS launch returning at RVA `0x17db632`. It retains
the 10,240 BF16 words of residual, raw gamma and output. Two synchronization calls
and three host copies complete before the native FC continuation; the original
launch still executes once. Export occurs after the request and native forward
finish, with eight files capped at 128 KiB. Its timing is intrusive and unscored.

The [launcher](../../scripts/benchmarks/halogen0162_mtp_hidden_rms_tap_launcher.py)
uses the pinned managed service, one cold 8192-input/16-output greedy request,
post-response harvest, ordinary stop and direct recovery checks. The
[comparison](../../scripts/benchmarks/halogen_npu_v2_d_rms_compare.py) preserves
the original A/B hashes as independent integrity checks. A different legitimate
captured input permits one additional call in the same fixed CPU session. There
is no arithmetic fitting or tolerance adjustment.

Local GCC compilation with `-O2 -Wall -Wextra -Werror -shared -fPIC
-fno-optimize-sibling-calls`, libdl, libcrypto and pthread completed successfully.
The result is an ELF64 little-endian x86-64 shared object exporting
`hipLaunchKernel`. The launcher's `--prepare-only` source/runtime/SO checks passed.
Source review checked the actual native SysV dim3 registers/stack, original call
count, pointer lifetime, harvest synchronization and process-lifetime preload.
Actual runtime ABI and capture qualification remain pending.

The post-WSL pre-launch snapshot recorded 43.438 GiB available physical RAM and
198.045 GiB commit headroom. Physical availability is below the existing 44 GiB
engine admission threshold; an unrelated GPU workload was also observed. No
engine or NPU provider was started. Preserve the 18 GiB runtime reserve and obtain
an exclusive admitted window before capture. The full head, recurrent state and
target verifier integration remain separate unfinished work.

## Sealed artifacts

| Artifact | SHA256 |
|---|---|
| Observer C | `4d612044fb5e84932726d8a4568d2ca3bd463832eeab875376d7c286c8640603` |
| Compiled observer SO | `cdd6f54bccb3b42131004195d4f30f092362df93d90b711930077d634d98b52e` |
| Launcher | `026a95e747e908d421869be7e6a1c57d2f0c0b7b59bd86fbc3de648bfe23def4` |
| CPU comparison | `1e1c2c68a1c1017a1ef734ba8accc05e20e1b4bf425e5cd29327be03484a3c81` |

Local preparation receipt:
`server/.local/optimization9h-20261004/hidden-rms-preparation-20261004.json`.
The exclusive source/runtime plan is retained separately; no capture receipt or
provider execution is inferred from it. Existing sealed observers are untouched.
