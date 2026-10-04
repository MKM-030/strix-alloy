# Public DD FC admission — 4 October 2026

Both original-geometry FC stages now execute through the ordinary public
Dynamic Dispatch C++ API with owned input/output BOs. All four synthetic
zero-weight calls passed, both contexts were destroyed, the owned child exited
with code 0, and no native fault record was collected. This resolves the
standalone adapter admission blocker; real weights, complete routed/shared
MLP, native MTP integration and any speed gain remain unqualified.

The original adapter called preformatted `initialize_const_params` before
`set_shape`. In the reviewed DD 1.8 source, the constructor and preformatted
path leave `grp_size_` uninitialized, but scratch allocation consumes it.
The installed DD DLL 1.8.0.6 independently has the same read/write paths:
allocation reads `[this+0x58]` at VA `0x180C6F4AD`; `set_shape` writes it at
`0x180CB1429`. Setting/validating geometry first establishes group32 before
allocation. Correct FC1/FC2 scratch extents are 7,580,160 / 2,882,304 bytes.
The revised client reaches every flushed setup checkpoint and both executes.
The failed run's exact 31.3-GiB commit jump was not traced to a retained native
allocation record; the successful changed-order run supports the correction
without recovering that missing original trace.

| Stage | Logical K/N | Kernel K/N | First completed call ms | Second completed call ms |
|---|---:|---:|---:|---:|
| FC1 | 2560/1280 | 2560/2560 | 2.6798 | 0.2583 |
| FC2 | 640/2560 | 768/3072 | 0.2723 | 0.2117 |

These are individual synchronous QPC intervals including DD execution,
depadding and output synchronization. Four calls of a synthetic zero bank are
not a statistical benchmark. They exclude input preparation and do not cover
ten experts, SwiGLU, routing/shared branch, cross-platform transfer or target
verification. Their sum must not be reported as NPU MTP or decode throughput.

The first adapter run exhausted the physical reserve during `fc0_create` and
its final reserve check suppressed `result.json`. Retained logs stop at
19.18 GiB physically available; the exact violating frame and original exit
code were not retained. A separate post hoc receipt preserves those unknowns,
confirms the fresh PID/listener absence and recovered reserve, and does not
rewrite the failed run as a success.

The new parent guard saves each frame before checking it, aborts at 22 GiB
to preserve margin above the hard 18-GiB reserve, and applies/readbacks an
8-GiB process/job committed-memory ceiling before child resume. A CPU-only
128-MiB ceiling check denied a 512-MiB allocation and confirmed clean closure.
The limit constrains process/job commit; host physical and commit monitoring
remain necessary for driver allocations. See the
[Microsoft job-memory contract](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information).

In the corrected NPU run, recorded minimum physical reserve was **42.534
GiB**, commit headroom **197.072 GiB**. All required loaded DLL paths match
the reviewed pins. The optional `me_aie4`, `ryzen_mm` and `dyn_bins` modules
were absent; this client does not use Light/ORT. Fresh Windows PID and WSL
process inspection confirmed no remaining measurement child/engine.

The [evidence JSON](halogen-dd-owned-fc-admission-20261004.json) retains exact
source/config/artifact hashes, full receipts, calls, lifecycle, prior recovery
and CPU ceiling evidence. Raw artifacts remain under ignored
`server/.local/optimization9h-20261004/dd-owned-fc-admission-9210c341c0434659b12d7a516810986c`.
