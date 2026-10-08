# Exact 0.17.2 asynchronous scalar experiment

Experimental and off by default. The completed frozen 8K comparison established
output/acceptance parity and 52 aggregate successful substitutions, but no
repeatable serving gain. Do not enable this as an optimization.

`scalar_async.c` is bound to engine SHA256
`ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`.
It changes one guarded aligned four-byte H2D site into a D32 value fill on the
explicit legacy stream. All unmatched calls forward unchanged. Activation needs
the externally verified full engine/runtime/preload/library identities and a
fresh receipt path. The local instruction guard alone is not that qualification.

The CPU-only `analyze_receipt.py` parses the 64-byte V1 header and records. It
reports observed append counts and integrity without inventing complete capture,
request coverage or GPU completion. It never initializes HIP.

See `docs/benchmarks/halogen0172-scalar-async-20261008.md` and `.json` for the
actual workload, before/candidate/after means, clock caveats and retained evidence.
