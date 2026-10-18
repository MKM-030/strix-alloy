# Halogen 0.18.1 passive phase clock source audit, 12 October 2026

**The actual 0.18.1 aggregate Prefill/Decode map and default-off passive observer source are complete. No observer build, actual engine stamps, live engine-provider binding or phase-rate qualification is established.** Root's separate normal-product CPU build is not an observer build or a serving phase measurement.

This agent read extracted evidence and decoded actual ELF functions with pinned native Windows LLVM. It did not use WSL/Docker, access devices/models/credentials, load Linux code, call serving/health APIs, build the observer or change production/installed configuration or STATE. All new files belong to [the source packet](../../scripts/benchmarks/experimental/halogen0181_phase_clocks/README.md).

## Independent current-version map

Root-extracted engine is 27,096,728 bytes, SHA256 `d946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab`, from image `ghcr.io/peonist-ai/halogen-flash-server@sha256:f0b39c8908f9897f27ab0a64e964c775e136a7cf7a1bafeb4de0c6d5d1e07e29`. Extraction root is `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0180-normal-bridge-preparation-20261011/halogen0181-extracted-20261012/`.

The clock symbol was joined independently through the actual PLT/GOT relocation: `steady_clock::now`, GLIBCXX_3.4.19, PLT `0x19d1fc0`, GOT `0x19d9710`, JUMP_SLOT7/addend0. There are 207 raw E8 candidates for this import, versus 181 in 0.18.0; these include unrelated native profiling/scheduling clocks. Only four verified phase endpoints are selected. Actual FDE-bound disassembly confirmed each instruction boundary. Eight complete functions total 111,744 bytes; 26 exact windows cover phase writers, all three transfers, three append paths, identity/count/scalar movers, heap selection, D formatting and `snprintf`. [Static map](../../scripts/benchmarks/experimental/halogen0181_phase_clocks/static-map.json) and `evidence/` preserve their bounds, bytes and SHA256 hashes; no global RVA shift or prior-version location is assumed.

| Endpoint | Call / return RVA | Native contract |
|---|---|---|
| Prefill begin | `0x181870a` / `0x181870f` | R14 Prefill, signed ID+0, native RAX saved at caller SP+0x18 |
| Prefill end | `0x1818d5b` / `0x1818d60` | Same object; native-end minus SP+0x18, ns/1e6 accumulated at Prefill+0x458 |
| Decode begin | `0x181a8d7` / `0x181a8dc` | R14 Request, native RAX saved at Request+0x1c8 |
| Decode end | `0x181e7bd` / `0x181e7c2` | R14 moved Request, RBX carries +0x1c8 native start; native ns/1e6 |

The Prefill accumulator changed again from 0.18.0's +0x450. New Request fields remain Prefill double+0x1c0, Decode start+0x1c8, signed ID+0, prompt/generated counts+0x54/+0x58, stride 0x338. The exact1,000,000.0 divisor is at `0x13df0`.

Three transfer loads at `0x180e0c0`, `0x180e229` and `0x180c517` move Prefill+0x458 to stack SP+0xca0; Request base is SP+0xae0, giving Request+0x1c0. Constructor `0x18171a0..0x181772e` and assignment `0x181b7c0..0x181c0e4` preserve ID/counts and memcpy exactly `[+0x1b8,+0x239)`, 0x81 bytes, including both phase fields. Append/growth `0x1817730..0x181785c` advances0x338 and uses the constructor for direct append and all relocation elements. All three main-handler append calls are mapped: `0x1800665`, `0x180c70f`, `0x180ea3d`. Terminal selection `0x18161b6..0x18161cd` selects the moved heap Request and call `0x181656d` passes it into D formatter `0x181e750..0x181eed3`.

D reads the native fields unchanged, formats phases with `%.1f` (0.1ms rounding), and calls `snprintf` at `0x181e977`. The new D literal is at `0x15067`. Decode start occurs after native `n_gen=1` is stored; the rate-count convention includes this native first-token policy. Aggregate Decode is not a target-verifier or isolated neural-drafter timer.

That static count initialization does not prove whether first-token generation lies before or after the timing boundary, or whether D/API count128 spans128 operations wholly inside Decode. This revision passively records Decode-begin/end native counts and their delta. Phase count scope remains unqualified until minimal actual runtime proof closes the first-token boundary; neither128/t nor127/t is assumed valid.

Root's exact-image CPU provider receipt and actual library bytes independently bind `libstdc++.so.6.0.33`, 2,497,768 bytes, SHA256 `972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00`. Its 39-byte chrono implementation at `0xd5490` calls `clock_gettime(1)` and forms ns: normal Linux `CLOCK_MONOTONIC`. The new CPU receipt includes actual `dladdr` of the chrono symbol and records a closed, removed CPU container without model/device access. This is the CPU image-provider binding, not a loaded model-engine observation. Complete receipt/output hashes and copied receipt contents are in the static map.

