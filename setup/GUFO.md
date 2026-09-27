# Optional GUFO static runtime package

The staging command verifies and stages one of two reviewed GUFO server binaries into an independent local runtime directory. It does not build a new binary, start a service, load a model, run GPU checks, or qualify the runtime for use. A separate bounded build command is described below. The persistent start/status/stop workflow remains a later delivery step.

Prerequisites are 64-bit Python 3.12, Windows PowerShell 5.1 or later, and explicit paths to the existing pinned build, TheRock SDK, vcpkg tree, and a separate runtime destination. The default `baseline` identity pins [pixmaate/gufo](https://github.com/pixmaate/gufo) commit `cff564964e8506c0abb3e530cecb55332187ac6c` in `config/gufo-runtime-pins.json`. The explicit `service-ar4k-v1` identity pins source commit `139aa9c58dadcb75c1bd0741aad0823fc65a0547` and its distinct `gufo.exe` (42,439,168 bytes, SHA-256 `66798D3BCAD27B7E2BEC16980B225F83CC3F017FAD9088ADA8D64D604BC4F209`) in `config/gufo-service-runtime-pins.json`. Both use the same TheRock SDK 10.2.0, vcpkg `x64-windows` DLLs, resource trees, and host OpenMP prerequisite. The [GUFO MIT license](https://github.com/pixmaate/gufo/blob/main/LICENSE) and third-party notices need separate review before any redistribution. This command creates a local package only; it does not redistribute AMD binaries or model weights.

The baseline payload is 311,830,580 bytes (about 298 MiB); the service payload is 311,839,796 bytes. Each includes `gufo.exe`, 17 named DLLs, and two gfx1151 resource trees. The destination volume must have the selected payload space plus a 1 GiB reserve. The host must supply the pinned `libomp140.x86_64.dll` from the Windows system directory; it is checked but not copied. The manifest records static identity with status `staged-static-only` and `runtime_qualified: false`.

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

For the reviewed service candidate, use its build directory and add `-RuntimeVariant service-ar4k-v1` to both stage and verify. The Python entry point accepts the same choice as `--runtime-variant service-ar4k-v1`. An omitted choice always selects `baseline`; a package staged under one identity fails verification under the other.

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
has passed offline fixture tests but has not itself been used for a real GUFO
build.

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
