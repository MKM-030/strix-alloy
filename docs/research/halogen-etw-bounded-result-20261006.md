# Bounded Windows GPU trace result — 6 October 2026

The installed DxgKrnl provider accepted an ordinary five-second file trace. The
recorder closed exactly its own returned session handle and the offline decoder
materialized all 8,454 captured DxgKrnl events. The controller reports no lost
events or log buffers. This establishes a working supported capture path on this
host; **it does not establish Halogen copy ownership or acceleration**.

The foreground HistoricalStock server stayed ready and open. Its native console,
controller and backend identities were checked exactly before and after capture,
along with authenticated health, container identity and image digest. No
inference request, engine restart, NPU operation, privilege adjustment, provider
ACL change or installation occurred. A pre-capture process observation found
Riot client/background crash handling, without a League game process. A GPU
counter snapshot showed only System copy activity above 0.1%; that snapshot is
not an ownership proof or a timed benchmark interval.

| Evidence | Actual result |
|---|---|
| StartTrace / EnableTraceEx2 / final QUERY / STOP | All returned 0 |
| Requested / observed ETW pool | 64 × 64 KiB = 4 MiB; unchanged |
| Sequential ETL | 1,179,648 bytes; cap 67,108,864 bytes |
| Requested interval | 5 seconds, completed |
| Recorder monitor | 50 samples; maximum gap 112.137 ms |
| Minimum physical / commit headroom during recorder | 27,691,859,968 / 126,910,337,024 bytes |
| Recorder maximum private commit | 786,432 bytes |
| Decoder selected events written | 8,454; no unresolved property materializations |
| Decoder maximum private commit | 4,747,264 bytes |
| Recorder final event / log-buffer / realtime-buffer losses | 0 / 0 / 0 |
| Complete lifetimes/rundown, allocation beneficiary, Halogen attribution | Unresolved |
| New Prefill, Decode or native acceptance values | None measured |

Both C programs compiled under installed x64 MSVC 14.44 with `/W4 /WX /O2 /MT`.
The recorder's receipt writes and flushes are checked: startup/query receipt
failure goes to owned-handle cleanup before provider enable, and final receipt
failure returns nonzero. Independent static review checked this repair. The
decoder uses system commit headroom and correctly labels the ETL header buffer
size in bytes. A recorder `--plan` call returned `session_api_called=false`.
No broad inference/test matrix was run.

The first initial decoder build rejected duplicate command-line Unicode defines;
its original build receipt remains retained. Removing the duplicate command-line
defines fixed the build command. The final rebuilt binaries and sources have a
separate fresh receipt. A root helper was first invoked with the base Python
interpreter, which lacked `aiohttp`; it failed during import before any trace.
Using the existing project environment completed the single actual capture.

The decoder intentionally does not substitute its header counters for the
recorder's final ControlTrace counters. The [combined receipt](halogen-etw-bounded-result-20261006.json)
joins the started/queried/final session records and retains both sets. Reported
zero loss is narrower than complete relevant coverage: no capture-state/rundown
request was made, the trace was idle, and existing object lifetimes and semantic
bridges remain unavailable. A successful raw property materialization likewise
does not resolve a handle namespace or owner.

The earlier access-feasibility receipt's PowerShell JSON serialization rounded
64-bit FILETIME values. It remains historical discovery evidence; this capture
uses exact native Python integers and checks the original process birth values.
Neither ordinary trace eligibility nor provider enable is blocked by the
previously observed inability to read the provider security descriptor.

The [observed coverage review](halogen-etw-observed-coverage-20261006.md) determines
which event families actually arrived. Do not repeat this idle capture merely to
expand an inventory. A new engine comparison needs a concrete supported
attribution mechanism and a frozen workload. The unqualified checked-copy
observations (+1.19% prefill and +2.17% decode) remain unqualified and disabled.
The complete acceleration goal remains unachieved.

Raw artifacts are retained locally in
`server/.local/optimization9h-20261004/etw-native-build-3bc6e3f283a541b9afd2c4a47d7f7bdc/`.
They include the ETL, streamed TDH records, exact recorder receipts, compiler
output, identity observations and source/binary pins. Raw machine pointers and
trace records are not published as an ownership finding.
