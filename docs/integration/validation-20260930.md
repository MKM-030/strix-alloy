# Validation record: Halogen v2 and managed endpoint

Validated 30 September 2026 on the existing Windows/WSL2 Strix Halo machine.
No display driver, BIOS, Windows clock or WSL memory-limit setting was changed.

| Check | Observed result |
|---|---|
| Installed Halogen backend source tests, Windows | 105 total: 86 passed, 19 platform skips |
| Fresh exported backend source tests, Windows | 105 total: 83 passed, 22 platform/installation skips |
| Backend tests under WSL Linux | 105 total: 103 passed, 2 platform skips |
| Managed gateway/controller tests | 18 passed, including owned Windows process closure |
| Shared publication helper tests | 14 passed |
| PowerShell syntax | 26 source files parsed; no launchers executed by the parser |
| Fresh exported server/helper suites | Both passed using the installed isolated Python test environment |
| Actual fresh backend installation | Completed from exported tracked source; extracted/compiled components matched their pinned hashes; no model/GPU workload started by setup |
| v2 file integrity | Full 66,687,678,432-byte SHA-256 verified; per-file receipt and bounded checksum reads tested |
| w4b versus v2 benchmark | 126 retained core/serving measurements, including PP512, PP2048 and 262144 capacity |
| Managed lifecycle | Multiple real v2 starts; three controlled managed shutdowns with backend memory recovery; final cache-Off service left running |
| Gateway live tests | Direct/proxy paired requests, identical outputs, real SSE and negative authentication passed |
| Public HTTPS | Valid token answered OK; no token returned 401; tested from the Windows PC through its public hostname |
| GUFO candidate | Build succeeded; 26/30 operator runs passed; two exactness failures in each tuning mode; not promoted |

The initial broad Linux suite incorrectly ran a Windows-only lifecycle fixture. Its
platform requirement is now declared; the fixture still runs and passes on Windows.
The parser fixture initially lacked the new package/server directories. It was extended,
including deliberate malformed-source checks; real new source is not skipped.

Two integration failures were retained before the successful managed runs: a guard
refused a source tree that changed after launch, and an unbounded full-file checksum
read crossed the Windows reserve through page-cache growth before model allocation.
Source checks were preserved; guard bootstrap diagnostics were added; bounded checksum
reads corrected the second issue without lowering the 12 GiB runtime protection.

The first proxy design added a synchronous health-probe delay. The repeated paired
check after asynchronous readiness monitoring measured about 0.9 ms serial and 20.8 ms
MTP mean added whole-request time; per-pair noise includes negative differences.
These are small-sample observed overheads, not universal latency guarantees.

The Exact-cache experiment preserved output identity but returned zero cached tokens
on repeated 8192-token requests. It failed its reuse gate and was not promoted. Final
serving and all cold-prefix benchmarks use cache Off. Initial Tailscale TLS negotiation
failed immediately after enabling Funnel; subsequent verified HTTPS requests passed
without disabling certificate verification.

The final publication contains source, documentation and sanitized measurements only.
No API token, installed executable, DLL, shared library, driver or model file is included.
Full raw local run logs remain under ignored version-specific `.local/` directories.
Do not edit or update guarded backend source while its model is running: source drift
is intentionally a stop condition, not a supported live-upgrade mechanism.

[Checkpoint/latency results](../benchmarks/halogen0151-v2-262k-20260930.md)
[Research and remaining implementation gates](unified-review-20260930.md)
