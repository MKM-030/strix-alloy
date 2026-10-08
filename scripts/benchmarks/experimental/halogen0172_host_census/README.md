# Halogen 0.17.2 HIP host-call census

Experimental observer sources and CPU analyzers for the sealed Linux x86-64
Halogen 0.17.2 engine. The observer measures host API calls for attribution.
It makes no serving-speed or GPU-busy-time claim. The recorded investigation is
in [the research report](../../../../docs/research/halogen0172-host-call-census-20261008.md).

`host_census.c` is the exact source used by the pinned private build.
`analyze_host_calls.py` is copied verbatim. `analyze_direct.py` changes only its
two package-relative source paths. `source-provenance.json` pins the original
and copied sources, private build library, raw export, and analysis references.
This package contains source and documentation; captured data contents, model
files, compiled libraries, and SDK probe sources are excluded.

## Build and activation

Build with Linux x86-64 GCC and libc; no HIP SDK headers are required:

```sh
gcc -std=c11 -O2 -shared -fPIC -Wall -Wextra -Werror -pthread \
  host_census.c -ldl -o libhalogen0172-host-census.so
```

Observation defaults off. Root owns compilation, hardware access, server/API
requests, profiling, lifecycle, and live exports for this investigation. Root
must use the normal managed lifecycle to prepend this library to the existing
`LD_PRELOAD` chain and pass `HG0172_HOST_CENSUS_PATH` as an absolute, fresh output
filename. Logging activates only when `/proc/self/exe` exactly equals
`/usr/local/bin/flash_serve`. `O_CREAT|O_EXCL` prevents replacing an existing file.

The six hooks are `hipMemcpy`, `hipMemcpyAsync`, `hipDeviceSynchronize`,
`hipStreamSynchronize`, `hipModuleLaunchKernel`, and `hipLaunchKernel`. They pass
all arguments and HIP results through `dlsym(RTLD_NEXT, ...)` and preserve errno.
Logging failures disable observation. An unavailable forwarding target emits a
short diagnostic and exits 127 because no faithful HIP result is available.
Existing preload-internal `RTLD_NEXT` calls bypass this prepended observer, so
the capture does not establish whole-runtime coverage.

## Raw contract and CPU analysis

Version 1 is little endian: a 64-byte `<8sIIIIQQIIQQ` header followed by 96-byte
`<10QiiII` records, with no footer. Header fields are magic `HGHC0172`, version,
header size, record size, clock ID, main load base, file cap, PID, reserved32,
flags, and reserved64. Flags are 7; clock ID 7 is `CLOCK_BOOTTIME`. The maximum
file size is 64 MiB, including the header (699050 whole records).

Record fields are sequence, start_ns, end_ns, caller_rva, tid, size_bytes, src,
dst, stream, function, result, direction, api, and flags. API IDs follow the six
hooks listed above, numbered 1 through 6. Copy direction preserves the original
HIP kind (0, 1, 2, 3, 4, or 1024); noncopies use -1. Nonapplicable fields are zero.
The caller is the return-address RVA within cached main-executable executable
`PT_LOAD` ranges; load base zero is valid. External callers use `UINT64_MAX` and
record flag 1. Sequence starts at 1 and follows successful append order after
HIP returns. Timing brackets the original HIP call; record writes follow its
end timestamp. Addresses are numeric metadata; pointed-to bytes and kernel
argument contents are never read.

Run the CPU-only analyzer with explicit private inputs and a separate output
prefix using Python 3.10 or newer:

```sh
python analyze_direct.py --trace /private/host-census.bin \
  --boundaries /private/request-boundaries.json \
  --output-prefix /private/analysis/host-direct-analysis
```

Request boundaries must explicitly share calibrated
`linux_CLOCK_BOOTTIME_ns`; a valid phase split is needed for prefill/decode
attribution. `analyze_host_calls.py` also accepts `--csv`, `--boundaries`, and
`--output-prefix` for profiler HIP host CSV data. Both analyzers use the standard
library and retain raw inputs. The direct reader reports malformed records,
sequence gaps, partial tails, and cap saturation. A live snapshot has no
independently established completeness; host-duration sums may overlap, while
interval unions count covered elapsed time once.
