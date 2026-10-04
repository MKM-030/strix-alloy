# Halogen upstream and GPU scout — 4 October 2026

Checked at 2026-10-03 23:49 UTC (4 October in Berlin), without launching an engine or exercising either accelerator. The strongest new experiment is a **persisted hipBLASLt plan tuned on this machine, followed by frozen-plan qualification**. No newer Halogen release or AMD driver in the processor's current official download channel was found. No hardware setting is selected.

The existing [0.16.2 investigation](../benchmarks/halogen0162-upgrade-20261003.md) already screened depths 1/3, chunks 8192/16384/32768, keep-trunk, DN_SCAN/DN_FUSED/ATTN_QS/FA_OPT/FLASH_MOE controls and cache policies. The [gather probe](../benchmarks/halogen0162-gather-20261004.md) already declined 32 threads after a warmed stock bookend. Repeating those screens supplies no new candidate. Persistent matmul plans and adaptive speculation do not appear in those completed experiments.

## Current upstream and installed drivers

GitHub's read-only [main commit API](https://api.github.com/repos/peonist-ai/halogen-flash-server/commits/main) and [tag API](https://api.github.com/repos/peonist-ai/halogen-flash-server/tags?per_page=5) both identify `v0.16.2`, commit `7f31bbd4021f217a1be9776bdb7304bcf8eca62d`, dated 2026-10-03 04:29:22 UTC. This is the release already pinned locally. Its changes concern additional small NPU models, NPU execution speed and cache eviction; the earlier GPU decode/prefill improvements are already included. [Pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/CHANGELOG.md).

Read-only CIM/registry inventory:

| Item | Installed observation | Current official comparison |
|---|---|---|
| OEM / BIOS | BOSGAME LIMITED, BeyondMax Series; BIOS 3.10 | No firmware action considered |
| Radeon 8060S | `32.0.32015.2008`, CIM driver date 2026-09-28 | Exact Driver Store version packaged by Adrenalin 26.9.2 |
| NPU Compute Accelerator | `32.0.20102.3930`, CIM date 2026-07-05 | Exact NPU version packaged by Adrenalin 26.9.2 |
| Active Windows power scheme | `REV:N Performance` | Balanced is also installed; neither was changed |
| Existing telemetry libraries | `amdadlx64.dll` 1.5.0.124; `atiadlxx.dll` 7.26.20.1616 | Read-only inventory only |

The [Ryzen AI Max+ 395 download page](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html) lists 26.9.2 WHQL Optional, released September 29, as its newest Windows package, with 26.8.1 Recommended also available. Its [release notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html) name both installed versions. The NPU date in those notes is May 7, whereas local CIM reports July 5; matching versions are the comparison, not an assumed date equivalence. There is no justified driver update in this channel.

## Candidate 1: persisted machine/workload matmul plan

