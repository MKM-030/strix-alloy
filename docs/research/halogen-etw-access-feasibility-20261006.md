# ETW access feasibility — 2026-10-06

**The existing tokens qualify for ordinary ETW access by default, but this read-only check cannot prove that the installed DxgKrnl provider can be enabled.** The installed native compiler and SDK prerequisites are present. No trace or enablement test occurred.

## Token and identity evidence

The current execution observer was Python PID `19552`, birth `134357933570915540`, executable `C:\Users\Marcel\AppData\Local\Programs\Python\Python313\python.exe`. Its inherited execution token was **not elevated**, elevation type **limited**, integrity SID `S-1-16-8192` (medium).

The retained console's native handle matched the parent-provided identity **before** its token was queried:

- PID `5136`
- Creation time `134357918635702746` (Windows 100-ns units)
- Executable `C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe`

The same native identity remained stable after the token query. The console token was also **not elevated / limited / medium**. Neither checked token provides an elevated console route.

Both tokens had:

- Administrators `S-1-5-32-544`: **deny-only**, not enabled.
- Performance Log Users `S-1-5-32-559`: **enabled**, attributes `0x7`.
- `SeSystemProfilePrivilege`: **absent** from the queried privilege list.
- `SeChangeNotifyPrivilege`: enabled; shutdown, undock, working-set and time-zone privileges were present but disabled.

Process handles used only `PROCESS_QUERY_LIMITED_INFORMATION`; token handles used only `TOKEN_QUERY`. No token was duplicated or used to execute anything. Identity came from `QueryFullProcessImageNameW` and `GetProcessTimes`; token values came from `GetTokenInformation`.

Parent-provided expected identity source: `server/.local/optimization9h-20261004/continuation-frontier-final-20261006-evening.json`; authoritative current state: `continuation-current.json`. This check matched the supplied identity against native handle results; it did not reread those receipts or inspect the rejected audit.

The current execution observation does not certify the token of every Codex GUI/broker process. It establishes the token available to this tool-launched observer and the specifically retained console.

## Provider security and concrete conclusion

`EventAccessQuery` was available in Advapi32 and was called once for provider GUID `802ec45a-1e99-4b83-9920-87c98277ba9d`. It returned **ERROR_ACCESS_DENIED (5)** on the initial size query, with no security descriptor or required size returned.

That denial establishes only that this security-descriptor query did not succeed. It does **not** establish that `TRACELOG_GUID_ENABLE` is denied. No provider ACL was available for evaluating enable rights. [EventAccessQuery](https://learn.microsoft.com/en-us/windows/win32/api/evntcons/nf-evntcons-eventaccessquery)

Enabled Performance Log Users membership is the documented default eligibility for ordinary cross-process session creation and provider enablement; administrative elevation and `SeSystemProfilePrivilege` are not universal prerequisites for this ordinary file-mode path. The NT Kernel Logger has separate restrictions. [StartTraceW](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-starttracew), [EnableTraceEx2](https://learn.microsoft.com/en-us/windows/win32/api/evntrace/nf-evntrace-enabletraceex2)

Provider GUID permissions can independently restrict enablement. Therefore the exact answer is: **ordinary-session default access is supported by the current token; actual installed DxgKrnl enable authorization remains unknown.** Neither success nor denial can be certified from these observations. [EventAccessControl](https://learn.microsoft.com/en-us/windows/win32/api/evntcons/nf-evntcons-eventaccesscontrol)

A prospective native recorder can be implemented with these existing tokens and must handle eventual `StartTrace`/`EnableTraceEx2` results fail-closed. No privilege workaround or renewed elevation action is proposed.

## Installed native build prerequisites

Read-only file/version inspection verified:

- Compiler: `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\cl.exe`, version `19.44.35228.0`.
- Linker: `C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Tools\MSVC\14.44.35207\bin\Hostx64\x64\link.exe`, version `14.44.35228.0`.
- MSVC headers and x64 `libcmt.lib`/`msvcrt.lib` under the same MSVC version.
- Windows SDK `10.0.26100.0` headers: `shared/evntrace.h`, `shared/evntprov.h`, `um/evntcons.h`, `um/tdh.h`, `um/Windows.h`.
- SDK x64 libraries: `tdh.lib`, `advapi32.lib`, `kernel32.lib`, `ucrt.lib`, `libucrt.lib`.
- Headers declare the controller, consumer and TDH functions needed by the prospective design; `EVENT_TRACE_NO_PER_PROCESSOR_BUFFERING` is `0x10000000`.

The current PowerShell PATH does not resolve `cl` or `link`; CMake resolves. Existing `VsDevCmd.bat` and `vcvars64.bat` setup scripts were found but not run. Root can use explicit installed compiler/SDK paths during implementation. Compilation/linking remain unverified. The JSON companion records absolute header/library/setup paths.

## Actions and limits

`trace=false`: no `StartTrace`, `EnableTraceEx2`, WPR, capture, UAC/RunAs, token duplication, group/privilege changes, installation, server/lifecycle action or GPU/NPU operation occurred. The rejected native-controller audit was neither inspected nor repeated.

This note does not qualify any speed gain, resolve historical copy ownership, verify build execution, or test event delivery/rundown/file writing. Attribution remains **not attributed**.
