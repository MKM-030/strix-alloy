# Native WDDM collector compile plan — 5 October 2026

The new source is
[`halogen_windows_wddm_probe.cpp`](../../scripts/benchmarks/halogen_windows_wddm_probe.cpp),
SHA-256 `ce658a938a10f1d72023bdef97893848d44d5c78ac9bc77b2233dc6716ac1d91`.
Its separate
[`CMakeLists.txt`](../../scripts/benchmarks/halogen_windows_wddm/CMakeLists.txt)
is `a023fd4fc9438a01f9053fc9d99bbe532bb2ad2b43b00b8e4c493bd385d04c98`.
This preparation wrote/reviewed source and read local SDK/toolchain metadata;
it performed no build, native API acquisition, hardware query or network call.

ROOT can configure a fresh owned output directory using the available CMake and
Visual Studio 2022 BuildTools. These commands **compile only** and do not run the
collector:

```powershell
$wddmBuild = Join-Path 'C:/Projects/strix-alloy-clean/artifacts' ('halogen-wddm-build-' + [guid]::NewGuid().ToString('N'))
& 'C:/Program Files/CMake/bin/cmake.exe' -S 'C:/Projects/strix-alloy-clean/scripts/benchmarks/halogen_windows_wddm' -B $wddmBuild -G 'Visual Studio 17 2022' -A x64 -DCMAKE_SYSTEM_VERSION=10.0.26100.0
if ($LASTEXITCODE -ne 0) { throw 'WDDM configure failed' }
& 'C:/Program Files/CMake/bin/cmake.exe' --build $wddmBuild --config Release
if ($LASTEXITCODE -ne 0) { throw 'WDDM build failed' }
$wddmExe = Join-Path $wddmBuild 'Release/halogen_windows_wddm_probe.exe'
Get-FileHash -LiteralPath $wddmExe -Algorithm SHA256
```

The CMake target requires MSVC x64 and SDK 10.0.26100.0, C++17, `/W4 /WX`, and
static CRT; it links the standard `gdi32` import library. The existing retained
ADLX compiler metadata selects MSVC 14.44.35207 / compiler 19.44.35228.0. The
source and direct SDK/import-library pins are in the companion
[pin manifest](halogen-wddm-collector-pins-20261005.json). No driver, private Wkmi,
ROCm library, ADLX SDK, model or downloaded dependency is required. Compilation
was subsequently verified by ROOT's retained configure/build result below.

ROOT executes the resulting absolute executable **with no arguments** under the
existing owned child/job and 22-GiB admission / 18-GiB continuous physical/commit
reserve guard, retaining the unchanged ready/idle server identity and health
counters. Capture stdout/stderr/exit code to exclusive owned files. One fixed
sample and at most 13 native graphics calls are requested. The 10-second internal
pre-call deadline cannot interrupt a synchronous driver call; ROOT must retain a
hard outer deadline and terminate its owned child on timeout. No collector process
or availability test was started by the source author.

The exact LUID is `0x00000000_0x00011884`, physical adapter0, requested node2.
The collector requires a successful native physical-adapter count, AMD
vendor `0x1002` / device `0x1586`, nonsoftware adapter type, and unchanged selected
physical index. It records driver-model version and support-gates metadata and
performance queries by that reported WDDM version. Node metadata must succeed
with the same packed physical-index/node ordinal before NODEPERFDATA is queried.
The PDH `eng_2` to native node2 join remains explicitly unqualified.

Every attempted open/query/close status is emitted as signed 32-bit NTSTATUS and
its unsigned hex representation, with SDK buffer size, host QPC/FILETIME bounds
and status-qualified fields. Only STATUS_SUCCESS qualifies data; an explicit
STATUS_NOT_SUPPORTED means unsupported, while other errors remain unknown.
Skipped queries have null status and a reason. Successful responses with changed
requested indices preserve raw fields but mark them unqualified. An identity,
node-metadata or dynamic-index mismatch, or failed adapter close, yields exit1.
Unavailable optional telemetry is a valid discovery outcome and is never zeroed.
Adapter close is attempted once, including after the internal deadline; there is
no retry, alternate adapter fallback, device creation, queue, escape or setter.

