# Benchmark methodology and release qualification

Status: publication preparation, 2026-09-24. The original60-request serving
suite passed and the86-request size sweep completed; see the
[report and raw records](upstream-20260924.md). Historical successful
measurements and aborted attempts remain distinguishable. Further speed optimization, 256k and
maximum concurrency are ongoing research, not reasons to mislabel this profile.

## Reproduce the upstream instruments

Use the original tools inside the official pinned Halogen 0.13.8 image:

`ghcr.io/peonist-ai/halogen-flash-server@sha256:6e626c979d536ab1edb07898e278be6686afd353758ea268817457f801d687dd`

| Tool | SHA256 |
|---|---|
| `/halogen/tools/bench-serving.py` | `7edd38e6ce04854298cf7584ecac13d47afeb96c93e4c85fe113c14094944f83` |
| `/halogen/tools/halogen-bench.py` | `0587690c50cfa6769b54d67c7553ba8aa3ec861e677082590d322b0b2f0f846f` |
| `/halogen/tools/eval-prompts.json` | `23df9feb5ec2b343f675bb08dc6c0c2286e17dd6d73acf4e7d363d0c0c49922b` |

Run only the Python HTTP clients against an already loaded, guarded, otherwise
idle server. Do not start a second model through the image's `bench` or `sweep`
entrypoint mode. The serving client must be supplied a continuously flushed
API log through `HALOGEN_API_LOG`; a missing ledger is not a passing test.

```sh
python3 /halogen/tools/bench-serving.py serial,mtp 256 low 3
python3 /halogen/tools/halogen-bench.py --api http://127.0.0.1:8731 \
  -p 512,2048,8192,16384 -n 128 -d serial,mtp -r 3
```

The first command uses all ten original prompt shapes, both modes and three
repetitions: 60 responses. Require completion, cross-drafter output identity,
no repetition-instability markers, all 30 MTP ledger records matched, and no
unrelated traffic. Inspect the records, not just exit status: the script's
exit code alone does not reject every ledger/instability problem.

It uses upstream default thinking behavior, low effort and greedy decoding.
With the current answer-room default and a256-token budget, thinking is closed
at token1; report that behavior, do not label this a long reasoning test.
Serial rows marked `*` include HTTP/prefill wall time; MTP rows use the engine
decode window. Their ratio is NOT an MTP speedup measurement.

### Supplemental engine-to-engine comparison

The pinned0.13.8 API also emits `serve_api: batch` lines for serial requests.
The original serving tool ignores those because its parser requires the
speculative-rounds field. The unmodified tool's output remains the benchmark
of record. A separately labelled supplemental CSV may pair ALL60 API lines
with the60 client records in exact execution order. Require each mode and
output token count to match, with no missing or additional requests.

Verified in the pinned `serve_api.py`, lines3157–3262: both `batch` and `mtp`
rates use the same `n_gen / (decode_ms /1000)` expression. Only the rounds
clause is conditional. This permits a genuine engine-to-engine comparison,
unlike dividing MTP engine rates by the original table's serial wall rates.
Preserve all three repetitions, actual prompt/output counts, cache counts,
rounded decode/prefill seconds, reported engine rate and separate HTTP wall.
Recalculation must allow for independently rounded log seconds/rates.

Short prompt prefill rates are dominated by fixed costs; do not advertise
them as large-prompt processing capacity. Use the size sweep for that purpose.

The second command is an HTTP end-to-end size sweep. Prompt processing includes
one generation step. Generation includes prefill and covers all ten original
prompt shapes, not the fastest code example. Its synthetic repeated filler is
appropriate for this upstream size test but not a realistic long-context chat
or speculative-acceptance benchmark. Publish actual token counts, not just
requested lengths. These rates are not the engine-only prefill numbers in
upstream's headline table.

## Depth, concurrency and memory

For later serving-at-depth results, use the same serving script's documented
`HALOGEN_BENCH_DEPTH` and a public real-text prefix; include prefix hash and
measured prompt lengths. Keep enough room for template and output in the shared
KV pool. A32k configured pool is not proof of32k occupied context, and neither
is proof of256k support.

Report queued clients separately from simultaneous GPU sessions. The current
qualification profile has one slot. Previous small three-slot experiments do
not qualify fast parallel serving in this release profile.

Observe Windows available RAM continuously throughout model loading and every
timed request. Startup advice is outside timed requests; runtime observation
must not drop caches. Do not open a separate HIP probe alongside the model.
Record driver, VGM, WSL memory ceiling, image/adapter/model identity, arena,
cache mode, copy/registered weight bytes and device-wide GPU counters. Do not
add overlapping engine, GPU and Windows memory counters.

## Qualification history that must not be omitted

- Earlier bounded32k/2048/one-slot tests produced coherent answers and about
  41–42 MTP decode tokens/s at7k–14k prompt depth (128 outputs, thinking off).
- The first full original serving suite stopped after4 of60 requests.
- The different DXG library bundled in0.13.8 failed full-model memory
  qualification and is disabled in the launcher.
- Post-benchmark repeated starts exposed a 240-second startup timeout,
  distribution power-off without a host-attached lifetime observer, and a
  first serial 512-token request that timed out after 180 seconds. These
  attempts are [reported separately](repeat-qualification-20260924.md), not
  included as successful repetitions or hidden by the earlier complete suite.
- Three fresh attempts with the OLD byte-qualified bridge on24September also
  triggered the earlier20GiB startup stop before any request, including one
  after a verified complete WSL VM restart. They preserved minimum16.37,
  20.73 and18.17GB of available Windows RAM during observed cleanup. This
  contradicts any claim that the earlier fast profile already starts reliably.

These aborted attempts never supplied a publishable full-suite mean. The
subsequent early-cache run did complete both original suites and is reported
separately, with every observation preserved. It remains unacceptable to
present the best partial cases as a representative average.

The [historical version-comparison CSV](historical-version-comparison-20260924.csv)
contains all24 earlier measurements: two versions, three custom prompts, both
modes and TWO repetitions (not the original suite's three). It includes first
and second repetitions and exact prompt/answer hashes. Every matched request
payload and answer was freshly rechecked against the0.13.2 source record.
Input text is not in this numeric export, so this file alone is not a complete
reproduction package. It is bounded historical evidence, not a stability result.
See [qualification and data validation](qualification-20260924.md).

## Working dependency provenance

The previously local DXG library is obtainable from AMD:

[ROCm SDK core wheel](https://stable.repo.amd.com/rocm/core/whl-next/rocm-sdk-core/rocm_sdk_core-10.0.0-py3-none-linux_x86_64.whl)

- Whole archive SHA256: `3bf4a72d11aa2a4ee1e90572c73630f937d38c1b7af4dda45b483b54655138a7`.
- Allowlisted member: `_rocm_sdk_core/lib/librocdxg.so.1` (6606449 bytes).
- Member SHA256: `0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6`.

Both hashes must match; the URL is not an immutable release identity. This
proves obtainable identical bytes, not official Halogen/AMD support for this
combination. Do not install the whole wheel or replace system libraries merely
to obtain this one dependency. License/notices and a clean installer remain
release gates.
