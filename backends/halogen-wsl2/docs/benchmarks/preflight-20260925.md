# Real 260k input and multi-session qualification — 25 September 2026

**One real 260028-token input passed. Three smaller clients passed together. Three full 260k contexts did not fit the guarded configuration.** These are bounded qualification measurements, not a statistical performance guarantee or an upstream-supported WSL release. Earlier 24 September reports and their methodology are preserved byte-for-byte as historical snapshots; their then-current profile/release status is superseded by this report and the current README.

## Single-client engine timings

Prompt cache was disabled. Every measured answer was nonempty and contained its requested marker. Rates were recalculated from actual server token counts and milliseconds, allowing for rounding. Non-streaming HTTP wall time is separate and is not TTFT.

| Pool capacity | Actual input | Actual output | Mode / order | Prefill tok/s | Decode tok/s |
|---|---:|---:|---|---:|---:|
| 32768 | 58 | 128 | Serial, first | 22.162 | 17.423 |
| 32768 | 58 | 128 | MTP, first | 87.786 | 29.844 |
| 32768 | 58 | 128 | MTP, second | 94.340 | 42.778 |
| 32768 | 58 | 128 | Serial, second | 97.627 | 39.351 |
| 262144 | 540 | 28 | Serial | 363.906 | 35.897 |
| 262144 | 540 | 28 | MTP | 409.091 | 44.304 |
| 262144 | 260028 | 32 | MTP | **790.920** | **36.626** |

Large-request engine prefill: 328.7666 s; decode: 0.8737 s; HTTP: 354.398605 s. The ~24.76 s difference was not broken down further. The API ledger independently reports 32 tokens, 16 MTP rounds, 1.88 commits/round, and 260096/262144 occupied pool positions. It is a filled-context test, not just a configured limit.

**Caveats:** one large sample, short output, synthetic repeated filler rather than 260k distinct code; no quality-at-depth or long-duration soak guarantee. Warmup and request order confound serial/MTP comparisons. The fastest short sample is not a sustained average. The new profile has not repeated the full historical 60-request upstream suite; that suite is preserved [separately](upstream-20260924.md).

## Two and three simultaneous smaller clients

One shared 32768-position pool, three slots; each client processed **8212 input + 128 output** tokens. Every response passed its own marker, unique ID/content and zero-cache checks. All client intervals overlapped, and API pool usage reached 16896 positions for two clients and 25344 for three. This is one model serving multiple requests, not multiple model copies.

| Clients | Cumulative input | Cumulative output | Total tokens | Common wall, s | Delivered output tok/s |
|---|---:|---:|---:|---:|---:|
| 2 | 16424 | 256 | 16680 | 30.846 | 8.299 |
| 3 | 24636 | 384 | 25020 | 39.421 | 9.741 |

The last column is **total output / common wall including prefill**, not pure aggregate decode. Do not sum individual rates with overlapping, unequal time windows.

| Group / client | Prefill tok/s | Decode-window tok/s |
|---|---:|---:|
| 2 / 1 | 801.468 | 14.470 |
| 2 / 2 | 849.172 | 6.852 |
| 3 / 1 | 852.947 | 4.794 |
| 3 / 2 | 837.951 | 19.769 |
| 3 / 3 | 780.067 | 7.858 |

MTP was requested, but most output tokens were logged with the speculative head off under the mixed prefill/decode schedule (114–127 of 128 per answer). Request overlap alone does not prove simultaneous GPU execution. Only one group at each concurrency was measured, so there is no stable fairness estimate.

## Three full 260k contexts: capacity failure, no throughput result

Requested: three slots, context 262144 each, **786432 total pool positions**, ~780000 input tokens plus output. The engine completed weight placement, then began reserving an estimated 21.6 GiB KV pool. The startup guard stopped the run before readiness because Windows available memory fell below the 20 GiB stop threshold.

- At the stop decision: 19590668288 B available.
- Minimum observed through stop: **19228377088 B = 19.228 GB = 17.908 GiB**.
- Recovery: **57376460800 B** available, without reboot.
- Terminal state: PID 0, not running, exit 137, OOMKilled false.
- No completed inference requests; cumulative token counts and throughput are **not measured**, not zero-speed samples.
- Runtime telemetry never started: no exact full-pool GPU/cgroup peak is available.

The guard ledger proves the intended pressure stop; the parent controller also records early-termination cleanup warnings because the guard stopped it first. This is not a passing qualification. Stop thresholds cannot prevent transient undershoot during asynchronous cleanup. The result bounds this profile with these reserves, not ultimate hardware capacity. We did not weaken the reserve and do not expose this failing mode in the public launcher.