Fields retain documented units: engine/memory Hz, mV, 100-ns maximum transition
latency, bytes, RPM, deci-Celsius, and power in tenths of a percentage **not watts**.
Transfer amounts have unqualified provider-interval boundaries; reported maximum
frequencies are not current power limits. Segment sizes are not proof of BIOS UMA
reservation. The powered-on/raw override byte is not AMD private power-policy
readback. Neither engine frequency nor memory frequency identifies DCLK/FCLK,
proves a held fabric clock, or qualifies simultaneous GPU/NPU execution. No
frequency-hold setter is present. A single idle acquisition supplies current
state and API availability; it cannot explain the historical decode gap or
establish loaded-state behavior, a limiter reason or a safe tuning value.

ROOT subsequently configured and compiled the released source with both stages
exiting 0; the configure log identifies MSVC 19.44.35228.0. The executable SHA-256
is `87e0dde5ff325f86e676fe4c79085dfeb0f1a7fa800b588ea032d9dca5603923`.
The retained
[build receipt](../../server/.local/optimization9h-20261004/wddm-build-1200a1d89bcb43d9b6c379e93f8b665c/result.json)
is `333c2cd61fb5c0be5003474f2a6a1a7b0f7d32d75ba295a1f7abe5afe9195ec7`;
the pin manifest also records the executable and stage-receipt hashes.

ROOT's single bounded idle-window invocation exited 0 with empty stderr. Its
[sample receipt](../../server/.local/optimization9h-20261004/wddm-sample-2074981aa39448e0a98536282acd6dba/result.json)
is `ad89839e58d4569bd5a6b5c733229f89ab9ea6912be5d5605a446085094adb26`;
the unmodified
[raw sample](../../server/.local/optimization9h-20261004/wddm-sample-2074981aa39448e0a98536282acd6dba/sample-stdout.txt)
is `5b374ff41986d8fc3f46da751f4c6e96a68cdd3180c7bb7d85350d554b9311c7`.
All 13 attempted graphics calls (open, 11 queries, close) returned signed
NTSTATUS 0 / hex `0x00000000`. Acquisition, native adapter identity, node metadata
and close were qualified; no requested input-index mismatch occurred. Native
vendor/device were 4098/5510 and description `AMD Radeon(TM) 8060S Graphics`.
Driver-model enum 3200 is SDK WDDM 3.2. Node 2 returned friendly name `Compute 0`
with raw engine type 0; the PDH-engine join remains unqualified.

| Qualified raw fields | Reported values and documented units |
| --- | --- |
| Node 2 frequency; normal/overclocked maxima | `653000000`; `2900000000` / `2900000000` Hz |
| Adapter memory frequency; normal/overclocked maxima | `1000000000`; `1000000000` / `1000000000` Hz |
| Power; temperature; raw override | `37` tenths of a percentage (3.7%); `440` deci-Celsius (44°C); raw byte `1` |
| Legacy dedicated video/system/shared segment sizes | `68535660544` / `0` / `34170374144` bytes |
| Local/nonlocal/nonbudget group sizes | `102706034688` / `0` / `59773358080` bytes |
| Adapter maximum memory/PCIe bandwidth caps | `0` / `28368000000` bytes/s |

The success-qualified raw voltage, transition-latency, transfer-amount, fan and
temperature-threshold fields were 0. These raw driver returns are retained as
reported; they do not independently qualify a physical sensor interpretation,
provider interval or policy. The overall host QPC span was 13,686 ticks at 10 MHz
(1.3686 ms), which is one acquisition bound, not a collection-overhead distribution.
The 20-second outer stage deadline completed normally; the receipt records owned
job closure, no pending cleanup and a stopped reserve monitor, with observed
minima 27.219745635986328 GiB physical and 119.82342147827148 GiB commit headroom.
Termination of a blocked synchronous driver was not exercised.

This result establishes buffer availability and the stated native identity for
one acquisition. Fabric-clock observation/hold proof, frequency-hold setter use,
GPU/NPU-overlap qualification, private policy readback, settings changes, tuning
and throughput-cause claims all remain false in the raw sample. It does not
establish loaded-state behavior, historical sensor pairing, BIOS UMA reservation
or an evidence-backed operating-state adjustment. The source author only read and
hashed ROOT's retained results; no further acquisition or matrix was performed.
