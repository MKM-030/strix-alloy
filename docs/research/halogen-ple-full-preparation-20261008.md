# Full PLE CPU preparation: complete comparison fails the frozen tolerance

The original layer-1 key and value weights were exported unchanged as 62.5 MiB
of BF16 words. Exact original UNC handle identity, header/directory hashes,
directory descriptors, matrix extents and both directory XOR32 values passed.
The exported matrices have new recorded SHA256 hashes and were rehashed during
decoding. All frozen native input and oracle bytes were independently verified.
This strengthens the actual weight binding; it does not establish every detail
of the engine's allocation or accumulation implementation.

Every output for 8,192 input rows was compared using the unchanged CPU tolerances
`rtol=0.002, atol=0.0002`. The input and weights were widened to FP32 for NumPy
MatMul, then rounded to BF16 using nearest-even. Raw FLOAT comparison and rounded
BF16 comparison were counted separately.

| Projection | Values | Rounded BF16 tolerance failures | Different BF16 words | Maximum rounded error |
|---|---:|---:|---:|---:|
| Key | 83,886,080 | 359 | 105,662 | 0.00390625 |
| Value | 20,971,520 | 21 | 38,080 | 0.0009765625 |

The raw FLOAT comparisons separately failed 6,310 key and 78 value positions.
The complete 104,857,600-element comparison therefore fails the frozen CPU
tolerance. The earlier successful 1,024-value subset remains valid for its
selected positions and never established full parity. Accumulation and rounding
differences are a hypothesis to examine at the selected failing positions,
rather than a demonstrated explanation or a reason to change tolerance.

The existing NPU development constants are both 15 times the CPU constants.
The largest recorded rounded error divided by its CPU allowance is 2.930832,
so these CPU outputs fall inside that existing NPU development envelope. This
derived bound does not qualify any NPU output or repair the stricter CPU result;
no tolerance was changed.

The preparation completed in 6.515 seconds without runtime errors. Child exit 2
and guard exit 1 deliberately preserve the accuracy failure. The owned job
closed successfully. No provider, device session, GPU/NPU computation, inference
request or server restart occurred.

## Prepared graphs and observed CPU work

Two ONNX graphs passed serialization checking. Both use the unchanged shared
external BF16 weights and an 80 MiB FLOAT input converted exactly from the native
BF16 words. One returns a 200 MiB BF16 output pair. The other explicitly widens
those BF16 outputs to a 400 MiB FLOAT pair. Their graph Cast behavior, runtime
execution, device assignment and native OrtValue binding remain unqualified.

| Observed CPU interval | Seconds |
|---|---:|
| Weight export | 0.583203 |
| Key FP32 MatMul | 2.014302 |
| Value FP32 MatMul | 0.483878 |
| Complete comparison including decoding, I/O and checks | 5.639629 |
| ONNX serialization and checker | 0.222188 |

These are preparation/component durations, not serving Prefill or Decode
rates. They establish no NPU benefit or overlap budget. The CPU projection
implementation is not enabled in the live server, and no token-rate delta is
inferred. The future NPU tolerance remains `rtol=0.03, atol=0.003`.

## Selected exact-arithmetic classification

A separate guarded CPU check completed for the first 16 retained rounded
failures per branch and six fixed controls per branch. It read 450,648 selected
bytes; the guard checked complete export/native file hashes before and after.
Original finite BF16 products were summed exactly as Python integers times
`2^-266`, then rounded using two fixed references: direct BF16 nearest-even,
and exact FP32 nearest-even followed by BF16 nearest-even.

All 32 selected failing CPU values match both fixed exact references. None of
the corresponding native values matches them. Each pair differs by one adjacent
BF16 word and lies close to its midpoint: maximum exact-sum distance from that
midpoint is 0.001168752 of the pair's gap. There are no exact ties or double
rounding differences in these cases. All 12 fixed native controls match the
exact reference. The child exited zero and its owned job closed.

Higher CPU precision therefore cannot repair native equality at these selected
positions: the retained CPU result is already the correctly rounded exact dot.
This does not prove the native GPU accumulation algorithm, classify every
failure, or justify fitting results to the oracle. No correction, tolerance
change or serving integration was applied. The stricter full CPU result remains
failed. Actual NPU output must still be compared at the unchanged NPU tolerance.

The unchanged full comparison will not be repeated. The next bounded candidate
is an actual NPU component run through the supported FLOAT output path. Live
early publication, an NPU producer, measured lead and complete-engine benefit
remain open. The original ServiceNow server remains available on port 8840;
the authorized physical startup floor is 35 GiB, commit admission 131 GiB and
runtime reserve 18/18 GiB. The acceleration goal is still unachieved.

The companion JSON binds actual source/config/review pins, complete raw results,
exported products, accuracy failures and owned cleanup.
