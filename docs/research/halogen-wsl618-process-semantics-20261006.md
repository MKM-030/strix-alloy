# WSL 6.18.33.2 guest process semantics — 2026-10-06

**Exact release source resolved; GPU ownership remains not attributed.** Microsoft's [linux-msft-wsl-6.18.33.2 release](https://github.com/microsoft/WSL2-Linux-Kernel/releases/tag/linux-msft-wsl-6.18.33.2) links immutable commit `c21a03b2943d147c280bdf32530d4fe6badfd6bd`. Its [Makefile lines 2–5](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/Makefile#L2-L5) specify 6.18.33.2; the pinned x86 configuration has the standard WSL2 suffix at [line 34](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/arch/x86/configs/config-wsl#L34) and DXGKRNL enabled at [line 6603](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/arch/x86/configs/config-wsl#L6603).

Root supplied the running version `6.18.33.2-microsoft-standard-WSL2`. This assessment matches its official release source; it does not attest the running binary's build provenance. The prior 6.6 source is not used to establish 6.18 semantics.

The exact guest relation is:

| Stage | Established by pinned source |
|---|---|
| Object creation | Stores `current->pid`, `current->tgid`, `task_pid_vnr(current)` and the active PID namespace separately. [dxgprocess.c25–38](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/drivers/hv/dxgkrnl/dxgprocess.c#L25-L38) |
| Object reuse | Lookup uses thread-group ID; opening `/dev/dxg` obtains that object or invokes creation. Thus creation metadata can belong to a different thread from a later submitter. [dxgmodule.c351–403](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/drivers/hv/dxgkrnl/dxgmodule.c#L351-L403) |
| Host creation request | Sends the guest object pointer, the stored creation-task ID, `linux_process=1` and current task comm. A nonzero returned host handle is retained in `host_handle`. [dxgvmbus.c669–710](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/drivers/hv/dxgkrnl/dxgvmbus.c#L669-L710) |
| Protocol shape | The request declares a pointer, a 64-bit ID, a name array of 261 16-bit elements and Linux bit; the response declares `hprocess`. [dxgvmbus.h 250–263](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/drivers/hv/dxgkrnl/dxgvmbus.h#L250-L263) |

The transmitted ID is an **initial Linux PID namespace task ID/TID**, not automatically a container PID, TGID or namespace-relative TID. The kernel's [PID helpers168–185 and234–253](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/include/linux/pid.h#L168-L253) distinguish initial and current namespaces; [fork.c2254–2260](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/kernel/fork.c#L2254-L2260) sets the initial task ID and thread-group relation. A null namespace selects the current active namespace in [pid.c510–523](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/kernel/pid.c#L510-L523). `getpid()` returns namespace-relative TGID, while `gettid()` returns namespace-relative task ID. [sys.c990–1008](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/kernel/sys.c#L990-L1008)

The name comes from task `comm`, a mutable label of 16 bytes including NUL, so it carries at most 15 non-NUL bytes. It is copied element by element into the payload's 16-bit array; it does not supply a full path, command line or trustworthy ownership identity. [sched.h 323](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/include/linux/sched.h#L323), [sched.h 2002–2006](https://github.com/microsoft/WSL2-Linux-Kernel/blob/c21a03b2943d147c280bdf32530d4fe6badfd6bd/include/linux/sched.h#L2002-L2006)

These sources establish the **guest protocol relation only**. They do not prove that Windows ETW `ProcessIdInVm`, `DxgProcessInVm` or `DxgProcess` aliases any guest payload field or returned handle. Host event emission, object lifetimes, allocation joins and Linux task birth/namespace/container identity remain unresolved.

All source anchors use **one-based original raw-file line counts**, checked through bounded read-only HTTPS fetches into memory. The web renderer normalizes whitespace, so its display line indices were not used as source anchors. The JSON companion records every immutable source URL and range.

`trace=false`. No WSL commands, hardware, capture, benchmark, installation or update operation occurred. No broad update survey was performed; the two-hour update gate remains unchanged. No speed gain is claimed.
