# Halogen 0.18.0 phase clock audit, 12 October 2026

**The saved 32K fixed2/adaptive cohorts lack phase-local independent clock evidence. They do not demonstrate a 0.18.0 timing defect.** Their source intentionally rejects a phase instrument and preserves API phase timings as unqualified observations. Offline inspection closes the exact 0.18.0 native phase producers, request moves and normal image chrono provider; it cannot recover the missing runtime timestamps.

This audit read saved files and used native Windows Python and Windows LLVM to decode bounded ELF functions. Neither an ELF nor a native library was loaded or executed. No inference, health, accelerator, WSL/Docker, process inspection, lifecycle, credential or continuation-state operation occurred. Production sources and saved raw evidence were not changed. The audit covers the pinned **0.18.0** binary only; it supplies no mapping or qualification for 0.18.1.

## Saved evidence and the qualification decision

The [comparison packet](../benchmarks/halogen0180-fixed-adaptive-natural16k-20261011.json) has SHA256 `735fbbee2742e548ebaf38e501bd0c236d130721131ba42b2ac2991792450883`. The [acceptance report](halogen0180-acceptance-comparison-20261011.md) correctly separates whole-request QPC rates from native phase observations.

The cohort root, relative to the workspace, is:

```text
server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0180-adaptive-option-20261011/
```

Its `client/measure.py` (SHA256 `ddfc64739e365dd0e25632019ac56c90dea6ec33596f0466c2bf6c8e563c8341`) records QPC before the nonstream HTTP request and after receiving its entire response at lines 363–366. Lines 201–202 reject `manifest.phase_clock_instrument`; lines 125 and 268 retain `api_phase_clock_qualified=false`. Offline qualification verifies raw-response hashes, QPC subtraction, output/count identity, memory receipts and exclusive completed-request accounting. Passing those checks does not mean the phases were independently timed. Both saved `qualification.json` files explicitly retain the false phase-clock flag. No phase RAW journal or captured native D records accompany either cohort.

The exact upstream `halogen0180-normal-bridge-preparation-20261011/artifacts/tools/serve_api.py` has SHA256 `1cdd97732df7819c203e38fb4531546e2308f6ea29c4871ca12a7fa9ffef9902`. Lines 1282–1284 parse D fields 5/6 into `prefill_ms`/`decode_ms`; lines 2942–2953 publish those native durations and count/duration rates. Python does not retime these phases. The user-stop proportional Decode adjustment at line 2751 applies only after a stop match; the retained responses finish with `length`, actual 16,384 prompt / 128 output tokens and no cached, restored or reasoning tokens.

The following values come from unchanged measured raw responses and QPC receipts. The last column is only an arithmetic closure diagnostic.

| Arm / rep | QPC whole request s | API Prefill ms | API Decode ms | API phase sum s | QPC minus phase sum ms |
|---|---:|---:|---:|---:|---:|
| fixed2 / 1 | 16.8294892 | 13516.6 | 3226.4 | 16.7430 | 86.4892 |
| fixed2 / 2 | 16.6436045 | 13223.1 | 3315.1 | 16.5382 | 105.4045 |
| fixed2 / 3 | 16.5239806 | 13193.1 | 3239.7 | 16.4328 | 91.1806 |
| adaptive / 1 | 19.4518586 | 15914.6 | 3442.3 | 19.3569 | 94.9586 |
| adaptive / 2 | 20.0762097 | 16272.9 | 3708.6 | 19.9815 | 94.7097 |
| adaptive / 3 | 19.2205203 | 15483.0 | 3650.3 | 19.1333 | 87.2203 |

Measured sums/QPC range `0.993666967..0.995462126`. Excluded warmup residuals are 76.7617 ms fixed2 and 473.1263 ms adaptive. These observations are consistent with work outside the native phase intervals, but do not establish its precise cause. HTTP transfer, tokenization, detokenization, scheduling and phase gaps are not independently separated here. A near-equal phase sum and HTTP duration cannot prove either phase's clock slope; different phase distortions and outside work can produce the same sum. No corrected timing, normalization factor, reconstructed phase rate or rescaling was calculated.

