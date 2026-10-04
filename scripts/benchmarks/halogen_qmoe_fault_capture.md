# QMoEBf Windows fault-address collector

Source-only observer for one root-owned diagnosis. It never loads a runtime,
launches hardware, reads tensor/model memory, walks a stack, or creates a dump.
`DllMain` only returns `TRUE`. All exception paths return
`EXCEPTION_CONTINUE_SEARCH` and restore the interrupted thread's Win32
`LastError`; context and exception records are never modified.

Exports use the native Windows x64 C ABI:

- `DWORD __cdecl start_capture(const WCHAR *path)`: zero means armed; otherwise
  returns a Win32 error code. Supply a valid NUL-terminated UTF-16 absolute local
  drive path with backslashes, an existing parent directory controlled by root,
  and a fresh filename. It rejects alternate streams and uses `CREATE_NEW` and
  `FILE_SHARE_READ`; it never overwrites or deletes a file. A failed arm may leave
  an empty file. One successful arm is permitted per loaded DLL lifetime.
- `DWORD __cdecl stop_capture(void)`: zero means disabled, removed, and closed.
  Call from an ordinary host thread after inference has quiesced. It waits for
  any current metadata writer and therefore can wait indefinitely on stalled
  filesystem I/O. Keep the DLL loaded for the entire process lifetime; removing
  the VEH does not establish that every dispatched callback has returned.

Arm after session admission and runtime DLL loading, immediately before the
first run. The output is ASCII JSON Lines: at most eight attempted access-
violation records, each at most 8192 bytes, containing OS exception metadata,
RIP, a module-relative offset if found, and x64 general/control register values.
It includes no instruction bytes, stack bytes, vector-register values, or data
at the fault address. Other exception codes are ignored. An empty file does not
prove no failure: fail-fast/termination can bypass VEH, and I/O can fail.

Module paths/base/size are snapshotted before installing VEH. The handler only
searches collector-owned immutable entries; it never calls loader APIs or probes
memory. The snapshot is limited to 512 modules and 1023 UTF-16 path code units
(truncation is flagged). Newly loaded modules are unknown. Unload/reload or base
reuse can make attribution stale; record RIP remains exact. The caller must
avoid concurrent module changes across arming and the diagnostic run.

The handler serializes with a non-waiting interlocked gate: simultaneous or
recursive AVs skip logging, and attempted writes count against the limit even
if they fail. One synchronous `WriteFile` per record is best effort and may
block, partially write, or fault in an already damaged process. The observer
adds callback/I/O timing and supplies first-chance metadata, not proof that an
AV was fatal or that execution reached an accelerator.

Existing MSVC 14.44.35207 / SDK 10.0.26100.0 build, from the repository root:

```powershell
& 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe' /nologo /c /TC /O2 /W4 /WX /GS- /Zl /Brepro /I'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/include' /I'C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/um' /I'C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/shared' /I'C:/Program Files (x86)/Windows Kits/10/Include/10.0.26100.0/ucrt' /Fo'server/.local/optimization9h-20261004/qmoe-fault-capture-build/halogen_qmoe_fault_capture.obj' 'scripts/benchmarks/halogen_qmoe_fault_capture.c'
& 'C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/link.exe' /nologo /DLL /MACHINE:X64 /NODEFAULTLIB /ENTRY:DllMain /Brepro /INCREMENTAL:NO /NOIMPLIB /NOEXP /OUT:'server/.local/optimization9h-20261004/qmoe-fault-capture-build/halogen_qmoe_fault_capture.dll' /LIBPATH:'C:/Program Files (x86)/Windows Kits/10/Lib/10.0.26100.0/um/x64' 'server/.local/optimization9h-20261004/qmoe-fault-capture-build/halogen_qmoe_fault_capture.obj' kernel32.lib
```

Create the ignored build directory before running the commands. `/GS-` and
`/NODEFAULTLIB` avoid CRT cookie/initialization dependencies; bounded formatting
uses static buffers. Build/PE inspection is permitted; DLL loading or execution
belongs to root's explicitly pinned probe. No runtime validation is claimed.

Root subsequently loaded the pinned DLL for the owned QMoEBf attempt
`qmoe-light-admission-d35f5a8b9b034d63a4f58faf0850e933`. Its first inference
invocation terminated with access violation `0xc0000005`; one retained record
located the instruction in System32 `xrt_coreutil.dll` at RVA `0xf2186` and
reported a null read. This exercises loading, arming and one exception record;
it does not qualify all handler limits or normal stop behavior. The child crash
bypassed Python cleanup; the parent closed its owned job. Static instruction
attribution is recorded in
`docs/research/halogen-qmoe-xrt-fault-20261004.md`.