## Exact memory accounting

All successful model runs used the same completed adapter operations:

| Operation | Bytes | GB (decimal) | GiB |
|---|---:|---:|---:|
| GPU weight copies | 50433337536 | 50.433 | 46.970 |
| Host weight registrations | 22574008704 | 22.574 | 21.024 |
| Total weight payload | 73007346240 | 73.007 | 67.993 |

These are completed allocations/registrations, not a precise physical-residency measurement. The ~124 GB checkpoint includes a large disk-backed lookup table and is not fully pinned.

| Metric | Single 32k | Single 256k | 2/3 clients, shared 32k |
|---|---:|---:|---:|
| Windows available minimum, B | 27266002944 | 26031091712 | 27058495488 |
| Same, decimal GB | 27.266 | 26.031 | 27.058 |
| Sampled adapter-wide dedicated + shared peak, B | 85441536000 | 92428980224 | 85769244672 |
| Cgroup peak, B | 24649949184 | 25248124928 | 25108201472 |
| Sampled cgroup swap, B | 0 | 0 | 0 |

The large run's engine reports rounded weights + KV + workspace of 68.0 + 7.2 + 3.8 = **79.0 GiB**. Adapter counters include the desktop/driver/other clients. Windows, GPU shared, guest and registration counts overlap: never add them. The 256k run's smallest margin above the 24 GiB runtime floor was only ~0.261 GB.

Successful runs ended only after all responses, then explicit stop reached PID 0, OOMKilled false, with no cleanup failures. Windows recovered and WSL auto-stopped. A bounded System-log query found no Display event 4101 between 13:00 and 13:15 UTC; this does not cover every GPU fault or the later failed capacity run.

## Reproduction and source identity

Qualified research environment: Ryzen AI Max+ 395 / Radeon 8060S, 128 GiB physical; VGM64; Windows-visible 68340748288 B; WSL memory 56 GB; Windows 11 build 26200.7462, AMD 32.0.31041.1004 / Adrenalin 26.8.1, BIOS AMI 3.10, WSL 2.7.12/kernel 6.18.33.2-2. Both model files reside on native WSL Ext4.

- Engine 0.13.8 SHA256 `39382df17e7bd922a302d7dbfaaaa80d5dbb4a813e50268265a74c70c8679625`.
- Image `ghcr.io/peonist-ai/halogen-flash-server@sha256:6e626c979d536ab1edb07898e278be6686afd353758ea268817457f801d687dd`.
- Combined adapter `adadd8dd5cebcdf559fcc9df767a2bcb36e6946c1a123b90c670320bf7a873f5`.
- Private adapter `f567e21d5c7293ce75f62d36e57bf65915640c11fb2c753b39757d17b3ed034d`.
- Working DXG `0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6`.
- Native source/build identities: [build manifest](../../profiles/build.json).
- Profiles: `flash0138-copy48-v1` / `vgm64-copy48-v1`; copy cap 48 GiB, reclaim 1, PIN_TRUNK 1, arena/prefill 2048, prompt cache 0, quality overlay enabled.
- Windows launch floor 49 GiB; startup stop 20 GiB; readiness/runtime 24 GiB; guest reserve 12 GiB; cgroup 44 GiB, no extra swap.

Use `Start.ps1 -Profile Single32k`, `Single256k` or `Sessions32k` after installation. Public controller copies are portable adaptations of the frozen research sources; their validation is tracked in [release qualification](../release-qualification.md). Full 3×260k remains research-only.

Numeric exports: [32k](32k-analysis-20260925.json), [256k](256k-analysis-20260925.json), [small sessions](sessions32k-analysis-20260925.json), [capacity failure](sessions260k-analysis-20260925.json). [Compact exact request recipes and original response objects](responses-20260925.json) retain UTF-8 prompt hashes; reconstruct `prefix + repeat_unit * repeats + suffix` (or literal prompt). The 14 records include two one-token calibration responses, whose zero decode window is not a benchmark rate. All 12 measured response rates were checked independently.

[Forty memory observations](memory-20260925.csv) include Windows available/commit, cgroup usage and the most-used individual adapter's dedicated/shared counters; they are not summed across different adapters. [Startup/runtime guard observations](guard-20260925.csv) include the failed capacity run and cleanup minima. [Validation record](validation-20260925.json). No private chats or full machine dumps are included. Exports are covered by [SHA256 manifest](manifest-20260925.json).

Validation status: **share with the above caveats**. Publication is not proof of 120 GB capacity, universal installation, official support, or sustained 40–60 decode / 1200 prefill tok/s.
