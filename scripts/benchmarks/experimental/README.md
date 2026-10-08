# Halogen0.17.2 ordinary page-order experiment

These source-only copies preserve the implementation prepared for Halogen0.17.2
engine SHA-256 `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`.
The original directory names are retained so relative includes remain valid.

The feature is off by default; `PLE0172_ORDINARY_PAGE_ORDER=1` enables it for
experiments. CPU page-order copies retain native GPU IDs and the native unpack,
RMS, and FC paths. Small decode falls back to stock behavior. Cancellation uses
exit code 79.

The frozen before/candidate/after cohort completed on 8 October. The attachment
loaded, but no completed-row marker was observed, so copied-row execution and
an improvement remain unqualified. This adapter stays disabled. See the
[comparison](../../../docs/benchmarks/halogen0172-ordinary-first-gather-20261008.md)
and the [native-worker scope](native-worker-interception-scope.md).
The preserved C++ and assembly bytes are unchanged; no binaries or start
scripts were copied. The analyzer and publisher operate only on saved evidence.
