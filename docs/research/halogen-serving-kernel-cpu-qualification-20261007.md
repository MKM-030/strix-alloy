# Native serving-identity bridge CPU qualification — 7 October 2026

The real native bridge, BPF-only capability removal and held-FD exec passed in
two finite CPU-only configurations. The second preserves the existing serving
container's SYS_PTRACE capability. Each configuration first measured a separate
no-BPF container, then added only BPF in a fresh qualification container. No
GPU/NPU device or real flash_serve was executed.

| Configuration | Kernel PID/TGID | Container PID | E/P/bounding after | I/ambient after |
|---|---:|---:|---:|---:|
| Docker default | 3897 | 7 | 2818844155 | 0 |
| Serving SYS_PTRACE baseline | 4277 | 7 | 2819368443 | 0 |

Both144-byte ABI calls reported closed probe FDs, checked capability removal,
no probe/drop errors and runtime capability extent41. The post-exec reporters
prove unchanged PID, birth ticks, boot, UID, namespace, environment digest and
all five independently measured baseline masks. The actual cgroup view contains
the complete container ID under a component-scoped host cgroup namespace.
Receipts are created0600 in WSL-native private storage; their preserved Windows
copies and plan/result hashes are listed in the [evidence JSON](halogen-serving-kernel-cpu-qualification-20261007.json).

The first attempt completed its no-BPF observation but the host revn reader
could not open its root-owned0600 receipt. It made no native probe. The corrected
coordinator uses root only to read/hash those exact owned receipts; it neither
relaxes their permissions nor changes the tested bridge. Both corrected runs
closed their owned Windows jobs and removed their exact containers. Minimum
physical/commit reserves were above41/197GiB;22GiB component admission and18GiB
runtime floors remain unchanged.

This qualifies the CPU bridge mechanism, not the exact Halogen exec boundary,
an engine queue/Copy-span association or faster serving. The standalone launcher
is default-off. Actual service integration must preserve its authenticated API,
lease lifecycle and exact kernel/driver/model settings. Container-level BPF adds
also reach ancestors; the native helper removes BPF only from the observed engine
task before exec. No container-wide rights removal is claimed.
