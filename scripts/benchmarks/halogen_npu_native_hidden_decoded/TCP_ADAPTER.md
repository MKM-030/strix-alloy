# Owned Windows TCP adapter for the once-decoded variant

The adapter source is copied unchanged from the reviewed native H package. It
does not import XRT or read model weights. `build.ps1` compiles it offline with
MSVC C++17, ws2_32.lib and bcrypt.lib. Runtime requires the external root-owned
process/job guard and forwards all pinned arguments to this variant's `host.exe`:

```text
native_tcp_adapter.exe --bind-address CAPTURED_WINDOWS_PRIVATE_IPV4
 --peer-address CAPTURED_LINUX_PRIVATE_IPV4 --port OWNED_FIXED_PORT
 --host-exe C:\absolute\native-hidden-decoded-build\host.exe
 --accept-ms 10000 --io-ms 10000 --deadline-ms 80000 --shutdown-ms 5000
 --report C:\owned\adapter-result.json -- --serve ALL_PINNED_HOST_ARGUMENTS
```

One explicit privateIPv4 socket accepts one pinned peer, closes the listener,
and enables TCP_NODELAY. One suspended child is atomically assigned to the
adapter's KILL_ON_JOB_CLOSE job through Windows10+ PROC_THREAD_ATTRIBUTE_JOB_LIST
during CreateProcess; ResumeThread must report exactly one prior suspension.
Only stdin/stdout/stderr handles inherit. Parent endpoints are uniquely named
overlapped byte pipes rejecting remote clients; child endpoints are synchronous
stdio pipes. There is no shell, Python hot relay, or per-request child.

All56B outer-frame kinds/sequences/extents/digests are checked. The native host
admits full process/model/graph/nonce/epoch/input/request bindings. Adapter checks
exact response-header echo, response digest and finite BF16 before forwarding the
whole assembled reply. Partial sends fail the owned session; no error frame or
retry is emitted. TCP select and pipe event/process waits use finite stage/overall
deadlines. Pending pipe operations cancel/drain within two1-second cleanup waits;
unconfirmed cancellation kills only the owned job then fail-stops adapter itself
to preserve OVERLAPPED/buffer lifetime. The outer deadline remains mandatory.

Clean owner EOF occurs only before any byte of a next REQUEST frame. Completed
calls0..64 are reported. After reply63 adapter keeps the host/endpoints resident
until owner closes the socket; any trailing byte fails. It then closes host stdin
and requires child exit0 within shutdown deadline. The host's shorter-cohort
change is already present; no patch needs applying to this package.

The adapter records per-call receive/validation, pipe write, native roundtrip/
response validation and TCP reply-write costs. Full-head results additionally
need Linux bridge and HIP readiness/readback/publication intervals. Source is
uncompiled/unexecuted as part of this handoff.
