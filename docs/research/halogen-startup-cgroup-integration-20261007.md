# Exact cgroup memory integration and Current8K restoration

The startup sampler previously selected the aggregate cgroup root when the
container used the host cgroup namespace. It now resolves the exact unified
cgroup leaf through `/proc/self/cgroup` and its cgroup2 mount. The caller uses a
memory-only CLI, carries the helper through the source manifest and read-only
mount, and preserves the first failure while recording the full traceback.

Root applied the reviewed five-file patch and ran one isolated CPU container
using the same pinned image. Its telemetry resolved the container's own leaf,
matched its 256 MiB memory limit and returned the complete expected counters.
The probe opened no model files, called no cache worker, performed no cache
advice and accessed no device. The exact owned container was removed.

The ordinary visible Current8K server was restored and independently verified
through fresh process births, run IDs, container identity and authenticated idle
health. Startup admission remained 40 GiB physical, 131 GiB commit and 60 stable
seconds. The last 61 admission samples had minima of 40.0117 GiB physical and
195.6643 GiB commit reserve. This single successful start does not establish
sufficiency at exactly 40 GiB under other loads. Runtime reserve remains 18 GiB;
the final observation had 25.3648 GiB physical and 117.6068 GiB commit reserve.

Serving settings remain context 262144, prefill chunk and workspace limit 8192,
MTP2, PLD3,3, Cache Off and console tracing. The server remains ready and open on
port 8840. Foreign applications, models, drivers and global WSL settings were
preserved.

The first coordinator failed before applying the patch because a bare Git name
was interpreted as a workspace path. Its subsequent 600-sample admission period
did not stabilize; no replacement server was created. Root proved the unchanged
stopped interval and retired only that child-free coordinator. The corrected
coordinator resumed that same stopped window with absolute executable paths and
retained read queries, then completed the integration and restoration. The
failed evidence remains intact.

This fixes memory attribution and enables subsequent work. It provides no new
measured Prefill, Decode, MTP acceptance or NPU acceleration result. The source
reviewed after-ready capture draft still requires a fresh bound plan before
activation.

Evidence: [independent verification](halogen-startup-cgroup-integration-20261007.json),
including hashes of the patch, coordinator, readiness receipt, CPU qualification,
cleanup and all 19 final source pins.
