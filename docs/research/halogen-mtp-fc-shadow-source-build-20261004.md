# Paired FC shadow publication: implementation and host build

The new `halogen0162_mtp_fc_quality_publish.c` implements the previously audited
[paired projection seam](halogen-mtp-d-projection-integration-20261004.md).
Two independent source reviews and root review are released. A root-owned
host GCC build with `-O2 -Wall -Wextra -Werror -shared -fPIC
-fno-optimize-sibling-calls` completed with empty stderr. Its compiler and
hashing children exited, jobs closed and reserve monitor stopped. Minimum
physical/commit headroom was 33.052 / 110.093 GiB.
The [retained build receipt](halogen-mtp-fc-shadow-source-build-20261004.json)
contains source and binary seals and the complete owned-job result.

The source is disabled by default. Explicit `HALOGEN_MTP_FC_QUALITY=shadow4-v1`,
`HALOGEN_MTP_WIRE=D`, a fresh root-managed directory and an exact 120-byte
armed descriptor are required. Both original FCs execute once before capture;
there is no skip mode. The head TLS supplies ABI position/token/count and
model identity. Exact entry, function, callsite and normal-Q8 kernel checks
bind the native embedding and hidden FCs. Other calls retain native execution.

The shim captures both normalized inputs and both native output backups, emits
the codec-compatible 224-byte header and bounded paired request, and validates
the full response identity/digests and finite BF16 words. A successful candidate
replaces both projections before native seed-add. A publication failure restores
both originals and synchronizes; failed restoration terminates the owned
process. The original head result and native errno are preserved by the source
contract. These behaviors have not yet been observed in a live engine.

Review fixed two concrete defects. Reads now use `O_NONBLOCK` before regular
file validation, preventing a FIFO at an expected filename from blocking an
open. After the first candidate write attempt, the overlap guard remains sticky
until the original full-head returns, including successful output restoration.
Reversing exactly these two edits reproduces the previously reviewed source
hash, preserving the other ABI/protocol code.

The final C source SHA256 is
`d33b5dd1e31a38b99e496ab1f378d349493fbc73cac507fbb0698f1b096e740f`.
The compiled, unloaded shared object is
`/home/revn/halogen-re/libhalogen0162-mtp-fc-quality-24de4312a6b846c487463aa6457c402a.so`,
SHA256 `d99d76c571c583440f5e6c1a8d9d60446586ca9813dd292fbf40149b65537a2c`.
It was never loaded into the user engine. No provider or inference session
was initialized for this build.

Actual integration is still incomplete. Root must implement and qualify fresh
model-pointer observation and serial epoch admission, canonical native weight
and qualified graph bindings, the Windows/WSL transport and a persistent NPU
responder. The stateless codec and root-supplied epoch do not detect native
resets or enforce coordinator consume-once state. Native embedding RMS and FC
oracle gates, paired negative/restore/fatal runtime cases, accepted-prefix
lifecycle and matched output/acceptance remain pending. Useful FC skipping or
GPU/NPU overlap needs separate implementation and timing after those gates.
No NPU placement, native parity, full-D/head, acceptance or speed qualification
follows from this source review and host build.
