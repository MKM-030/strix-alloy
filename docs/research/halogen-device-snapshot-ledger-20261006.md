# Independent GPU drafter device snapshot work

The full Halogen acceleration goal remains unachieved. Partial and full device
snapshot mechanisms were separately measured on the same growing 256-to512
raw-ID policy and matched llama.cpp bundle. The full mechanism passed finite
exact-state qualification; native acceptance and serving gain remain unmeasured.

- Baseline: original growing bridge commit a585f5d copied into the isolated
  codex/gpu-draft-snapshot branch; unrelated older-worktree changes preserved.
- RED: the real retained growing-GPU receipt fails the new runtime qualifier
  at round0 because speculative rejection still clears/prefills the prefix.
- Implementation: default-off partial device save/restore, recurrent restore
  before attention suffix removal, epoch ownership, scalar authoritative replay,
  recorded fallback rebuild, unchanged target arithmetic.
- Build: one MSVC build passed; frozen bundle/imports checked, output not loaded
  during compilation. Independent source review found no implementation blocker.
- Ruling: exact control uses identical256 prefill plus scalar authoritative
  updates rather than fresh parallel prefills; the latter have a known numerical
  discrepancy and would confound rollback correctness.
- Ruling: source checks and one full15-case state/cost comparison provide the
  relevant verification. No general application test suite, CPU/NPU repeat or
  unchanged Halogen cohort is justified by this isolated benchmark change.
- Runtime qualification: **failed** in the actual partial-device pass. Initial
  and first two resolved F32 rows matched the identical-prefill/scalar control;
  round 2 at committed length 260->263 differed in 248,319/248,320 words. All 15
  post-resolution greedy IDs still matched, which does not satisfy exact row
  equality. The partial realization remains disabled; tolerance was not relaxed.
- Actual component cost: 32.6397 ms initial 256 prefill, 10.95597 ms mean proposal
  including save, 8.612 ms complete mean resolution, and 21.74395 ms seed-amortized
  core per round. These are costs of a failed trajectory, with no historical
  paired improvement, serving tok/s or native acceptance claim.
- Fresh offline evaluation using `expected_next_ids`: 22/44 leading labels,
  opening-reference equality 10/15, and 19 opening-conditioned leading matches.
  The final third ID is unscored. Full per-round rows, costs and source pins are
  in [the partial result](halogen-device-partial-snapshot-results-20261006.md)
  and its [JSON companion](halogen-device-partial-snapshot-results-20261006.json).
- Lifecycle: initial restoration and later observation failures were preserved.
  The supplemental read-only receipt verified the same launched original
  ready/open, controller 23252/backend 24280 with backend birth 134357508439272936,
  without restart or inference. The component job was closed.

- Full follow-up: default-off flags 2 save, private attention/recurrent clear,
  full restore, and scalar authoritative replay. The frozen independent
  [source review](../../scripts/benchmarks/halogen_llama_raw_id_bridge/FULL_SNAPSHOT_REVIEW.md)
  found no blocker. One separately built full-mode screen completed under UUID
  d07bf4b747224116b00dd6e1c55a3a62; initial and all 15 resolved full F32 rows
  independently matched scalar control exactly, with zero differing words.
- Full operations/cost: 15 saves, nine private clear/restores, six append
  resolutions, and no measured prefix rebuilds. Seed plus all measured rounds
  cost 390.8318 ms, or 26.05545 ms per round; measured diagnostic writes cost
  37.0657 ms separately. Fresh scores were 22/44 leading labels, 10/15 opening
  equal, and 19 opening-conditioned labels. State parity supplies no historical
  paired improvement, native acceptance, target tok/s, or serving qualification.
  Full details are in [the full result](halogen-device-full-snapshot-results-20261006.md)
  and its [JSON companion](halogen-device-full-snapshot-results-20261006.json).
- Offline ensemble coverage: stock 22/44 labels; optimistic per-case maximum
  28/44 adds six labels in rounds 4/9/12/13. Applying opening equality gives
  25/44, adding three in rounds 4/9/13. Round 12 alone rescues a mismatching
  native first ID. This one-family oracle coverage supplies no runnable router
  or native acceptance claim.
- Full lifecycle: component/coordinator passed and jobs closed. Final normal
  and supplemental receipts confirm original ready/open, controller 2172/backend
  25932 with births 134357523143840310/134357523252585985 and unchanged profile.
  The supplemental reseal used no restart or inference. The first failed preflight UUID
  688352fec0794b39b869b06aadbae621 ran no screen and remains separately retained.

CPU can use the public snapshot APIs but its proposal cost already exceeds the
planning allowance. NPU uses different state/checkpoint APIs and its prior cost
is also defeated. GPU is the only justified first placement for this mechanism;
all target weights and verification remain on their existing path.
