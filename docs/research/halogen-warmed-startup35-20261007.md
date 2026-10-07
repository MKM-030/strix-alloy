# Halogen warmed WSL startup with the authorized 35 GiB floor

The human instruction on 7 October 2026 selected **35 GiB available physical
memory** for v2 startup in both installed backend versions, 0.16.2 and 0.17.1.
Commit admission at context capacity 262144 remains 131 GiB. The independent
runtime RAM and commit floors remain 18 GiB each. The boundary test admits the
exact configured pair and rejects either reserve one byte below its floor.

The previous native-only admission wait could let WSL become idle. A later
Docker operation then woke WSL after the reserve observation. Both services now
own one bounded foreground guest during admission and loading. Its exact ready
marker is required, early exit fails startup, and a successful handoff requires
stdin EOF with exit zero. It is reaped before memory recovery on failure; an
unproven cleanup retains the lifecycle lock. It ends before the server reports
READY. No global WSL settings, model bytes, driver or engine binary were changed.

The reviewed source patch was applied after all three version-comparison windows
had completed and both engines were stopped. Historical source seals and frozen
comparison manifests were preserved. The current source manifests bind every
file (31 in 0.16.2; 39 in 0.17.1), including the updated 0.17.1 README. Installed
artifact manifests were unchanged.

Validation after promotion: eight lifecycle tests per version and all 21
existing 0.16.2 service tests passed. The exact prepared keeper also passed a
real native-PowerShell-to-WSL ready/EOF test, exiting zero with its proxy and
reader reaped. The original saved ServiceNow profile is restored separately in
a visible native PowerShell 5.1 console; its readiness evidence is linked from
the [version-comparison report](../benchmarks/halogen0171-current8k-20261007.md).

These are startup and lifecycle changes. They establish no Prefill/Decode gain,
and successful starts with more available memory do not prove sufficiency at
exactly 35 GiB. The measured comparison and its clock-calibration limits are
documented in the linked report.

Private receipts are retained under
`server/.local/optimization9h-20261004/halogen0171-backend-preparation-20261007/`:
`authorized35-source-binding.json`, `warmed-keeper-live-eof.json`,
`warmed-lifecycle-promotion.json`, and `original-final35-console-launch.json`.
