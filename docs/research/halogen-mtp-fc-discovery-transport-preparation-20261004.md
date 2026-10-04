# Fresh model discovery and paired FC transport preparation

Root completed bounded CPU preparation at 2026-10-04T20:04:50.903560+00:00. This adds concrete source
for fresh native model discovery, one fixed epoch coordinator and a resident
container-local pipe relay. No GPU/NPU call, native shim load, engine restart,
driver installation, model change or global WSL change occurred.

## Implemented path

The exact-version native shim observes one original count1 D head and its real
Q8 M1/M4 FC routes without observer device copies. It publishes the464-byte
PID/starttime/model/descriptor/buffer record and a synced native success receipt,
then waits at most2seconds for arming before returning to the native caller.
The head stays registered; the state mutex is released so overlap invalidates
the epoch. Original result/errno and original-once execution are retained.
Four paired shadow responses retain the separate200ms native deadline.

The pure coordinator binds immutable canonical named asset/receipt hashes to a
fresh nonce/epoch/model and consumes sequences0..3 before invoking a candidate.
Invalid/stale/replayed inputs and candidate/reentrancy/abort failures latch.
Both projections must pass the packet validator before either is returned.
Caller-supplied hashes retain provenance; they do not qualify model payloads,
CPU/NPU arithmetic, provider placement or a fresh process on their own.

The relay owns no engine or provider. The future root-owned launcher stages its
pinned sources in the same fresh container as the shim and supplies resident
binary stdin/stdout through Windows/WSL/docker pipes. No Windows-visible /tmp or
cross-mount atomic rename is assumed. Source implements same-uid no-follow
regular files, exact modes/extents, fd/path identity and byte checks, NOREPLACE
rename, process PID/starttime checks and bounded nonblocking Linux pipe waits.
The relay requires the successful original-call/launch receipt before HELLO;
terminal or already-armed discovery rejects before a new handshake.

## Narrow verification and resource evidence

| CPU window | Checks/build | Minimum physical GiB | Minimum commit GiB |
|---|---|---:|---:|
| Pure codec/coordinator/fragmented pipe |13 passed once|34.002|109.330|
| Exact native shim host build |GCC -Werror passed, empty stderr|33.959|109.266|
| Actual Linux file publication |3 passed once|33.916|109.210|

The Linux checks use tiny fresh host fixtures: exact arm publication/no replacement,
FIFO/symlink rejection and mode/extent rejection. They do not execute the relay
entrypoint in a container or qualify Windows/WSL pipe timing. The13 pure checks
include a four-request native-echo bridge with real coordinator API and fragmented
bytes. Native echo is a transport fixture, with all NPU/speed flagsfalse.
All owned jobs and reserve monitors closed. No broad suite was repeated.

Compiled artifact, never loaded:
`/home/revn/halogen-re/libhalogen0162-mtp-fc-quality-9965f26cdf5e476dae2c4ffc02f25cab.so`
SHA256 `2882071c9299771707453b46d47dac8fa9e891556fcc74513ef01a55676a32c3`.
The companion JSON retains source hashes and all three owned-window receipts.

## Current service and remaining qualification

At 2026-10-04T20:01:49.1425503Z, controller PID10048 (creation19:59:38.811622+02:00),
run`c5fd81b1e4cb47b3a6cd3ba1f6ead0cc`, was live and ready at262144 capacity,
authenticated health wasok and active_requests0. The exact user container was
running with Linux host PID915. League of Legends was live as PID20004; earlier
PID28944 is obsolete. These user processes were preserved. The four CPU child
PIDs were absent after verified owned-job closure.

Actual fresh native discovery, canonical payload/graph/provider admission,
container pipe execution/timing, persistent qualified NPU responder, native
projection parity, reset/accepted-prefix lifecycle, output/acceptance and
end-to-end speed remain pending. Shadow mode still executes the original FCs;
useful skip/overlap requires a later separately qualified implementation.

The next exclusive hardware sequence remains native embedding RMS, original FC
oracle, frozen same-source CPU projection screen, then NPU screen with actual
placement proof. Preserve failed evidence and frozen tolerances. No competing
measurement starts while the user server/game is running.

Publication numbers are unchanged:8192 actual input at262144 capacity,
paired prefill1866.537tok/s, MTP decode48.423621tok/s, accepted207/drafted345=60%.
This is not a262K occupied-input measurement. No qualified nonrepetitive260K
actual-input result exists. The full goal remains active and unachieved.

Official engine/driver check at19:38:06–19:42:03UTC found no new version; newly
recorded Reddit/source leads are in [the separate checkpoint](halogen-update-checkpoint-20261004-1936.md).
