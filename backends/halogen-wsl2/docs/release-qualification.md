# Experimental release qualification

Status: **initial experimental package, qualified on the development machine on 25 September 2026**. Portable installation, real answers, API serving, interruption, normal expiry and rollback were exercised below. This is not a fresh Windows/WSL installation or a universal support claim.

**Later incident, same day:** a separate three-full-260k research run with a lower 12 GiB stop threshold froze Windows and required a hard power cycle. The guard's exact-container stop timed out; clean recovery was not verified. The earlier successful cleanup below is a different run. Neither this three-context mode nor the successful two-full-context research mode is installed by the public package. **Guards are not hard host-memory protection.** [Incident, successful pair and raw evidence](benchmarks/parallel260k-20260925.md).

The later publication update changes documentation and adds sanitized evidence plus an offline recount tool; it does not change the 38-file frozen executable package. Post-incident checks are Windows CPU-only: 67 Python tests discovered, 47 passed and 20 Linux-only tests skipped; PowerShell controller/argument round-trip passed, as did both offline native-token recounts. Independent publication review found no remaining critical or important issues. The earlier Linux and live-inference results below are historical, not rerun after the freeze.

## Already measured

- Native sources compiled with GCC 13.3 and reproduced pinned adapter hashes.
- Real placement trace, single 32k, real 260028-token input, and two/three smaller clients passed in the research harness.
- Three full 260k contexts failed guarded startup and recovered without reboot. This mode is not exposed publicly.
- Native planner/bridge and controller/guard tests passed before research runs; independent reviews approved the tested slices.

## Release gates

- Portable CPU tests after review fixes: 62 Windows Python tests discovered (42 passed, 20 explicitly Linux-only skipped). All 20 Linux native fixture tests separately passed. PowerShell controller and actual benign argument-roundtrip checks passed. Independent task specification/quality review approved the package and subsequent fixes.
- Actual installer dry-run and explicit install passed. Both adapters reproduced the exact pinned SHA256 values from this public directory; no compiler-output fallback was used.
- Bounded public `Single32k` passed four 58-input/128-output responses, serial/MTP twice, zero prompt-cache reuse. Full telemetry and exact-container cleanup passed. 152.643 s controller duration. Cold/warm decode observations were 18.528 / 31.350 / 44.384 / 36.813 tok/s in request order; these are not a stable mean.
- `Serve32k -ServeSeconds 60` passed real health and a separate real API response (26 input / 30 output). Deliberate Ctrl-C then stopped the exact container, PID 0, OOMKilled false, no cleanup errors or surviving owned helpers. Shell exit 1 and incomplete final telemetry reflect intentional interruption, not a normally completed benchmark.
- A separate `Serve32k -ServeSeconds 30` completed its window automatically: shell exit 0, four memory observations including final capture, no failure/cleanup errors, terminal PID 0 and OOMKilled false. Controller duration 162.422 s includes cold loading.
- Actual uninstall removed the two generated adapters, machine configuration and installation manifest. Existing run logs and an unmanaged test file remained byte-identical. Reinstallation reproduced the exact adapters again. Models/OS/drivers were never uninstall targets.
- File allowlist, private-path/credential-pattern scan, licenses/notices, prompt/rate arithmetic and staged raw-byte identities checked. Public Git excludes all generated binaries, dependencies, model weights, private machine configuration and runtime dumps.
- Publish only this independent directory. The dirty native sibling and broad private investigation are excluded.

[Sanitized actual package qualification evidence](benchmarks/package-qualification-20260925.json) records the successful and interrupted runs separately. Frozen executable source manifest SHA256: `b5727b7638cc29b60f54cf299333f98023d1292fbef54811f3fe9f90a643bcc8`.

The single-256k and smaller multi-session results were measured using the frozen research controller and identical native/image/profile identities. The portable copies of those two modes have not separately repeated the long/group workload in this packaging check; they remain explicit local qualification commands, not additional benchmark observations.

## Failures retained during packaging

The first portable diagnostic was refused before Docker/model creation: the launch wrapper unnecessarily quoted every WSL switch, which WSL parsed differently from the original benign argv test process. A focused regression now keeps plain switches unquoted; escaping of spaces/quotes/empty strings remains tested. A real selected-WSL command then passed, followed by the actual placement diagnostic (252 ranges, expected wrapper exit 1, terminal PID 0, OOMKilled false, no cleanup errors). The original engine worker's expected diagnostic exit 77 is not directly observed through the wrapper.

An immediate model attempt after the trace was refused at the unchanged 49 GiB launch reserve. The system recovered and a later admitted attempt was used, rather than lowering the threshold. A successful dry-run/diagnostic alone is not model qualification.

Review also corrected Git byte preservation and refusal of linked uninstall manifests. Real temporary Git clones preserve all frozen source bytes under `core.autocrlf=true`, `false` and `input`. Uninstall tests exercise a real Windows directory junction; file-symlink creation was not privileged on this host, so that specific test uses a disclosed metadata fallback.

## Rollback and limits

Stop the foreground launcher before uninstalling. Stopping the exact supervised container removes the process-local bridge; the engine file is untouched. Uninstall only removes manifest-owned generated files. Models, Docker images, WSL, drivers, firmware and manually chosen `.wslconfig` remain yours. Restore manual settings only after stopping their workloads and considering other applications.

One-machine experimental qualification, not a fresh Windows/WSL installation test. Finite foreground serving, not an unattended service. Guards are reaction thresholds: cleanup may undershoot them. The 256k success has little margin. No 120 GB GPU-readback success, fully resident 128 GiB pool, maximum session count, gaming qualification, long-duration stability, or new 27B launcher is claimed.
