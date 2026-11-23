# Halogen 0.20.7 timing audit on WSL2

The captured 0.20.7 image records Prefill and Decode using
`CLOCK_MONOTONIC`. A separate observation on the running HT4 server
found this WSL clock advancing about 10% faster than Windows
QueryPerformanceCounter (QPC). The complete HTTP time on Windows therefore
remains the basis for the [forced decode prefetch](../benchmarks/halogen0207-decode-prefetch-20261123.md)
and [DNZ prefill](../benchmarks/halogen0207-dnz-prefill-20261122.md) decisions.

## Native and API timing

The pinned ELF calls `std::chrono::steady_clock::now()` at the four
Prefill and Decode boundaries. The bundled libstdc++ implements that call
with `clock_gettime(1)`, Linux `CLOCK_MONOTONIC`. Prefill accumulates
per-chunk durations. The terminal native `D` record carries the Prefill
accumulator and the elapsed Decode interval, rounded to 0.1 ms. The
length-finished responses in both archived comparisons expose those durations
via the API and calculate tokens per second from them.

| Comparison | Requests with API phase sum above HTTP QPC | Excess across all arms |
| --- | ---: | ---: |
| DNZ prefill | 24/24 | 0.447–1.060 s |
| Forced decode prefetch | 24/24 | 0.490–1.116 s |

For example, forced-prefetch control request `natural8192-1` reports
4,315.2 ms Prefill and 2,432.0 ms Decode. The Windows client timed 6.1540504 s
from HTTP dispatch to response EOF. The accepted and drafted token counters
are integer counts and do not use the phase clock.

## Host and guest clocks

At 23:26 UTC on 22 November, an exchange against the steady normal server
bracketed each WSL timestamp with Windows QPC. The interval between the first
post-initialization sample and the last sample was 7.5848426 s by the QPC
midpoints. The median post-initialization round trip was 0.7064 ms.

| Guest clock | Elapsed guest time / elapsed Windows QPC time |
| --- | ---: |
| `CLOCK_MONOTONIC` | 1.0998905–1.1001149 |
| `CLOCK_MONOTONIC_RAW` | 0.9999005–1.0001045 |
| `CLOCK_BOOTTIME` | 1.0998906–1.1001149 |
| Python `perf_counter` | 1.0998904–1.1001148 |

A later read-only `adjtimex` query returned clocksource `tsc`, tick
`10836 µs` and frequency adjustment `+46.23 ppm`. The query occurred
after the slope observation. Apply the clock observations only to their
recorded interval. Historical phase rates retain the original native values.
Future phase comparisons need the live provider binding and contemporaneous
clock evidence, including phase boundaries and counts, alongside independent
HTTP QPC.

The API's streamed prompt-progress event marks the end of prompt processing,
and its timestamp uses the same guest clock. Client-side QPC can independently
measure time to the first text chunk and time through EOF. Those intervals
measure delivery and include API and transport overhead.

A separate read-only check after the [KV8 comparison](../benchmarks/halogen0207-kv8-natural-8k16k-20261123.md)
bound the mapped libstdc++ inode and running engine to the same artifacts
used in the static audit. The restored server passed readiness before and
after this check. The provider check establishes the current runtime clock
source. Historical phase intervals still lack contemporaneous validation.

## Local evidence

The observations used the existing HT4 run on port 8840. They required
no inference, restart or clock setting changes. The local receipts are under
`server/.local/halogen-update-20261122/primary0207/phase-clock-0207`.

| Receipt | SHA-256 |
| --- | --- |
| Native phase source audit | `2d91b13ad9684ca4013874c4397d988531fa9a387fe31a38e84ad3382094a1e8` |
| Host and guest clock exchange | `cd01a7dc04f721942e4f34b9a3c1cbdab5a457b1e6496640a448ed788bbbd5ea` |
| Read-only guest clock state | `11913bfaa825700274f17a03ff3d264886be883fba2a82bc7027e064d07bd879` |
| Live provider binding after KV8 | `2cbe45ee051be16d295df2ca5078a640ab45bb7bcbb706d31fe0f0df14d21674` |
