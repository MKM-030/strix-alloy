# Halogen 0.17.3: bounded HC subchunk correction

The adapter now handles the native two 8,192-row HC groups inside one logical
16,384-row forward. The selected layers must arrive in order, share the native
group position and stream, and cover all five taps before advancing the capture
cursor. Copies use the accumulated row offset. Missing, duplicate, replayed,
short or out-of-range groups still invalidate the features; loss, generation,
fence and Birth checks remain enforced.

Root reproduced the original first-group rejection with the unchanged parent
code, then passed the same CPU fixture against the correction (26 focused
cases, including every concatenated BF16 cell and fence behavior). The original
test runner had two fixture/reporting issues: inherited `-fno-exceptions` and
misplaced `flush=True`. Their failed outputs were retained. A fresh standalone
fixture runner repaired these issues; production flags and the sealed fixture
were unchanged. All 27 production C++ units compiled and linked, and the three
retained relay islands passed their byte audit. An independent three-file source
review found no actionable issue.

The single corrected hardware diagnostic, session 65341, reached the complete
16,384-token natural prefill. First Birth evaluated a zero Lane loss counter;
only the zero arm-baseline record was present. The prior HC geometry rejection
is therefore resolved in this actual run. The worker then entered Held because
Triton could not find a C compiler. There was no successful complete worker
ingestion, capture retirement, decode or acceptance measurement. This is not a
qualified serving or NPU acceleration result, and the trial must not be repeated
unchanged.

Nineteen stopped runtime files were retained once. Session 65341 is terminal
with exit 1. The normal 262,144-context server was restored and freshly verified
ready/open: controller 31384, backend 33596, visible console 33428. The qualified
natural 16K reference remains 1,833.70 prefill tok/s, 43.05 decode tok/s, and
180/399 = 45.11% combined API MTP+PLD draft acceptance. Native MTP-only
acceptance was not isolated. The NPU and provider remain disabled.

A read-only inventory of the restored original runtime found no C compiler,
standard C headers or C runtime development objects. A PATH-only fix cannot
resolve that environment. The next candidate is a private derived capture
image containing the compiler and development headers, preserving existing
runtime libraries and the original normal-serving image. No host driver,
firmware, model or global WSL change is needed or authorized by this finding.

Evidence is in the local preparation directory:
`dflash-checkpoint-20261009/hc-subchunk-build-checkpoint.json`,
`dflash-checkpoint-20261009/compiler-inventory-20261010.json`,
`dflash-hc-subchunk-source-preparation-20261010/independent-correction-review.json`,
and `dflash-root-hc-subchunk-map-advice-launch-20261010/trial/`.
No public commit or push was made.