Historical guest MONOTONIC/RAW scale discontinuities are demonstrated in [0.17.2's clock review](halogen0172-hc6-registration-route-20261009.md) and [0.17.3's SDMA screen](halogen0173-normal-sdma0-20261009.md). They explain the need for independent phase evidence. They do not demonstrate that this 0.18.0 cohort had the same defect. The earlier [failed object-pointer pairing](../benchmarks/halogen0173-phase-pairing-v1-rejected-20261009.md) is also a separate, diagnosed instrument defect; it is not a failure observed in these uninstrumented 0.18.0 requests.

## Exact current-version native map

Engine: `halogen0180-normal-bridge-preparation-20261011/artifacts/flash_serve`, 27,078,280 bytes, SHA256 `71d72b283f0937aec024baf6b6ec919e27dacd57cfc043832468ffdd603c8e08`. Image: `ghcr.io/peonist-ai/halogen-flash-server@sha256:de3b47d2e5f24f98a38ba5fb66b0075b0cd8a3219c38917c78fb4bbeb42b88d9`.

The image imports `_ZNSt6chrono3_V212steady_clock3nowEv` under `GLIBCXX_3.4.19`, needs `libstdc++.so.6` and has RUNPATH `/usr/local/lib/python3.12/site-packages/_rocm_sdk_devel/lib`. Its independently joined PLT/GOT relocation is PLT `0x19cd820`, GOT `0x19d4f38`, x86-64 JUMP_SLOT type 7, addend zero. The divisor at `0x13de0` is exactly 1,000,000.0. The D format at `0x15043` begins `D %ld %s %d %d %.1f %.1f`; native protocol phase values are rounded to 0.1 ms before Python computes the published rates.

| Phase endpoint | Call / return RVA | Native value and identity |
|---|---|---|
| Prefill begin | `0x1814a3a` / `0x1814a3f` | R14 Prefill object; signed ID at +0; real RAX saved at caller SP+0x18 |
| Prefill end | `0x1814e41` / `0x1814e46` | Same Prefill; subtract saved SP+0x18 start; double ns/1e6 added at Prefill+0x450 |
| Decode begin | `0x1817136` / `0x181713b` | R14 Request; real RAX saved at Request+0x1c8 |
| Decode end | `0x181b0ad` / `0x181b0b2` | R14 Request; RBX carries Request+0x1c8 start; real-end minus RBX gives ns/1e6 |

The native Decode begin stores `n_gen=1` immediately before its timestamp, so the native API convention is `predicted_n / native Decode phase seconds`; it is not an isolated target-verifier or per-round cost. A future directly observed RAW phase rate must retain or explicitly distinguish this count convention. Both draft sources and other native Decode work remain inside the aggregate phase.

The terminal formatter reads signed Request ID at +0, prompt/generated counts at +0x54/+0x58, and Prefill double at +0x1c0. It subtracts Decode start at +0x1c8 and passes both phase doubles unchanged to `snprintf` at `0x181b267`.

All three Prefill-to-Request transfers are decoded in the complete main-handler FDE. The Request stack base is SP+0xa60; the store at SP+0xc20 is therefore Request+0x1c0. Primary transfer `0x1800070`, alternate `0x180013a`, and later transfer `0x180b037` read Prefill+0x450 and write this field. Prefill diagnostic starts at +0x4a8/+0x4b8 are copied from the original native SP+0x18 timestamp at `0x1814be5`; they remain distinct from the accumulated Prefill phase field.

Request moves preserve the signed ID through sixteen-byte +0 copies and the counts through sixteen-byte +0x50 copies. Constructor `0x1815fa9` and assignment `0x18186ee` invoke `memcpy` over exactly `[Request+0x1b8, Request+0x239)`, 0x81 bytes. Both eight-byte phase fields lie within this copied range. Native stride is **0x338**. Stack insertions at `0x18005ac` and `0x180b292` call append/growth `0x18176f0`; its direct append and reallocation paths move through the constructor, with every element advancing by 0x338. Terminal selection at `0x1813bd6..0x1813bed` selects the moved heap Request; formatter call `0x1813f5e` supplies that element to `0x181b040`. Assignment used in terminal vector compaction calls the mapped assignment function.

