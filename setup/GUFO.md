# Optional GUFO static runtime package

This experimental Windows command verifies and stages one reviewed GUFO server binary. It creates an independent local runtime directory. It does not build a new binary, start a service, load a model, run GPU checks, or qualify the runtime for use. The bounded build command and persistent start/status/stop workflow are later delivery steps.

Prerequisites are 64-bit Python 3.12, Windows PowerShell 5.1 or later, and explicit paths to the existing pinned build, TheRock SDK, vcpkg tree, and a separate runtime destination. The reviewed tuple is [pixmaate/gufo](https://github.com/pixmaate/gufo) commit `cff564964e8506c0abb3e530cecb55332187ac6c`, [TheRock](https://github.com/ROCm/TheRock) SDK 10.2.0, and [vcpkg](https://github.com/microsoft/vcpkg) installed `x64-windows` DLLs at the hashes in `config/gufo-runtime-pins.json`. The [GUFO MIT license](https://github.com/pixmaate/gufo/blob/main/LICENSE) and third-party notices need separate review before any redistribution. This command creates a local package only; it does not redistribute AMD binaries or model weights.

The expected payload is 311,830,580 bytes (about 298 MiB): `gufo.exe`, 17 named DLLs, and two gfx1151 resource trees. The destination volume must have that payload space plus a 1 GiB reserve. The host must supply the pinned `libomp140.x86_64.dll` from the Windows system directory; it is checked but not copied. The manifest records static identity and keeps `runtime_qualified` false.

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

The stage operation verifies every source and destination byte against the fixed portable policy. It refuses unknown nonempty destinations and does not overwrite files. Verify is read-only and works after moving a valid package, provided the current host still supplies the OpenMP prerequisite. A newly built `gufo.exe` with a different hash needs a newly reviewed package policy; it is not equivalent to this pinned binary.

Rollback means stop selecting this optional runtime in a later launcher configuration. Neither stage nor verify removes a package. If removal is desired, review the exact runtime path and remove it explicitly outside this command.

## Separate request-policy source extension

The optional [AR4K source patch](../engine-patches/gufo/README.md) adds reviewed
engine-side request limits and has passed focused native CPU tests. It is not
the binary pinned by this staging command. Its GPU build, runtime identity and
persistent-service qualification remain separate, unfinished delivery steps.
