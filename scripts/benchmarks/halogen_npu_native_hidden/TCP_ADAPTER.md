# Owned native Windows TCP adapter

`native_tcp_adapter.cpp` is a separate standalone MSVC Windows program. It has
no XRT include, device import or model read. It accepts one explicit privateIPv4
listen address, one pinned privateIPv4 peer, a fixed port and one absolute native
host executable. It never invokes a shell. Forwarded arguments after `--` are
escaped with Windows CRT argv rules and must start with `--serve`.

Offline root build command from existing x64 Native Tools environment:

```powershell
cl.exe /nologo /std:c++17 /Zc:__cplusplus /EHsc /O2 native_tcp_adapter.cpp /Fe:native_tcp_adapter.exe /link ws2_32.lib bcrypt.lib
```

This command compiles only the adapter. It does not launch a child or device.
The package `build.ps1` also compiles the adapter. The reviewed
`host-short-cohort.patch` has now been applied to `host.cpp`; the retained patch
records that source change and must not be applied a second time. It admits clean stdin EOF only before
any byte of the next REQUEST frame, counts actual completed replies0..64, and
retains the host after reply63 until owner closes stdin. Partial header/payload
EOF remains a session failure. It does not change the finite core budget.

Runtime skeleton, only under the root-owned external process/job guard:

```text
native_tcp_adapter.exe --bind-address CAPTURED_WINDOWS_PRIVATE_IPV4
 --peer-address CAPTURED_LINUX_PRIVATE_IPV4 --port OWNED_FIXED_PORT
 --host-exe C:\absolute\native-hidden-build\host.exe
 --accept-ms 10000 --io-ms 10000 --deadline-ms 80000 --shutdown-ms 5000
 --report C:\owned\adapter-result.json
 -- --serve ALL_PINNED_NATIVE_HOST_ARGUMENTS
```

The listener uses SO_EXCLUSIVEADDRUSE and the accepted connection uses
TCP_NODELAY. Address parsing rejects hostname/public/wildcard/loopback endpoints.
The adapter permits only one connection and creates one suspended native child.
Windows10+ atomically assigns that child to its own KILL_ON_JOB_CLOSE job through
PROC_THREAD_ATTRIBUTE_JOB_LIST during CreateProcess, before resume, and limits
inherited handles to stdin, stdout and the root-captured stderr. Parent pipe
endpoints are overlapped, uniquely named, remote-client-rejecting byte pipes.
Child ends are synchronous stdio handles compatible with the native host.
An unavailable job-list attribute fails creation without a child; there is no
fallback that can leave an unassigned suspended process behind.

HELLO/READY and each REQUEST/RESPONSE have exact kind/sequence/extent/SHA checks.
The native host admits full CLI-pinned process/model/graph/nonce/epoch/input and
request bindings. Adapter also requires response header to echo the complete
request except magic, verifies response digest and all finite BF16 output words.
It fully buffers and validates the complete response before writing any reply
bytes. TCP and pipe writes can still fail partially; that closes/latches the
owned session. No error response frames or retry/relaunch are emitted.

All TCP I/O uses nonblocking sockets with blocking select until finite stage or
whole-process deadlines. Parent pipe I/O uses overlapped event/child-process
waits; timeout cancels and drains the pending operation within two1-second
cleanup waits. If cancellation still cannot drain after killing only the owned
child job, adapter fail-stops itself so no pending OVERLAPPED/buffer is freed
while kernel I/O can still access it. The outer process/job guard remains
mandatory for CreateProcess, job/pipe setup, output capture and cleanup APIs.

After reply63, adapter retains the host and pipe/socket endpoints until the
owner closes the socket. Any trailing byte fails. Earlier owner close is clean
only with zero bytes of the next frame; the adapter closes host stdin, waits
within shutdown deadline and requires child exit0. It never silently reclassifies
host exit1 as success.

Reports include actual completed calls and per-call socket receive/validation,
pipe write, native roundtrip/read/validation and socket reply-write durations.
They are component transport timings. Full-head timing also needs the Linux
bridge, HIP readiness/readback/publication and original head owner interval.
Source is uncompiled/unexecuted in this handoff; root owns compile/review and
later guarded operation.
