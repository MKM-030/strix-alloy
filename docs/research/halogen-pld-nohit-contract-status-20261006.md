# Offline no-hit consumer contract status, 6 October 2026

**The bounded offline trusted-caller consumer passes the final recorded synthetic host CPU qualifier. Live integration and serving remain unqualified and default off.** The source now supplies the previously missing finite no-hit semantic contract; it supplies no installed native consumer or ready producer. New serving Prefill, Decode, acceptance and every associated delta are **null (unmeasured), never zero** in the [machine-readable report](halogen-pld-nohit-contract-status-20261006.json).

This independent report reads the [contract README](../../scripts/benchmarks/halogen_pld_nohit/README.md), [distinct source review](../../scripts/benchmarks/halogen_pld_nohit/REVIEW.md), source, retained results and logs. It recomputes SHA256 values and checks references. It executes no new compiler/harness, model/provider, GPU/NPU, WSL, serving request or process lifecycle action and performs no staging or commit. Only this report and its JSON companion are written; the source review is preserved. Inspection context is branch `main`, HEAD `d6fc1d6971f4d671b49306d17eeba37fbd79d947`. The no-hit source directory was untracked then, so HEAD is context rather than a claim that these bytes were committed.

## Recorded RED and final GREEN

| Evidence | RED, 07:39:42 | Final GREEN, 07:44:15 |
|---|---:|---:|
| Compiler exit | 0 | 0 |
| Harness exit | 1, expected | 0, expected |
| Behavior checks failed | 38 | 0 |
| Contract groups | 4 | 4 |
| All owned jobs recorded closed | true | true |
| Receipt errors | none | none |
| Minimum available physical bytes | 33,876,021,248 | 33,919,729,664 |
| Minimum commit headroom bytes | 132,485,206,016 | 132,521,857,024 |
| Maximum recorded sample gap, seconds | 0.2654372999968473 | 0.26561770000262186 |

The [RED receipt](../../scripts/benchmarks/halogen_pld_nohit/_artifacts/20261006-073942-red-e2e4cec4/result.json) and [stdout](../../scripts/benchmarks/halogen_pld_nohit/_artifacts/20261006-073942-red-e2e4cec4/harness.stdout.txt) preserve `four contract groups: FAIL (38 failed checks)`. The [latest GREEN receipt](../../scripts/benchmarks/halogen_pld_nohit/_artifacts/20261006-074415-green-d739d803/result.json) and [stdout](../../scripts/benchmarks/halogen_pld_nohit/_artifacts/20261006-074415-green-d739d803/harness.stdout.txt) preserve `four contract groups: PASS (0 failed checks)`. The intermediate 07:40:42 GREEN directory is not used as the final source receipt.

Both recorded builds use the existing MSVC 14.44.35207 compiler with C++20, **`/W4 /WX`**, `/EHsc /O2 /MT` and `/INCREMENTAL:NO`; the [final command](../../scripts/benchmarks/halogen_pld_nohit/_artifacts/20261006-074415-green-d739d803/compile.cmd) records the flags. Compile and harness stderr files are empty. The guarded launcher requires **22 GiB** physical and commit reserves before launch/resume and **18 GiB** continuously, with requested 250 ms sampling and 90/10-second compiler/harness deadlines. Both receipts record all owned compile/harness jobs closed and no errors. These are retained receipts; this reporting pass does not fault-inject the attached recovery-owner cleanup path or inspect current processes.

The four groups check stock LEA/zero-count continuation, malformed packet and caller/publication truth, exact one/three-ID writes with canaries and allowance, and stale epoch/one-shot/exhausted-ledger decline. Historical child identities and byte-level reserve observations are retained in JSON. The older RED receipt's `hardware_executed=false` field does not mean no CPU work occurred: its owned compiler/harness records and stdout show the host run.

## What the source contract establishes

The seven displaced bytes at RVA `0x172d3bd` are `48 8d 85 e8 01 00 00`. Every absent, disabled or declined packet changes only saved RAX to modular `RBP+0x1e8`, preserves saved flags and other supplied frame/ledger data, and resumes stock at `0x172d3c4`. The harness also compares the retained store/zero-count/TEST branch continuation without assigning meaning to architecturally undefined AF.

A successful packet is fully checked before mutation, has `1 <= n <= min(3,B)`, writes exactly `4*n` ID bytes at original outer `RSP+0x360`, sets saved RBX=n, records one birth/epoch/round and returns `0x172e95f`. No oversized packet is truncated; no decline consumes or evicts the finite 64-entry ledger. The pinned [source review](../../scripts/benchmarks/halogen_pld_nohit/REVIEW.md) establishes that this native join executes its own LEA and `RSP+0x38` store, then reaches the original opening comparison and target verifier through the required no-constraint continuation. This report does not repeat a fresh disassembly control-flow audit.

The consumer is default off, fixed storage and absent from engine call sites. It has no allocator, callback, lock, wait, retry, runtime, transport or drafter launch. The existing hit-only Python selector retains its separate stock-count contract.

## Trust and remaining boundaries

The fixture deliberately fills opaque digest bytes with `0xa5`; those bytes are **not a valid HMAC**. The consumer performs no cryptography. Authentication of the complete header and ID body, integrity-key trust, immutable owned publication and its memory ordering belong to a trusted upstream caller. Epoch is separate trusted envelope truth because the wire lacks an epoch field. Boolean facts assert that qualification; they do not create it.

