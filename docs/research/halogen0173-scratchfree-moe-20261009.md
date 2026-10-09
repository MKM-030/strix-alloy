# Halogen 0.17.3 scratch-free MoE: actual component result

The new GPU kernel reproduces the original operation exactly but is slower in this component cohort. It remains disabled; no serving kernel was replaced and no decode or prefill speedup is established.

| Actual N=3 operation | Mean latency, ms | Sample SD, ms |
| --- | ---: | ---: |
| Original Halogen FL | 0.062242 | 0.004770 |
| Scratch-free owner512 candidate | 0.070524 | 0.008369 |

Candidate latency is 13.31% higher by ratio of means and higher in seven of nine measured pairs. The alternating schedule contains five BA and four AB pairs, after a separate excluded warmup. Each HIP-event bracket contains eight operations; reported times divide that bracket by eight. The small measured latencies and observed variation limit extrapolation. No component milliseconds are converted into serving token rates.

Root captured one authentic original operation during the excluded 16K warmup: three token rows, 30 selected expert slices, 25,419,244 total capture bytes. The capture hook forwarded the original operation unchanged and disabled itself after this capture. The private tensor payload is not published.

Original replay first matched all 7,680 captured BF16 output values bit for bit. The candidate then matched all 7,680 values, and every measured pair retained this equality. Input/output guard bytes and zero counter postconditions passed. The successful replay exit additionally requires every supplied candidate scratch byte to remain 0xa5, proving that buffer was unused. Cleanup passed and the component process exited.

The normal model remained ready on gateway port 8840 with unchanged completed/cancelled request counts throughout the component. Fresh process/GPU load checks preceded execution. Entry required 22 GiB physical and commit reserve; the watcher retained the 18 GiB runtime reserve. No NPU operation or second large engine ran. Model files, drivers, BIOS, voltages and global WSL settings were preserved.

[Numeric evidence](halogen0173-scratchfree-moe-20261009.json) records the nine pairs, artifact/evidence hashes and memory/ownership receipts. [Source-only experiment](../../scripts/benchmarks/experimental/halogen0173_scratchfree_moe/README.md) documents the default-off capture and replay. The private evidence remains under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/phase-clock-real16k-20261009`.

This GPU component result is independent of the first duration-adapter cohort's rejected Decode pairing. Those API observations were retained with their failure; they are not presented as a fully RAW-qualified serving benchmark.
