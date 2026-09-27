# Optional GUFO static runtime package

The staging command verifies and stages one of three pinned GUFO server binaries into an independent local runtime directory. It does not build a new binary, start a service, load a model, run GPU checks, or qualify the runtime for use. A separate bounded build command is described below. The installed start/print-only/status/stop controller is implemented and independently reviewed offline; real persistent-service qualification remains incomplete, so activation refuses.

Prerequisites are 64-bit Python 3.12, Windows PowerShell 5.1 or later, and explicit paths to the existing pinned build, TheRock SDK, vcpkg tree, and a separate runtime destination. The default `baseline` identity pins [pixmaate/gufo](https://github.com/pixmaate/gufo) commit `cff564964e8506c0abb3e530cecb55332187ac6c` in `config/gufo-runtime-pins.json`. The explicit `service-ar4k-v1` identity pins source commit `139aa9c58dadcb75c1bd0741aad0823fc65a0547` and its distinct `gufo.exe` (42,439,168 bytes, SHA-256 `66798D3BCAD27B7E2BEC16980B225F83CC3F017FAD9088ADA8D64D604BC4F209`) in `config/gufo-service-runtime-pins.json`. Both use the same TheRock SDK 10.2.0, vcpkg `x64-windows` DLLs, resource trees, and host OpenMP prerequisite. The [GUFO MIT license](https://github.com/pixmaate/gufo/blob/main/LICENSE) and third-party notices need separate review before any redistribution. This command creates a local package only; it does not redistribute AMD binaries or model weights.

The baseline payload is 311,830,580 bytes (about 298 MiB); the historical service payload is 311,839,796 bytes and the header-fixed service payload is 311,840,820 bytes. Each includes `gufo.exe`, 17 named DLLs, and two gfx1151 resource trees. The destination volume must have the selected payload space plus a 1 GiB reserve. The host must supply the pinned `libomp140.x86_64.dll` from the Windows system directory; it is checked but not copied. The manifest records static identity with status `staged-static-only` and `runtime_qualified: false`.

From this repository root, use explicit paths:

```powershell
& .\setup\stage-gufo-runtime.ps1 `
  -PythonExe 'C:\Path\To\Python312\python.exe' `
  -BuildDir 'C:\Path\To\Existing\Build' `
  -SdkDir 'C:\Path\To\TheRock-10.2.0' `
  -VcpkgDir 'C:\Path\To\vcpkg' `
  -RuntimeDir 'C:\Path\To\Independent\GUFO-Runtime'

& .\setup\stage-gufo-runtime.ps1 `
  -PythonExe 'C:\Path\To\Python312\python.exe' `
  -Verify -RuntimeDir 'C:\Path\To\Independent\GUFO-Runtime'
```

For the historical service candidate, use its build directory and add `-RuntimeVariant service-ar4k-v1` to both stage and verify. The new header-fixed candidate uses `-RuntimeVariant service-ar4k-header-v1`, the completed build at `C:\Projects\strix-alloy-research\build\gufo-service-header-frontdoor-20260927`, and a distinct destination such as `C:\Projects\strix-alloy-research\runtimes\gufo-native-service-header-e6feed7-therock10.2`. Its policy is `config/gufo-service-header-runtime-pins.json`: clean source `e6feed7ca52df4661d10434c72a8ea5b5f054bc2`, tree `7912be2688d6874c0e13f4723aad00a5c3cbe1cf`, and `gufo.exe` 42,440,192 bytes with SHA-256 `9682019A5198B19CA131D60298A1E896186099ACC971C17B04BB31E302F7FFE9`. The Python entry point accepts the same variant names. An omitted choice selects `baseline`; verification under a different identity fails.

The stage operation verifies every source and destination byte against the selected fixed policy. It refuses unknown nonempty destinations and does not overwrite files. Verify is read-only and works after moving a valid package, provided the current host still supplies the OpenMP prerequisite. Any different `gufo.exe` requires a newly reviewed package policy. Successful staging is not service qualification.

Rollback means stop selecting this optional runtime in a later launcher configuration. Neither stage nor verify removes a package. If removal is desired, review the exact runtime path and remove it explicitly outside this command.

## Separate request-policy source extension

The optional [AR4K source patch](../engine-patches/gufo/README.md) adds reviewed
engine-side request limits and has passed focused native CPU tests. A separate
native HIP build of that reviewed source has also succeeded. Its executable is
pinned by the explicit `service-ar4k-v1` static runtime identity above.
Persistent-service qualification remains a separate delivery step.

## Build the reviewed source extension

`build-gufo-windows.ps1` configures and compiles only the `gufo` target from a
clean source checkout. It does not execute GUFO, run tests, copy runtime files,
or change the fixed staging policies above. A new `gufo.exe` hash requires a later
review and runtime policy update before staging. The build manifest always says
`runtimeStaged: false` and `runtime_qualified: false`. This reusable entrypoint
has passed offline fixture tests and a real two-job HIP build on the target
Windows host (27 September). An identical second invocation verified and reused
the completed build without recompiling. Its new executable hash differs from
the staged candidate; it is not automatically accepted by the static runtime
policy and has not been executed. This proves the build workflow, not bit-for-bit
reproducibility, clean-machine installation or runtime qualification. Local
evidence: `C:\Projects\strix-alloy-research\reports\gufo-build-frontdoor-validation-20260927.md`.

Start with the reviewed [source patch](../engine-patches/gufo/README.md) applied
to upstream `cff564964e8506c0abb3e530cecb55332187ac6c` and committed in a
clean checkout. The build gate checks the exact reviewed content tree
`273d84974a604c81023dae15d379a9bfc0b1c29b`, the upstream base ancestor,
origin URL, and clean tracked/untracked status. Your resulting commit ID may
differ from the reviewer's commit. The manifest records both identities and
uses your actual commit ID for `GUFO_VERSION`.

Use explicit local paths for every tool and input. For example:

```powershell
& .\setup\build-gufo-windows.ps1 `
  -PythonExe 'C:\Path\To\Python312\python.exe' `
  -GitExe 'C:\Path\To\Git\bin\git.exe' `
  -SourceDir 'C:\Path\To\Clean\ReviewedGufo' `
  -BuildDir 'C:\Path\To\New\gufo-service-build' `
  -SdkDir 'C:\Path\To\TheRock-10.2.0' `
  -VcpkgDir 'C:\Path\To\Pinned\vcpkg' `
  -VcVars64 'C:\Path\To\VS2022\VC\Auxiliary\Build\vcvars64.bat' `
  -CMakeExe 'C:\Path\To\cmake.exe' `
  -NinjaExe 'C:\Path\To\ninja.exe' `
  -Jobs 2
```

The omitted `-BuildRecipe` selects the historical `service-ar4k-v1` source and
build pins. To select the separately reviewed header-fixed source in a new
build directory, add `-BuildRecipe service-ar4k-header-v1` and point `-SourceDir`
at a clean checkout with tree
`7912be2688d6874c0e13f4723aad00a5c3cbe1cf`. This recipe uses
`config/gufo-header-build-pins.json` and the complete
`engine-patches/gufo/service-header-v1/` export. The reviewed build completed
in a distinct directory; its static runtime identity is the separate
`service-ar4k-header-v1` policy above. Runtime staging, model execution and
service qualification remain pending.

`-Jobs` accepts only 1 or 2. The command requires 24 GiB available physical
memory and 25 GiB free on the build volume at entry and throughout configure
and compile. It imports VS tools only into the child build environment and
disables vcpkg manifest acquisition. The reviewed TheRock 10.2.0 compiler
combination remains experimental. A successful build creates
`<BuildDir>/build-manifest.json`, plus separate configure/build stdout and
stderr logs. The manifest records source, SDK, compiler, VS/Windows SDK,
vcpkg ports and DLLs, commands, effective CMake cache, and executable hash.
Failed or incomplete build directories retain their evidence and must be
reviewed manually; the command does not erase or automatically resume them.

## Finite service-policy smoke

The separate `ar4k-service-policy-smoke-v1` adapter runs the existing private,
one-request guardian against the reviewed `139aa9c` source/tree and the complete
`service-ar4k-v1` package at
`C:\Projects\strix-alloy-research\runtimes\gufo-native-service-139aa9c-therock10.2`.
Historical operator results retain their original `cff564` source identity.

Local qualification status (27 September): the new candidate loaded and
answered the fixed request correctly, then exited successfully. The overall
attempt failed memory recovery: available Windows RAM remained below the
required49GiB. Its consumed-attempt and incomplete-cleanup records are retained;
do not clear them or replay the profile. Persistent service is not qualified.
Local evidence: `C:\Projects\strix-alloy-research\reports\gufo-service-policy-smoke-validation-20260927.md`.

The separate `python -m gufo_control.service_recovery` command is bound to that
exact failed run. Its implementation has passed independent review, but the
live audit has not been run: subsequent available-memory readings remain below
49 GiB. Once its live prerequisites hold, it can observe present memory
recovery without launching GUFO, then archive only that run's verified
incomplete latch under a separate operator blocker. A late certificate means
`present_recovery_observed_later`; it leaves the original result failed, does
not certify recovery within the original deadline, and does not authorize a
new model attempt or qualify persistent service. Review the exact current
prerequisites and evidence before invoking its one-time audit; do not consume
it against a known failed memory floor or erase prior disposition artifacts.

From this repository, inspect the fixed profile without launching GUFO:

```powershell
$env:PYTHONPATH = 'scripts'
python -m gufo_control.service_smoke status
python -m gufo_control.service_smoke print-only
```

`print-only` checks static prerequisites and port availability; it never creates
an attempt or qualification. The exact
`reports/gufo-service-policy-smoke-v1-qualification.json` binding was supplied
for the recorded attempt, which is now consumed. Historical qualification does
not permit a second run; the retained failure also blocks related profiles.
The adapter never creates or renews its own authorization.

The recorded `python -m gufo_control.service_smoke run` attempted exactly the
fixed public greedy 2+2 request: AR, context 4096, complete framed
input at most 512 tokens, output at most 64, one session/pending slot, no
thinking/preservation, speculation, vision or cache lookup/disk cache. It uses
loopback 8836, a private per-run key, three HTTP workers, 16 KiB input and 1 MiB
output limits; no retry or warmup is provided. Startup/request/lifetime limits
are 480/60/600 seconds; cleanup/recovery limits are 10/60 seconds.
This is the consumed experiment's recipe, not a reusable launch command.
Another experiment needs a separate reviewed identity and fresh admission
after the historical recovery failure has been reconciled.

The independently reviewed allowances are GPU/host/shared 68/4/20 GiB, with
49 GiB launch, 24 GiB runtime and 12 GiB commit reserves. Fresh correctly scoped
telemetry and the original/current stricter baselines remain mandatory; floors
are stop conditions, not reservations. Source/tree, full runtime package,
qualification, model descriptors and projector absence are rechecked before
creation and resume. Rechecks retain the existing freshness deadlines.

Evidence is separate in `reports/gufo-service-policy-smoke-v1-runs`. A consumed
attempt remains consumed after cleanup, and incomplete cleanup blocks related
old and new profiles in both directions. Success proves only this finite
request; it does not qualify persistent serving or change launch settings.