These layout changes rule out copying the old 0.17.4 hook RVAs or updating only its engine label: old Prefill+0x440, Request+0x1b8/+0x1c0 and stride0x330 differ. There is no global RVA-shift assumption in this audit.

The complete FDE-bounded source closure has eight functions, **107,803 bytes**, with the following exact body hashes. Twenty-three native instruction/dataflow windows are embedded in the helper, including the full 300-byte append/growth function; `--full` emits their exact bytes, bounds, file offsets and hashes.

| FDE RVA range, end exclusive | Body SHA256 |
|---|---|
| `0x17fc440..0x1812623` | `709765e9f505d3844fe72889339ead28a079287e01f56577f24e53cd6c21890b` |
| `0x1813bc0..0x18143b8` | `2a4e657ee2d86550fdb23bfa3f34b0610e028ba56226b605c0ada6379f75bcd8` |
| `0x1814a20..0x1815a6a` | `b9f0352236e9fc784206be52876bbd16e14151562e5f167609f40c98f0d014bc` |
| `0x1815c80..0x181620e` | `6d91b671106f44fefa869ebb384fbe77a22d55b93f71c50f66c89b18afe24b96` |
| `0x1816210..0x18175a5` | `c3abe9a82b2e9c05f15dd80453c91dae0798fcaedf36edbd599aa1e9d321ef47` |
| `0x18176f0..0x181781c` | `01aae15122af227eded0cdb91bf26755758dd0086c04cbe1b89e2fe693f887c4` |
| `0x1818170..0x1818a94` | `88d4c00f99dc9323f51ba1ca609f1d4680dcf7b19adf44d33c3ed238ac6ffd75` |
| `0x181b040..0x181b7c3` | `1259f3eabeab20127964a2ece7b68caa6e14e3260fa23c61af494074f875b550` |

## Normal chrono provider and the remaining runtime gap

The saved exact-image CPU loader result is `halogen0180-normal-bridge-preparation-20261011/root-provider-inspection/stdout.json`, SHA256 `9f164df22ce608a1aa5a05691191fc5cca0b332c749ec68ea87d8f95c4e7585f`; its owning image/closed-container receipt has SHA256 `a2e8f0cc902864ea7664f880ac4c051d854616a57007184d31e6cfd245f4c198`. That recorded closure pins `/usr/lib/x86_64-linux-gnu/libstdc++.so.6.0.33` to 2,497,768 bytes, SHA256 `972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00`.

The retained `server/.local/optimization9h-20261004/rocr-base-image-libs/libstdc++.so.6` is byte-identical. Its chrono symbol is at `0xd5490`, 39 bytes:

```text
f30f1efa4883ec18bf010000004889e6e8eb83fcff4869042400ca9a3b48034424084883c418c3
```

At `0xd5498`, it supplies clock ID **1**, Linux `CLOCK_MONOTONIC`; `0xd54a0` calls the independently joined `clock_gettime` PLT, then forms `seconds*1e9 + nanoseconds`. This closes normal-image implementation bytes and the saved isolated CPU loader's provider-file identity. It does **not** show the address actually bound to chrono by either benchmark engine process, exclude a lower-level clock interposer in that process, or measure its clock slope.

## Proposed passive observer and smallest next measurement

The current-version static map is complete for the inherited aggregate Prefill/Decode contract. A new **default-off, measurement-only companion** can reuse the 0.17.4 assembly ABI capture, exact versioned provider binding and move-safe pairing core, with fresh 0.18.0 pins and namespace. It must differ from the old duration-replacement instrument as follows:

1. Only the four mapped endpoint return RVAs may create phase records. Every chrono call invokes the exact real provider once and returns its original native RAX, including valid ends. Do not write Request/Prefill time fields, substitute `native_start+RAW_delta`, interpose broad `clock_gettime`, or alter unrelated native callers.
2. On each selected endpoint, read `CLOCK_MONOTONIC_RAW` immediately before and after that single real provider call. Retain both RAW reads and the native return. The two-read width bounds endpoint timing uncertainty. Bind the header to the actual mapped ELF, provider file/base/symbol address and exact code pins. A provider/binding mismatch, clock failure, dropped event or journal failure leaves the capture unqualified.
3. Prefill pairing requires the signed native ID plus unchanged Prefill object, caller SP, thread and saved native start. Decode pairing requires one unambiguous signed native ID and exact original native start; verify carried RBX and Request+0x1c8 at the end while allowing object relocation. Preserve duplicate, missing, ambiguous, reversed and leftover-pair rejection. Bind Prefill chunks to the completed Request+0x1c0 double.
4. Write a new fresh observer journal only. Preserve existing native D output, API raw replies, source evidence and historical journals. An offline companion verifier must compare native endpoint subtraction/accumulation to the moved Request fields, complete D records, API durations and counts by request ID/order, allowing only native D's documented 0.1 ms rounding. It separately publishes **directly observed** RAW Prefill/Decode durations and rates with endpoint uncertainty; it never rescales the unchanged API rates by an HTTP ratio.
5. Independently qualify guest RAW against host QPC over matched clock-sampling intervals, with handshake/read uncertainty. Native first-Prefill-to-last-Decode duration and HTTP duration have different endpoints; their ratio is not that calibration. Reject loss, contamination or excessive uncertainty. Observer overhead remains part of an instrumented measurement and cannot establish a clean serving gain by itself.

For each endpoint bracket, an elapsed RAW interval containing the native endpoints is bounded by `end_before - start_after` and `end_after - start_before`; sum the chunk bounds for Prefill. A direct before-to-before RAW duration may be reported alongside this uncertainty. With positive bounds, token-rate bounds are count/upper-duration and count/lower-duration. This is measurement uncertainty attached to new observed timestamps, not a reconstruction of old phases.

The **smallest discriminating hardware observation** is one isolated, bounded 16,384-input / 128-output native request after the new observer is pinned and enabled by root, under the existing request-entry/runtime guards, with all four endpoint types and every Prefill chunk captured, complete native D/API records, exact loaded-provider binding and independent RAW/QPC sampling. Use one excluded warmup first if a warmed phase-rate sample is intended and none already exists. It needs one arm, not another fixed2/adaptive series. Phase-local native/RAW ratios distinguish ordinary outside-phase overhead from native clock scaling; a Request/D mismatch instead locates a field/pairing or reporting defect.

A capture on the restored full262 Current4K service would qualify that new instrumented configuration only. It cannot retroactively qualify the old 32K/8K cohorts. A diagnosis specifically matched to those old settings requires the old fixed2 32K/8K profile and fresh owned admission; no such launch or measurement is requested or performed by this offline audit. Until independent stamps exist, trustworthy Prefill/Decode tok/s cannot be recovered from the saved HTTP receipts alone.

## Reproduction and verification

The [offline helper](../../scripts/benchmarks/audit_halogen0180_phase_clocks.py) has SHA256 `0bfdc542d98adbce334cf682ce94a000d6f8cc7a7ffc2a1f877348cd6e141002`. It validates all eight original responses/client pins, original API rate arithmetic, QPC subtraction, the eight FDE bodies, twenty-three byte windows, chrono PLT/version/divisor and saved image/provider receipts. The pure ELF parser is itself pinned to SHA256 `671297d02e798107827e5b51def19a288479a8c733c41b2221854bc96af9eddd`. The source disassembly tool was Windows LLVM SHA256 `feaaf3874824cd550505b9be47ab6519240301f0ea80562d2c9720fc98fef5d1`; the helper needs no compiler or disassembler at runtime.

```powershell
& 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe' -B 'C:\Projects\strix-alloy-clean\scripts\benchmarks\audit_halogen0180_phase_clocks.py' --self-test
& 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe' -B 'C:\Projects\strix-alloy-clean\scripts\benchmarks\audit_halogen0180_phase_clocks.py' --full
```

Verification observed the qualification-regression test fail before implementation, then **8/8 offline tests pass**, followed by a complete real-file audit exiting 0. Fixtures reject raw/client, QPC, native-byte and rate tampering; even a perfectly equal HTTP/phase sum cannot create qualified RAW rates. The real-file audit reports `native_static_pins_verified=true`, `api_phase_clock_qualified=false`, and the four still-missing runtime evidence classes. This audit does not implement, build, activate or runtime-qualify the proposed observer.
