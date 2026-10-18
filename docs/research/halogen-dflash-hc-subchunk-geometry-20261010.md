# Halogen 0.17.3: internal HC groups inside one logical forward

The targeted geometry diagnostic (session 64818) is terminal with exit 1.
The normal 262,144-context server was restored and freshly verified ready/open
at 02:29 UTC. Its controller is 34308, backend 32488, and visible console 33148.
The stopped runtime was retained once; this diagnostic must not be repeated
unchanged.

The natural 16,384-input / 128-output request reached full prefill. The adapter
received one logical forward of 16,384 rows, but Halogen supplied the selected
HC layers in two internal groups of 8,192 rows. Each group emitted layers
4, 16, 24, 36 and 44. All ten rejection tuples have a present source, matching
stream, zero tap mask, and only the row-count mismatch (8,192 versus 16,384).
The end tuple has processed = position = expected = 16,384 and missing taps.

The arm loss baseline is zero. All eleven forwarded Lane loss ordinals are
recorded, with no gaps, overflow or unfinished reservations. First Birth
rejected stage 10 / loss 11; no exports, joined ingestion, complete decode or
acceptance measurement were qualified. The evidence identifies the failed
Owner geometry predicate, rather than a pre-arm or observed assembly loss.

The bounded correction must preserve the outer forward boundary while admitting
only the evidenced internal group size, requiring all five selected taps per
group and complete accumulated coverage. Native subgroup start, stream,
generation, range and duplicate/missing-tap checks must remain enforced. Loss
must not be reset or hidden to pass Birth. A CPU regression and one corrected
capture trial are the next steps, before any real-KV provider work.

This was a diagnostic, not a serving benchmark. The qualified natural 16K
reference remains 1,833.70 prefill tok/s, 43.05 decode tok/s, and
180/399 = 45.11% combined API MTP+PLD draft acceptance. Native MTP-only
acceptance was not isolated. NPU and provider remain off; no acceleration is
qualified. No public commit or push was made.

Raw evidence is retained under the local preparation directory in
`dflash-root-hc-geometry-tuple-map-advice-launch-20261010/trial/`:
`hc-geometry-log-evidence.json`, `terminal-checkpoint.json`,
`retained-startup-runtime.json`, `memory.json`, and
`normal-preserved-after-terminal.json`. The immutable build pins are in
`dflash-checkpoint-20261009/hc-geometry-build-checkpoint.json`.
