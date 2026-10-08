# Halogen 0.17.2: captured MTP shortlist screening

Development resumed after Marcel explicitly ended the ServiceNow demo pause. The regular 0.17.2 server remains ready on port 8840 with its visible request-log console. No experimental serving change has been adopted.

The existing capture contains 16 exported heads, of which 15 match its exported 34,571-row asset (32,033 core plus 2,538 tail rows). This is partial coverage of 112 observed scatters. The unmatched head and original capture failure remain preserved; no new capture was performed to enlarge coverage.

Two CPU adapter assumptions were corrected without changing source-reference arithmetic or numerical tolerances: a tail pool row need not be a multiple of 16, and the native scatter map spans 248,320 slots, including seven selected padding slots beyond the 248,070 defined-token boundary. Row uniqueness, bounds, complete native row coverage and the defined bound for actual chosen IDs remain enforced.

One real no-factor evaluation completed successfully: 15 heads, 975 source-reference rows, 385 bitwise matches, maximum absolute error 1.9073486328125e-6 and maximum ULP distance 512. All 15 actual chosen IDs are unique maxima of their captured reduced logits. These results do not establish bitwise native arithmetic equivalence, current MTP acceptance or serving throughput. The process stayed below its 256 MiB job limit; peak working set was 24,727,552 bytes.

The frozen next screen is rank64 BF16 weight-only factors and top256 selected-row rescoring. No queries or logits enter factor fitting. Original native Q4 rows remain necessary for exact rescoring. Analytical weight bytes are 49,782,304 stock versus 5,121,472 for factors plus selected Q4 rows; this excludes top-k, publication, dispatch, cache effects and fallback. It is not a speed measurement.

The fixed weight-only fit completed in 55.9384 seconds. Basis storage is 327,680 bytes and coefficients 4,425,088 bytes. Peak private memory was 182,435,840 bytes and peak working set 170,721,280 bytes, below the unchanged 256 MiB limit. A full NumPy eigensolver was rejected during memory planning, without execution; the same leading64 covariance decomposition uses a subset eigensolver. Numerical packages are isolated in the private experiment directory; the serving interpreter is unchanged.

The single fixed top256 screen recalled the native winner in **11 of 15 heads (73.33%)**. Native-logit oracle rescoring and the CPU source reference both recovered that winner in those same 11 heads. Four omitted winners cannot be recovered by exact shortlist rescoring. Source checks now cover 4,796 rows, with 2,617 bitwise matches and the same maximum absolute error. This is stock-trajectory shortlist recall on partial captured data, not MTP acceptance or quality on the candidate's own trajectory.

The frozen rank64/top256 candidate is not adopted or connected to GPU/NPU. No rank/shortlist sweep, new capture, engine cohort or NPU producer was performed. Its live acceptance and throughput remain unmeasured; a rate loss is not invented. Independent Q4 computation mechanisms remain under source assessment. The ordinary server retains its stock configuration.

Private evidence: `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/mtp-q4-shortlist-cpu-v3/actual-source-reference-v3/summary.json`, SHA256 `5e888b2d4c3b95a889a1d2dc0031e13eeea1d2dccfd8290598c4d5d3160bd2a7`. Partial capture, source corrections and independent reviews are retained beside this evidence. Raw weights are not included in this report.