## Passive companion behavior and reporting limit

`phase_clock.c` calls the exact real chrono provider once, records direct RAW reads before and after it, then samples native identity/count fields. Every path returns original native RAX; no native timestamp, duration, divisor, counter, arithmetic or kernel is written or substituted. Default-off/unrelated calls simply forward. Enabled initialization validates exact ELF file SHA/size, mapped instruction windows, real symbol/version/address, actual provider file bytes and provider function code. Readonly native access follows the current ABI.

The bounded registry retains request epochs and completed signed IDs for the entire capture. Concurrent different objects with the same ID, reused completed IDs, duplicate/open overlaps or ambiguous pairing are errors rather than overwritten ownership. Decode can move objects while retaining the exact signed ID/epoch/native-start contract; carried RBX and Request+0x1c8 must match. Runtime capture failure disables observation and keeps native returns; the incomplete/error evidence is rejected.

`observe_api_done.py` is explicitly default-off and binds the actual API file/hash supplied by root. Its wrapper calls the stock D parser exactly once, journals copied numeric D parts and returned counts/durations afterward, and returns the same result object without mutation. Diagnostic failure is exposed through `failed/error` while preserving that object. Root must bind the actual API callable in a measurement-only wrapper; this source packet does not patch or launch the API.

Record/close now share one lock and recheck the enabled/failed state inside it. Arming I/O failures stay inside the diagnostic failure boundary; the API arm must be fresh and later owned, empty, regular0600 with the same device/inode as the phase activation. A successful completion record is required, alongside root's post-close `failed=false` receipt.

`verify_phase_journal.py` rejects missing/torn/dropped/error events, incorrect nonce/provider/source contracts, native-return changes, ownership collisions, RAW reversal, moved-start/scalar inconsistencies and native D identity/order/count/duration mismatch. It preserves direct observed phase duration bounds and partial internal overhead. **It emits no tok/s and leaves clean serving rates false.** Internal costs omit wrapper/forwarded-call overhead, the second log write/exit and API companion costs.

The revised reader compares the actual expected API source hash, copied D frame/reason, completion and shared arm identity, and retains the Prefill object's ownership across sequential chunks. Its optional root-produced actual capture receipt binds final journal hashes, signed ID/epoch/counts, source/profile pins, saved request/reply byte hashes and full-response client QPC. Matching journals alone establish consistency; actual artifact coupling does not itself grant RAW/QPC calibration, overhead, phase count scope or rates. Receipt recording provenance remains root-reviewed.

Before any separately reviewed instrumented rate claim, root must complete [the exact overhead protocol](../../scripts/benchmarks/experimental/halogen0181_phase_clocks/OVERHEAD-PROTOCOL.md): same-workload stock/observer/stock, one excluded warmup plus three measured requests each (12 total), complete request QPC and output/source/profile bindings, phase-native/D/RAW closure, and independent matched RAW/QPC calibration with 0.1% uncertainty gates. Report all control/B times, drift and measured instrumentation effect; do not subtract a fitted overhead or rescale old API phases. One isolated paired request can diagnose phase clock scaling but does not complete the overhead protocol or establish rates.

## Verified source delivery

The saved source packet had15 offline fixtures. This revision adds API pin, copied frame/completion, sequential Prefill object collision, actual saved-byte/QPC receipt coupling and arm-I/O failure cases. **One fresh full run passed20 tests** using the workspace Windows Python with `-B` (exit0,0.024s). All fixtures use synthetic CPU/file-only data. The root-owned `core_host_test.c` additionally exercises the actual C producer under mock syscalls for RAX preservation, one real call, moves, reused IDs, off/unrelated bypass, RAW failure and short writes; it was **not built or run by this agent**.

`source-pins.json` freezes the package. `verify_source.py` performs read-only file/FDE/window/provider revalidation without rerunning the map, invoking a compiler/disassembler or loading native code. Observer compile/link, C mock execution, exact measurement API hookup, live binding, phase stamps, overhead cohort and calibration remain root-owned work; none is implied by these offline fixture/source checks.

The exact root-owned GCC13.3.0 recipe is in [CPU-BUILD.md](../../scripts/benchmarks/experimental/halogen0181_phase_clocks/CPU-BUILD.md). Root's normal0.18.1 package is CPU-installed with runtime verification false; the current server-terminal available memory30.74GiB is below35GiB, so no capture is admissible yet. Gate failures alone supply no phase diagnosis. No production/STATE/configuration change, observer build, live capture or serving-speed claim is made by this source revision.
