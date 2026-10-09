# Closed CPU PLE-ID reciprocal probe

9 October 2026. Exact constant signed remainder reduced isolated full scalar ID preparation from **0.1974250 ms** to **0.0780625 ms** median per 8,192-token / 131,072-ID window. The paired median saving is **0.1194500 ms**. This absolute saving is too small to justify native binary attachment or another engine cohort. Keep the normal engine stock; this lead is closed.

The one completed timed run used 31 alternating paired samples of eight full windows each while the normal server was idle. Candidate timing includes a real 16-word divisor admission check per window. Times use `std::chrono::steady_clock` and describe elapsed CPU component work. They do not measure thread CPU consumption or serving throughput. Table payload reads, native row copies, accelerator work, engine critical-path overlap and possible binary thunk overhead are outside the screen. No throughput conversion is supported.

Both output buffers exactly match the archived 131,072-ID oracle, SHA-256 `b309f270a5af14d60b895507b8d9964303e7190a81d0c3e475f38d7083cea704`. Signed remainder, carry/EOS, sign extension and wrapped offset checks pass. Emitted token-loop assembly has 16 baseline IDIV instructions and zero candidate IDIVs. Historical sanitized receipts preserve the actual build hashes, correctness counts and all 31 numerical timing samples in `observed-build.json`, `observed-verify.json` and `observed-bench.json`. `independent-review.md` records the completed read-only review.

The compiled C++ sources, pinned scalar reference header and `prepare-screen.ps1` are exact copies of the measured probe. `run-screen.original.ps1` preserves the original runner exactly. Published `run-screen.ps1` changes only how the archived fixture receipt is located: it adds an optional `-FixtureVerificationPath` and a useful missing-fixture message. The archive was saved without recompilation, tests, benchmark reruns, integration, hardware access or state edits. Binaries, generated ID buffers, large fixtures and raw state are omitted.

## Offline reproduction

These commands are provided for explicit future reproduction; the completed investigation does not call for another run. The repository root is assumed below:

```powershell
& './scripts/benchmarks/experimental/halogen0173_cpu_id_reciprocal/prepare-screen.ps1'
& './scripts/benchmarks/experimental/halogen0173_cpu_id_reciprocal/run-screen.ps1' -Mode verify
# Original timed command parameters:
& './scripts/benchmarks/experimental/halogen0173_cpu_id_reciprocal/run-screen.ps1' -Mode bench -Samples 31 -Batch 8
```

The build script uses the retained Windows compiler `C:/AI/sdk/therock1151-10.2.0a20260930/lib/llvm/bin/clang++.exe`; edit this local tool path for a compatible installed clang++ if needed. It builds separate translation units with C++20, `-O2`, no LTO and disabled vectorization. No new dependency is required.

Fixtures are private offline artifacts and are deliberately absent from this tracked archive. The default receipt path is:

`C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/ple0172-native-worker-candidate-v1/verification.json`

Its `scalar_run.command[1..4]` identify the saved `tokens-i32.bin` (32,768 bytes), `history-before-i64.bin` (16 bytes), `hash-constants-i64.bin` (280 bytes) and `archived-suffix-ids-i64.bin` (1,048,576 bytes). The runner pins their hashes to that receipt and compares generated IDs to the oracle. For relocated fixtures, supply a copied receipt with these four paths updated:

```powershell
& './scripts/benchmarks/experimental/halogen0173_cpu_id_reciprocal/run-screen.ps1' -Mode verify -FixtureVerificationPath 'D:/offline-ple-fixtures/verification.json'
```

The real constants order is multipliers, offsets, moduli. The source's normalized CPU structure attaches to no native model offsets; 0.17.3 fields moved by +0x28 relative to the archived 0.17.2 reference. A future source-owned worker rebuild could admit the current sixteen divisors once and preserve all exact IDs, but this screen gives no practical reason to integrate it.
