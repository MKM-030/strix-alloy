# Read-only ADLX capability and telemetry probe — 2026-10-04

The official ADLX interface works on the Radeon 8060S with the installed
`amdadlx64.dll` 1.5.0.124. The local helper compiled successfully and read five
idle samples. GPU clock, temperature, reported GPU power, usage, and memory
telemetry are usable. **All six queried GPU tuning capabilities are unsupported.**
No clock, voltage, power, fan, driver, BIOS, or system setting was changed.

## Implementation and reproduction

- Source: `scripts/benchmarks/halogen_adlx_probe.cpp`.
- Build/run wrapper: `scripts/benchmarks/halogen_adlx_probe.ps1`.
- Official SDK v1.5 commit: `d9f04a9bba022d6cf6333f005dd540b4ad19fb63`.
- App-local SDK, build files, executable, and raw output are under the Git-ignored
  `artifacts/halogen-adlx/build/` directory. No SDK or package was installed globally.
- Existing MSVC 19.44.35228.0 and Windows SDK 10.0.26100.0 were used through CMake
  and Visual Studio 2022 Build Tools. The executable uses the static C++ runtime.

```powershell
& .\scripts\benchmarks\halogen_adlx_probe.ps1 -Samples 5 -IntervalMs 1000
```

To build only, add `-BuildOnly`. For later observation during an independently
authorized workload, the executable can be invoked directly without rebuilding:

```powershell
& .\artifacts\halogen-adlx\build\out\Release\halogen_adlx_probe.exe --samples 60 --interval-ms 1000 |
    Set-Content -Encoding utf8 .\artifacts\halogen-adlx\build\results\adlx-workload.ndjson
```

The probe follows AMD's [PerfGPUMetrics C++ sample](https://gpuopen.com/manuals/adlx/programming-with-adlx/adlx-samples/cplus-samples/performance-monitoring/perfgpumetrics/):
initialize ADLX, enumerate GPUs, query supported metrics, then call
`GetCurrentGPUMetrics`. It guards every sensor read with the corresponding support
query. Current metrics require no history tracking; the helper does not call
tracking start/stop, sampling setters, tuning setters, resets, or tuning interface
getters. Official [v1.5 headers and helpers](https://github.com/GPUOpen-LibrariesAndSDKs/ADLX/tree/d9f04a9bba022d6cf6333f005dd540b4ad19fb63/SDK)
define the interfaces and ABI; there is no guessed ctypes layout.

## Observed result

Run started at `2026-10-04T01:02:46.6702830Z`. One GPU was enumerated:
`AMD Radeon(TM) 8060S Graphics`, device ID `1586`, reported dedicated VRAM
`65536 MB`. Initialization, services, metrics support interfaces 1/2/3, all five
current sample requests, all supported sensor getters, and termination returned
`ADLX_OK (0)`. The five samples spanned approximately four seconds with no large
engine or NPU workload launched by this probe.

| Metric | Support | Observed idle values | Reported range |
| --- | --- | --- | --- |
| GPU usage | Yes | 0% | 0–100% |
| GPU clock | Yes | 619–621 MHz | `ADLX_NOT_SUPPORTED (12)` |
| VRAM clock | Yes | 812–1000 MHz | `ADLX_NOT_SUPPORTED (12)` |
| GPU temperature | Yes | 40–42 °C | `ADLX_NOT_SUPPORTED (12)` |
| GPU power | Yes | 12–34 W | `ADLX_NOT_SUPPORTED (12)` |
| Dedicated VRAM used | Yes | 947 MB | 0–65536 MB |
| Shared GPU memory used | Yes | 107 MB | 0–32587 MB |
| NPU frequency | Yes | 0 MHz | `ADLX_NOT_SUPPORTED (12)` |
| NPU activity | Yes | 0% | `ADLX_NOT_SUPPORTED (12)` |
| GPU hotspot / intake / memory temperature | No | Not read | Not queried |
| Total board power / GPU voltage | No | Not read | Not queried |
| Fan speed / fan duty | No | Not read | Not queried |

The ADLX `GPUPower` value is preserved as reported; this run does not establish
whether that sensor's accounting on this APU equals a particular package or GPU
rail. Total board power is unsupported. These idle readings are instrumentation
validation, not an inference-performance result or a thermal-limit diagnosis.

All six [GPU tuning support queries](https://gpuopen.com/manuals/adlx/adlx-sdk-references/adlx-interfaces/gpu-tuning/iadlxgputuningservices/)
returned `ADLX_OK (0)` with `false`: automatic tuning, preset tuning, manual GFX,
manual VRAM, manual fan, and manual power tuning. `IsAtFactory` returned
`ADLX_OK (0)` with `false`. That flag alone does not establish which setting may
differ from factory, particularly when all tuning domains are unsupported. No
tuning was attempted or performed, and unsupported telemetry ranges must not be
treated as writable clock/power limits.

The NPU readings establish that these ADLX telemetry getters work; they do not
establish a supported NPU inference path. The raw ADLX timestamp is preserved,
but its observed values do not resemble Unix epoch milliseconds. Use the probe's
separate `requested_epoch_ms` / `completed_epoch_ms` fields to align host workload
timing; do not interpret `adlx_timestamp_ms` as Unix epoch time in this run.

## Evidence and hashes

Raw NDJSON:
`C:\Projects\strix-alloy-clean\artifacts\halogen-adlx\build\results\adlx-idle-20261004.ndjson`.
It contains one run-context record, one initialization record, nine API-result
records, one GPU record, sixteen metric-support records, seven tuning-support
records, and five sample records. Each line was parsed successfully with
PowerShell `ConvertFrom-Json`. Build/run exit code was zero and ADLX termination
returned zero. The build and raw paths were confirmed Git-ignored. No test suite
or additional workload was run.

| Item | SHA256 |
| --- | --- |
| Official pinned SDK archive | `2E0B3527C432B3F4A4EE7EA3974B266BAE208282684A451BCD347684BEC94312` |
| C++ probe source | `223920311CFFAAAAF2E23680A5209E80E195DF6B555793B6CBAE0997BDEB2801` |
| Measured PowerShell wrapper | `F0141D78B286E566167A5D9F3E41260EAD29ADC4338091C5E161DDBE67F49FC7` |
| Compiled executable | `0AB11B6E8E2BB94D901AE32E9C1249775386FC218EDB1DD1747813A56D18D9BC` |
| Raw five-sample NDJSON | `DBCCEAD98DDFA2954E6F33D144DBCAEC182182D3B3D34525621020D88682F6E7` |
| System32 ADLX DLL 1.5.0.124 | `AD82900579AA59A75668FC04BE2A8F38C706F9FD94058F52081A0B87526B11A2` |

The wrapper's `run_context` records the System32 DLL file metadata. The official
helper loads the named installed ADLX library using its standard Windows loader;
this probe does not replace or copy the driver DLL into the application directory.

Review then changed only output creation to `FileMode.CreateNew`, so an explicit
output path cannot overwrite prior evidence. The original measured wrapper hash
above remains retained; the final wrapper hash is
`E1554E0B4B72F92A6926A37A4FC5010FCE5B8F824415214974B29F787692DE48`.
PowerShell parsing passed after that change. The C++ source, executable and five
idle readings were not changed or rerun.
