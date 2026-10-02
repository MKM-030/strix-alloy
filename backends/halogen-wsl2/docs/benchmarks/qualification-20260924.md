# Qualification and data validation — 24 September 2026

**Assessment: historical numbers may be shared with the caveats below;
repeat-start and installable-release qualification still need work.**

The original60-request Halogen serving benchmark now completed and passed
after a startup-only cache-advice timing change. Its original MTP mean is
41.20tokens/s; all60 engine/client records were independently paired and checked.
See [the full report and raw data](upstream-20260924.md). The original86-request
size sweep also completed; every API record was checked against expected mode,
sequence and actual token counts. One successful changed-policy start is not
repeatability proof.
Later repeat attempts exposed a startup timeout, a WSL distribution shutdown,
and a first serial response that exceeded its 180-second deadline. See the
[repeat qualification report](repeat-qualification-20260924.md). The original
throughput is not a repeatable cold-start guarantee; public installer
qualification remains open.
Three earlier old-bridge starts failed under memory pressure; those failures
remain part of the qualification history, not inference-speed measurements.

## Verified historical data

[CSV](historical-version-comparison-20260924.csv), SHA256
`12a770321df5df3d68f49c1ebd7cdf283df709784b52329a0e2a5bd704efe251`.
This is the decimal-point-normalized CSV. The original quoted decimal-comma
export is retained in the private research archive; only numeric formatting
changed, not the24 observations.

- 24 individual rows:12 per version, three cases, serial/MTP, two repetitions.
- All12 matched request payloads and full answer strings equal across versions.
- Every sample has128 output tokens, zero prefix-cache hits, a nonempty answer
  and the requested response marker. This is not broad quality certification.
- Both repetitions retained. The warm second repetitions cannot be presented
  as the mean of all requests; first repetitions were slower.
- No missing/null timings in this export; measured token counts retained.
- Timing metrics are the API's engine prefill/decode fields, with full wall
  time beside them. They are different from the original tools' HTTP rates.
- No historical27B or native-Windows result is silently treated as a matched
  same-model, same-prompt, same-configuration control.

The historical0.13.8 warm MTP rows span41.26–42.40 decode tokens/s and
646.47–839.49 prefill tokens/s at measured6676/7058/14078-token prompts.
That is useful performance evidence on those runs, not an achieved1200prefill
target, an original-ten-prompt average, or proof of256k/concurrent operation.

## Remaining publication gates

1. Establish repeatable loading. The original serving/size suites are now
   complete under continuous memory observation, without unrelated GPU contexts.
2. Preserve the included original public inputs, sanitized raw results,
   settings and failure history. Keep cold/warm and timing boundaries explicit.
3. Finish and verify the portable installer, dependency integrity and rollback.
4. Qualify each advertised model/profile separately. Keep256k and fast parallel
   sessions explicitly unverified until measured; do not make them promises.

The goal of future optimization remains unchanged. These limitations define
what can honestly be stated about the first experimental release, not a
replacement for the larger performance/context/concurrency objective.