The harness compares synthetic GPR/RFLAGS data, all **896 stack bytes** and a **1,024-byte opaque extended-state image**. Equality of that array is not real XSAVE capture/restoration, native pointer lifetime, actual register/stack preservation, unwind/signal behavior, indirect-entry exclusion or atomic installation proof. Reset/epoch/lifetime synchronization, authenticated transport/publication, sufficiently early independent ready proposals and complete authoritative-output handoff also remain unqualified. The final GREEN receipt records host CPU harness execution, no GPU/NPU or WSL execution, and no loaded native engine. It establishes no native acceptance or serving measurement.

## CPU, GPU and NPU placement

| Placement | Assessment |
|---|---|
| CPU consumer | Keep this tiny bounded host branch work on CPU: at most 236 packet bytes and 64 ledger entries. Device dispatch/synchronization has no demonstrated benefit. This is a placement assessment, not a timing measurement. |
| GPU/Vulkan proposer | A separate independent drafter must establish useful proposals already ready at the native boundary, with complete transport/readiness and contention costs. The matched recurrent snapshot API belongs to that separate Vulkan drafter. The consumer owns no snapshot or model runtime. |
| NPU proposer | An independent NPU route needs its own useful ready proposals, tokenizer/binding, publication and lifecycle qualification. The llama.cpp/Vulkan snapshot proof does not transfer to XRT/NPU; this contract establishes no NPU result. |

Mathematically identical target kernels preserve native acceptance decisions for the same proposal/input trajectory. Faster identical arithmetic or moving those kernels between devices alone cannot change native acceptance. Useful independent proposals can alter consumption opportunities and acceptance, which must be measured through the native route. The [snapshot feasibility design](halogen-recurrent-snapshot-adapter-feasibility-20261006.md) remains the source boundary for a separate drafter; this offline consumer result does not qualify a snapshot hardware run or connected serving producer.

| New serving measurement | Value | Associated delta |
|---|---|---|
| Prefill tokens/s | null — unmeasured | null — unmeasured |
| Decode tokens/s | null — unmeasured | null — unmeasured |
| Native acceptance | null — unmeasured | null — unmeasured |
| Complete time per committed token | null — unmeasured | null — unmeasured |

## Recomputed source and evidence pins

All eight final GREEN source/tool pins match current bytes, as do the independently reviewed source pins. The retained native ELF and disassembly pins also match. RED records earlier `seam_contract.cpp` hash `f972fb54866f39484535ae3f409844ebd2e39431154913f679510f06306d1f73` and launcher hash `b3805b58d526776debfe923a8326cd1e064af206bdba155cdbd6f4f2174cbe18`; these are historical receipt pins, not hashes of the current implementation. Both archived executable hashes match their receipts.

| Current source/reference | SHA256 |
|---|---|
| `scripts/benchmarks/halogen_pld_nohit/README.md` | `d0e5373870b2c70b21a3090ac3c21eee0b7d8bc7f725f3275439594453f8665d` |
| `scripts/benchmarks/halogen_pld_nohit/REVIEW.md` | `e1c1e801c8f2452543ecd1b91e75f0ddda22dd7fdbd162bbbab1b35eb1712798` |
| `scripts/benchmarks/halogen_pld_nohit/seam_contract.h` | `caa67ed65e991e2f8474e5ba16ae5c8a29cc74bc517d253fe95a330e152bc5f2` |
| `scripts/benchmarks/halogen_pld_nohit/seam_contract.cpp` | `c03d638baee63cf1d26c69a8cca19dd5c06d4cede60ae46150dbbdcbc2adf0f7` |
| `scripts/benchmarks/halogen_pld_nohit/contract_harness.cpp` | `240b923d075f6d872bcf96be771b7882f47aa58dd4048df1d1e99251bb4eaea5` |
| `scripts/benchmarks/halogen_pld_nohit/run_cpu_harness.py` | `2f8d2bde3e3d12056d0824c191f04e3a8811ce87d5737a5a3aa901b4aa60ebca` |
| `server/host_frames.py` | `417e33060ce6bc5b8f336f9e90282012a4a0e12475a13ad1dba20eec2df8bdf8` |
| `server/winjob.py` | `3d2db1c5c8ea3846152a0073dd4ed324a47ffd36ac63bf8f48cc52e39b0d4d4c` |
| `docs/research/halogen-recurrent-snapshot-adapter-feasibility-20261006.md` | `94fe739f97762c567edd010ea8e7e09c91cfd95348635354fe92948503839b0c` |
| `scripts/benchmarks/halogen_pld_proposal_wire.py` | `4d36783f6b0398199b22f53b40e6e25e0b8ed2b776b65bee1f5a6de62bc99ebb` |
| `server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt` | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| `backends/halogen-wsl2-0.16.2/.local/flash_serve` | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |

| Retained artifact | SHA256 |
|---|---|
| RED result | `bc749fa030697bad9966541205751aee9c49a48ca2c2c968e0c730ac20d167de` |
| RED harness stdout | `69d38cdc2f04183e6bbeafbe5e9dea699e06d2f717a377f6ac558a4d29010a11` |
| RED executable | `30938803d51e76221e3369c26800eecd8dbe90ce79ed3371d11d35c23d16bab0` |
| Final GREEN result | `038b0136039e94d917cf2100fe71071f77c4edbe4ee9f6d1d78cd6c89c05f813` |
| Final GREEN harness stdout | `38082819d9bb0199f4c90d4bad2915d406be8f7691818f375a0854d85bf569a1` |
| Final GREEN executable | `c95b42c04e283f1f3fe57a1f54fe78aadb4f3db2f192388c35530bc55fd34b8b` |

The JSON companion includes complete artifact hashes, compiler setup/tool pins, historical child identities and current hash comparisons. The next boundary remains qualification of actual native capture/restoration and installation, authenticated owned publication, reset/epoch/lifetime ownership, early independent readiness and authoritative-output handoff. The serving decision stays off.
