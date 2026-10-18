# Owned binary pipe adapter contract

`scripts/benchmarks/halogen_mtp_fc_owned_pipe.py` is source-only implementation,
awaiting ROOT's import and Windows lifecycle checks. Import launches no process.
It compiles the exact pinned bytes of `server/winjob.py` and inherits its retained
identity/job/exit methods; private ctypes/API use requires explicit source-pin
review if the base changes. The base file was not edited.

Construct `OwnedBinaryProcess(argv, cwd=..., env=..., stderr_path=...,
source_sha256=<independently hashed adapter>, live_guard=<bounded callback>,
cancel_event=<external Event>, lifetime_seconds=45, io_timeout_seconds=45)`.
Optional byte budgets cap each read/write at65536 and each direction at1 MiB.
The constructor captures `.identity` while suspended before `.resume()`.
Use `.reader.read(n)` and `.writer.write(bytes)/flush()` with the transport codec.
Use `.set_io_deadline(absolute_monotonic_deadline)` for a tighter protocol phase;
`.clear_io_deadline()` restores the bounded operation/overall lifetime limits.
ROOT must set the appropriate arm/reply deadlines; default45 s is only the outer
relay lifetime and does not qualify2-s arm or200-ms response timing.

All owner methods and pipe operations run on the constructor's guardian thread.
Another thread may set the supplied cancellation event. The two non-daemon I/O
workers have only pipe handles and duplicated own-thread handles; they never own
child/job cancellation. `live_guard` must return promptly and must supervise the
separately owned native engine/container/memory. A terminal exit0 child may have
its final frame drained from this retained pipe; new writes require a live child.

Always call `.close()` in guardian-thread `finally`. It first uses the inherited
retained job to kill/prove local child terminal, then cancels synchronous worker
I/O, joins workers, and closes pipes/thread handles. Unconfirmed steps raise with
`.owner` attached for guardian-thread retry and retain `.cleanup_evidence`.
`.exit_code()` stays compatible after closure. ROOT independently proves exact-ID
Docker container/exec cleanup; `remote_cleanup_proven` always remains false here.
The adapter creates no daemon monitor, provider, engine, listener or container.
