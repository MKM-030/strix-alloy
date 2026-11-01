# Halogen 0.18.22 bounded concurrency comparison

Goal: test the upstream shared-round drafting mechanism with two independent
requests, preserving target output and normal ServiceNow serving afterwards.
Aggregate completed-output throughput includes prefill and waiting; it is not
single-request decode speed. No NPU speed gain is assumed.

The already reviewed private implementation and portable tests are bound by
`candidate-receipt.json` and `portable-tests-supplement.json` under
`server/.local/halogen-update-20261101/primary01822/concurrency2-prep/`.

- [x] Reverify current server identities and no live measurement handles.
- [x] Reverify exact production and portable payload/baseline hashes.
- [x] Prepare an eight-file restore and six-addition removal transition.
- [x] Test full rollback, foreign-byte refusal and ownership retained after
  a semantic readiness rejection.
- [x] Read back supported OEM Performance mode and current GPU load.
- [x] Review finite collector and coordinator; verify CPU tests.
- [x] Stop the bound normal server, apply the source transition and run portable
  and existing forwarding tests.
- [x] Run before/candidate/after on private port 18840 with gateway concurrency2
  in all arms, engine slots1/2/1 and pool32768 in all arms.
- [x] Exclude one warmup pair and measure three pairs per arm. Reuse the exact
  distinct 8192/16384-token requests, output128, T0/seed1, cache/thinking Off.
- [x] Validate actual native capacity at every bind, per-request counters and
  output identity. Legitimate batched proposal counts may differ.
- [x] Restore exact normal sources and ready port8840; retain all evidence and
  report aggregate throughput, each latency and acceptance separately.

One engine shares the model weights. Pair reservation24832 fits pool32768;
two full16K requests would not fit. Startup30GiB physical/131GiB commit,
runtime18GiB and request entry22GiB remain unchanged. Do not reuse a singleton
RAW phase observer on interleaved requests. Necessary Halogen lifecycle actions
are already authorized; unrelated programs and system settings are preserved.

Ruling: use the single Primary checkout on a temporary `codex/` branch, rather
than create another physical worktree, following the user's consolidation and
disk-cleanup request. Only root changes installed files or uses hardware.
All candidate files are restored before normal serving, regardless of outcome;
a performance claim or later promotion requires the completed comparison.


Publication outcome: Complete 24-request comparison; both separate controls reported. Normal port 8840 and exact original sources restored. See `docs/benchmarks/halogen01822-concurrency2-20261101.md` and matching JSON. Candidate remains unpromoted.
