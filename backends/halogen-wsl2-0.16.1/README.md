# Halogen 0.16.1: superseded WSL transition experiment

This package preserves the intermediate 0.16.1 adaptation developed before the
[0.16.2 package](../halogen-wsl2-0.16.2/README.md). It is an unqualified source
archive, not a supported compatibility or rollback backend. The managed gateway
selects 0.16.2. No 0.16.1 performance, model-quality or long-context qualification
is claimed here; earlier 0.15.1 measurements do not qualify this engine.

The public scripts, patches and pinned profiles are retained for review and
reconstruction. Existing model data and ignored `.local/` installation/run files
are retained separately. Generated binaries, tokens and machine configuration
are not distributed in Git.

## Recorded identity

`profiles/release.json` records the 0.16.1 upstream commit
`6ff580c0f37513da2c4aae984ba89291efe08af6` and exact official image:

```text
ghcr.io/peonist-ai/halogen-flash-server@sha256:089701309a7ed9f70c91daca6a66080828e032788d4e6d0da4d427587387ede5
```

The engine SHA-256 is
`3829caf926da67bf1567e5f93a05f3fd925a7e08b52867b44ca3b3332915f907`.
The 24 entries in `profiles/sources.json` matched their preserved file bytes at
the 2026-10-03 source review. Matching source hashes does not prove successful
installation, runtime correctness or qualification. The release explicitly keeps
`v2_checkpoint_qualified` false.

## Unresolved archive blockers

- `scripts/runner.py` mounts `.local/librocroller-compat.so.1`, but this package's
  installer does not extract or pin that dependency. Its `COMPAT_IMAGE` constant
  does not provide a complete installation path.
- The legacy 4K runner hardcodes preflight-sequence SHA-256 `9df3f1c8...d42079c`,
  while the preserved file bytes hash to `2578343f...ccc886b`. The artifact seal
  rejects that mismatch before qualification.
- Trace validation expects bridge RVA `0x1171030`; this package's actual bridge
  binding is `0x1876e70`. The copied trace predicate cannot qualify that binding.
- The archived runtime guard retains a 12 GiB physical/commit threshold. It does
  not implement the current 18 GiB service policy.

These blockers remain visible rather than being repaired as part of the 0.16.2
upgrade. Resolving them would require a separate source review, repinning and
live qualification.

## Historical commands

The following records the former launcher interface only. These are historical,
unsupported commands and are not a current installation or serving recommendation:

```powershell
.\backends\halogen-wsl2-0.16.1\Start.ps1 -Checkpoint v2 -ContextSize 262144
.\backends\halogen-wsl2-0.16.1\Start.ps1 -Checkpoint w4b -ContextSize 262144
```

Use the [0.16.2 guide](../halogen-wsl2-0.16.2/README.md) for the current experimental
path. Do not start this archive beside an active inference backend.