The [supported flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md#L117) document a fresh tuning-file path with `HALOGEN_MATMUL_ALGOS=8`, followed by a clean stop. Later processes read the same decisions. Timing algorithms without persisting a file makes restart behavior dependent on timing. This is a numerical kernel choice: changed accumulation order can change near-tie tokens. The shipped plan's quality measurements do not qualify a new plan.

Static inspection of the actual `flash_serve` SHA256 `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` established:

- Plan reader RVA `0x18c4560`: `HGNTUNE3`, 52-byte header; bucket count at byte 8, hipBLASLt version at 12, WGP count at 16, and 32-byte architecture string at 20. Records are 64 bytes. Validate exact size `52 + 64 * bucket_count`, a bounded positive count, `gfx1151`, the observed runtime library identity and this SKU's WGP count.
- An architecture or hipBLASLt-version mismatch makes the engine discard the plan and regenerate. A WGP mismatch only warns and still loads; a frozen experiment should reject either mismatch. Native format acceptance is weaker than wrapper identity qualification.
- Getter RVA `0x18c6220` defaults/clamps small values to 1; no upper ceiling was established there. A trial interface should permit **only 1 and 8**, rather than copying the permissive native parser.
- Normal Matmul construction allocates a 128 MiB workspace (`0x18c4453`), and tuning uses the same workspace limit. This does not establish the entire tuning run's peak or incremental memory.
- Tuning routine RVA `0x18c6290` executes two warmups and four event-timed GEMMs per valid candidate, selecting the fastest. Selection is lazy when a shape is encountered. Training calls therefore carry extra work and cannot be throughput results. Total training latency remains unmeasured.

The [entrypoint](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/deploy/entrypoint.sh#L797) copies only the baked `/opt/halogen/flash-tune.plan` to a temporary file, preserving its mtime. Custom paths are left intact. The [0.11.10 fix](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/CHANGELOG.md) explains that `ALGOS=1` uses a library first choice for unseen buckets without timing; higher values record timed buckets. Absent/stale plans can still be written, so frozen qualification must refuse them before startup.

Current Alloy support needs a dedicated opt-in: `kernel_controls.py` rejects both controls, `service.py` has no plan argument, and every binding is read-only. The WSL adaptation preserves the native tuning function. `service.command()` already forwards every *validated manifest* environment entry, and its normal stop retains the stopped container. A bounded implementation can use an owned container-local `/tmp/halogen-local.plan` during training and extract it after normal stop with `docker cp`; no writable host-model binding is needed. Frozen trials can bind the sealed extracted file read-only at a fixed container path with `ALGOS=1`. Mount, profile, plan hash/mtime and runtime identities must enter the ordinary ownership and source seals.

Proposed root-owned sequence:

1. Complete the fresh stock 8K PP/TG/real-agent control. Hold depth 2, cache Off, allocation and request sampling fixed.
2. Train a missing container-local plan with `ALGOS=8` using that same bounded 8K prompt plus short serial/MTP decode. Retain logs, elapsed time and 18 GiB memory guards; exclude these calls from speed comparisons. Do not expand to many shapes yet.
3. Stop normally, prove cleanup/recovery, extract the plan, parse/bound it and seal bytes plus metadata. Reject missing/empty/truncated/stale files and native failure diagnostics. Pin image, DXG and loaded math-library identities with the plan.
4. Restart with that sealed plan and `ALGOS=1`, repeat matched workloads and restart-repeat determinism. Require actual counts, complete-output hashes, functional/strict quality, available first-token proxies, phase/client wall measurements and ordinary lifecycle proof. An output difference is a failed existing parity gate; it cannot be explained away by faster unequal work.
5. Bookend with fresh stock. Promote only a useful gain that survives the bookend and quality gates. Otherwise retain the plan as an unselected artifact and keep stock.

## Candidate 2: adaptive speculation, conditional

The [flags](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/FLAGS.md#L74) document `HALOGEN_SPEC_ADAPT=32,0.35,64`: low acceptance switches drafting off temporarily, then retries; `0` disables this adaptation. The policy also applies to sampling. A bounded on/off ablation is worthwhile only if real traces reveal low-acceptance windows or unexpected serial fallback. It changes which rounds draft, not draft-head accuracy; an aggregate acceptance increase can reflect selection. Record proposed/accepted counts and time alongside completed coding quality. The local wrapper currently provides no validated string-policy argument.

Prompt lookup is documented for greedy requests; sampled requests use the head alone. `MTP_DEPTH` is documented in terms of greedy drafting. These are reasons to inspect the sampled implementation before inventing draft-temperature/top-p controls.

## GPU/NPU and OEM boundary

The [current NPU interface](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/docs/NPU.md) still serves the listed small-model families and compatible fine-tunes. It adds no Flash-Next target-state export, external draft submission or rollback contract. Native concurrent GPU/NPU support requires amdxdna/XRT and held fabric clocks; this WSL DXG deployment does not provide that native seam. The [existing NPU prototype](halogen-npu-top10-20261004.md) remains the relevant evidence boundary.

For this OEM, [BOSGAME's product FAQ](https://www.bosgamepc.com/en/products/bosgame-m5-ai-mini-desktop-ryzen-ai-max-395) confirms performance/noise modes but gives an inconsistent duplicated green-mode list and no precise software control contract for this observed BeyondMax firmware. The active Windows scheme name does not prove the hardware mode. No undocumented power, clock, voltage or fan override is proposed.

A useful reversible addition is **read-only GPU telemetry** during the root's existing trials. [AMD ADLX GPU metrics](https://gpuopen.com/manuals/adlx/adlx-sdk-references/adlx-interfaces/performance-monitoring/iadlxgpumetrics/) expose clock, temperature, usage and power where supported; the [official sample](https://gpuopen.com/manuals/adlx/programming-with-adlx/adlx-samples/cplus-samples/performance-monitoring/perfgpumetrics/) checks support before reading values. The installed library is present, but device support and collection overhead are untested. Missing metrics must remain unavailable. This can address the prior run-order drift without claiming thermal causation from timings alone.

Reddit leads, checked against primary sources above: [October 2 Halogen NPU announcement](https://www.reddit.com/r/StrixHalo/comments/1wvfrj0/halogenflashserver_0160_strix_halo_npu_now_serves/) led to the actual NPU requirements; [BOSGAME performance-button discussion](https://www.reddit.com/r/StrixHalo/comments/1w2hryh/bosgame_m5_performance_button_on_linux/) describes Linux hardware-button state and anecdotal performance/noise differences. Neither supplies a qualified Windows Halogen tuning result. Linux kernel/IOMMU recipes and hardware modifications remain outside this run.

## Recheck at 02:57 UTC, 4 October

Official GitHub metadata still places main and the newest v0.16.2 tag at
`7f31bbd4021f217a1be9776bdb7304bcf8eca62d`. The Max+ 395 download page still
lists Adrenalin 26.9.2 as its newest package; its GPU/NPU versions match the
installed drivers. No update was installed.

The separate [Ryzen AI installation channel](https://ryzenai.docs.amd.com/en/latest/inst.html)
lists NPU driver 32.0.203.376 for Strix Halo and software 1.8.0. The different
driver branch alone does not establish that it supersedes installed MCDM
32.0.20102.3930. No newer applicable driver was verified.

The proposed matmul-plan trial above has since completed and was
[rejected](../benchmarks/halogen0162-matmul-20261004.md). ADLX telemetry has
[passed its read-only probe](halogen-adlx-20261004.md); all six queried tuning
capabilities were unsupported. Neither result establishes a new speed gain.

## Recheck at 13:23 UTC, 4 October

The official main commit API still returns
`7f31bbd4021f217a1be9776bdb7304bcf8eca62d` (`0.16.2`, committed
2026-10-03 04:29:22 UTC). The Max+ 395 download page still lists Adrenalin
26.9.2 Optional, dated September 29. Its release notes list GPU Driver Store
`32.0.32015.2008` and NPU MCDM `32.00.20102.3930`; fresh local CIM reads
match those versions. The current [Ryzen AI release notes](https://ryzenai.docs.amd.com/en/main/relnotes.html)
remain at 1.8.0. No applicable update was identified or installed.

The [requested Reddit comparison](https://www.reddit.com/r/LocalLLM/comments/1wu0m53/benchmarks_best_engine_for_qwen_38flashnext_on/)
was checked again. Its three-turn column normalizes every turn to 1,000 output
tokens; it is not observed wall time. Its numbers describe native Arch Linux
at 70 W and different weights, not this Windows/WSL2 deployment. The current
upstream README explicitly identifies on-demand lookup-table file reads as a
cold-prompt cost. The native ext4 lookup trial tests that specific local cost;
its completed stock/native/stock comparison now qualifies an initial-turn
prefill gain of 28–32% versus the later stock control. It does not qualify
a decode or complete three-turn wall gain. The original native recovery
failure and separate late recovery remain explicit in the
[measurement report](../benchmarks/halogen0162-native-lookup-20261004.md).
