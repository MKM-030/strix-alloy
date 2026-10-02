# Source integration validation — 29 September 2026

## Published scope

This checkpoint starts from native `origin/main` at `55bb4ff`, not from the
141-commit unpublished GUFO integration history. The Halogen package is copied
from `MKM-030/strix-alloy-wsl2` at `6b35ef80445d426237f87175258c7ceab724b252`.
Its source, frozen runtime controls, notices and evidence are byte-preserved.
Only the new discovery/API helpers, tests, documentation and explicit text
attributes are new code or configuration in this checkpoint.

## Checks completed on Windows

| Check | Observed result |
|---|---|
| New selector/API helper suite | 10 tests passed; exit 0; 12.772 seconds |
| Same suite from a fresh indexed checkout | 10 tests passed; exit 0; 12.805 seconds |
| PowerShell parser, source and fresh checkout | 12 files parsed in each; no parser errors; scripts not executed by the parser |
| Imported Halogen files against source manifest | 84/84 SHA-256 matches |
| Halogen frozen runtime/source manifest | 38/38 SHA-256 matches |
| Staged tree exported with `core.autocrlf=true`, `false`, `input` | All 84 imported files byte-identical in all three exports |
| Targeted key/token scan of introduced source | No matching private-key, GitHub-token, OpenAI-key or AWS-key patterns found |
| Introduced binary/model asset scan | No executable, DLL, SO, GGUF, HGN, safetensors, archive or credential database added |

The targeted scan is not a guarantee that every possible secret format has been
recognized. Imported content was already public at the pinned source revision.

## Imported test suite limitation

The imported Windows suite completed **46 passing tests and 20 Linux-only skips**
before the Git synthetic-repository round-trip test failed to complete in the
remote runner. The first attempt stalled during automatic maintenance; a second
attempt with process-local maintenance/GC disabled still did not complete that
case. Both owned test trees were stopped. **Neither attempt is a full-suite pass.**
No imported test or frozen runtime file was edited to hide that result.

As a separate check, the actual staged tree was exported into three fresh
locations with `git checkout-index` under all three `core.autocrlf` settings.
Every one of the 84 imported files matched its pinned source SHA-256 in each
export. This is stronger file coverage but is not a claim that the interrupted
synthetic Git test passed. The new tests and PowerShell parser also passed in
one of those fresh exports. These are source checks, not clean-machine inference.

## Regression caught and corrected

The API helper initially cast any returned content to a string. A deterministic
fixture exposed false passes for a number and an array. It now requires a
nonempty string; empty, null, numeric and array contents all fail. Tests also
cover model mismatch, exact native/Halogen request shapes, redirects, non-local
or credential-bearing URLs, GUFO refusal, path spaces and unsupported actions.
The fake HTTP servers serve tiny fixture responses; no LLM was loaded.

## Not established by this checkpoint

No native or Halogen model was loaded for this publication, and no GPU, WSL,
Docker, BIOS, driver, pagefile, security setting or production client was started
or reconfigured. The existing published inference evidence remains historical.
No persistent GUFO service, common long-running endpoint, cross-engine mutual
exclusion, no-reboot switch, new engine binary or fresh-machine installation is
qualified by these checks. The native release archive still contains only its
original native runtime. No release tag or combined runtime ZIP is created.

The existing native dirty checkout, original WSL2 checkout and GUFO integration
worktree remain separate and are not overwritten. The reviewed source checkpoint
belongs on its own branch; it must not be described as a completed three-engine
service or silently substituted for the existing release.
