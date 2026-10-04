# Real expert FC admission — 4 October 2026

The corrected public-DD client executed both real v2 layer48 expert0 FCs,
twice each, with no native fault. All context destruction returned, the owned
job closed, and the child exited 1 because the frozen arithmetic gate failed.
Both FC2 cases pass; each FC1 case has one failing element out of 1280.
This is working real-weight operator execution, not qualified NPU MTP.

| FC / case | Relative L2 error against affine reference | Elements outside `.03/.003` gate | Arithmetic pass |
|---|---:|---:|---|
| FC1 / 0 | 0.8203% | 1/1280 | No |
| FC1 / 1 | 0.8386% | 1/1280 | No |
| FC2 / 0 | 0.8249% | 0/2560 | Yes |
| FC2 / 1 | 0.8240% | 0/2560 | Yes |

The gate is `abs(actual-reference) <= .003 + .03*abs(reference)` for every
element, with finite output. It was not relaxed. All raw BF16 outputs and
receipts are retained, including failed calls. FC1 timing fields remain null;
no speed selection follows from failed arithmetic. The two FC2 call intervals
are .2605 and .2032 ms, separate non-statistical operator observations.

Preparation read only **2,785,408 bytes** of the pinned current-v2 checkpoint,
covering one expert's codebook/codes/scales, and completed in 7.15 seconds.
The official offline formatter produced original-geometry FC1/FC2 buffers.
Gate/up rows explicitly changed from concatenated halves to `g0,u0,g1,u1,...`.
CPU references decode affine nibbles independently of the formatter, use
BF16-rounded scales/inputs, and accumulate dot products in FP64 before FP32.
Two varied inputs are retained per FC. This does not duplicate native
accumulation order or prove a native activation convention.

Approximate affine INT4 conversion introduces a separate **8.46–8.53% weight
relative L2 error**, and **8.39–9.94% reference-output relative L2 error**,
against decoded original q4c weights in these cases. Actual NPU outputs differ
by 8.42–9.99% against that original reference. The much smaller affine-reference
error must not conceal the conversion error. Live target verification and
acceptance are required to qualify approximate drafts.

The native run recorded physical reserve **42.74 GiB** and commit headroom
**198.03 GiB** at minimum, with the fixed 8-GiB job ceiling and 22-GiB abort
margin. There were zero native fault records. Fresh PID inspection confirms
the child is absent. The [evidence JSON](halogen-dd-real-fc-admission-20261004.json)
preserves preparation, all four comparisons, exact artifacts/hashes and
lifecycle. Raw artifacts remain ignored under `server/.local/optimization9h-20261004`.

Next work is a source-grounded arithmetic diagnosis using these saved arrays;
there is no reason to export all 512 experts or repeat this identical hardware
run before a justified change. Complete routing, shared MLP, publication,
target-verifier acceptance and end-to-end speed remain open requirements.
