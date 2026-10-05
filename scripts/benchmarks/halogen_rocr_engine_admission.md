# Private ROCr engine measurement admission

This is a source-only startup and maintenance change. ROOT owns independent
review, any local Python validation, runtime admission, stop/start, measurement,
and rollback. No server, container, model, provider, or authored helper was run
while preparing these files.

The opt-in `engine.private_hsa` object has exactly `receipt` and
`receipt_sha256`. It passes through `server/controller.py`, backend `Start.ps1`,
and backend `scripts/service.py`. Default profiles do not add a private mount.
An admitted profile uses the original image digest and the existing one-slot
service, memory admission, independent 18 GiB physical/commit guards, exact
container ownership, cleanup, and recovery. Only this destination is added to
the existing read-only mount list:

`/usr/local/lib/python3.12/site-packages/_rocm_sdk_core/lib/libhsa-runtime64.so.1`

The module reads and hashes regular local files; it does not load any library.
Admission and revalidation before both container creation and start require the
complete static ABI gate, the successful three-variant component receipt,
each bound component probe receipt, and both frozen parity comparisons. The
private library's bytes and file identity must stay unchanged. The frozen
private variants are source_stock
`2ba2eafa07cfcedb3754a7708858f2c054bc07c9e4e24fe4820b5340cda95af5`
and candidate
`cf1f4447cd92330c6a551042eff1ad95de2df4e276c09dfbfe7a252b5fa89434`.

The engine scope is v2, capacity 262144, cache Off, MTP draft length 2,
`HALOGEN_PLD=3,3`, and otherwise ordinary service controls. The gateway keeps
concurrency 1 and reserve 18 GiB. This admission qualifies a measured trial;
it does not adopt a candidate or establish token speed or acceptance.

## Frozen profile data

The original profile is
`C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/pld-stock8k.json`,
SHA-256 `39faa5d1c98289be76d76a396aafd6ae4fe44cba673e61354a8d63f4540b3de7`.
Keep these original bytes intact and use this exact profile for restoration.

For a private copied profile, add only the appropriate `engine.private_hsa`:

```json
{
  "receipt": "C:\\Projects\\strix-alloy-clean\\server\\.local\\optimization9h-20261004\\rocr-engine-candidate-admission.json",
  "receipt_sha256": "2872496e0aa8c17d435a8e0e5690d75817f7b20e9b8f87934cf8dee6501a6677"
}
```

The source-built control receipt is
`C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/rocr-engine-source-stock-admission.json`,
SHA-256 `be8db6e364ab8df1c8bc5a0630b1eea1700936607f58c06564ef7834823965b3`.
Copy the original profile for that control too; do not combine HSA replacement
with lookup, matmul, kernel, prefill, or admission tuning.

## Managed maintenance and restoration

The current controller and backend are already managed by retained jobs and
exact run/CID ownership. A quiet singleton maintenance restart is supported by
the existing normal stop/start path. It does not require launching a second
large engine. Preserve the original profile bytes, controller identity/run,
backend run/attempt/CID, and gateway completed/cancelled counters first. ROOT
must make the final live idle/identity/reserve check and serialize this work
with other use of the local endpoint.

Request the managed controller stop using the existing command:

```powershell
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' -B `
  'C:/Projects/strix-alloy-clean/server/controller.py' stop
```

`control('stop')` writes only the exact current run ID. The live controller
owns gateway drain and backend stop; the backend validates and stops its own
CID and proves terminal cleanup and memory recovery. Wait for the exact
controller to reach STOPPED, its retained job to exit, the backend attempt to
report cleanup and recovery, runner/controller locks to clear, and inference
ports to close. Preserve uncertainty and locks; do not delete an ownership
lock, stop an unrelated process, or start another engine to work around it.

Then start the reviewed copied profile using the same controller:

```powershell
& 'C:/Users/Marcel/AppData/Local/Programs/Python/Python312/python.exe' -u -B `
  'C:/Projects/strix-alloy-clean/server/controller.py' run `
  --config 'C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/rocr-engine-candidate-stock8k.json' `
  --port 8840
```

The copied profile filename above is the intended runtime profile; ROOT
creates and freezes its bytes before launch. Preserve the generated backend
manifest, actual image and exact read-only mounts, qualified runtime identity,
guard minima, readiness, and owned run/CID for every engine window. Confirm the
actual engine's mapped HSA bytes match its manifest before drawing a runtime
conclusion.

After each private window use the same managed stop/cleanup/recovery sequence.
Use source_stock versus candidate to isolate patch effect, and installed stock
versus candidate to measure the whole rebuild. End by restarting the untouched
original profile with the command above and `--config` pointing to
`pld-stock8k.json`. Verify original profile SHA, stock runtime/no private mount,
ready/idle, exact singleton ownership, context262144/cacheOff/MTP2/PLD3,3,
cancelled counter continuity, and reserves. Leave that restored instance open.
Restoration remains required after measurement failure.

### Active-request limitation of the preserved controller

The preserved controller's gateway cleanup waits 30 seconds. It does not have
an atomic idle-only maintenance latch. A request admitted after an idle health
read and before its one-second stop poll may be drained for up to 30 seconds,
then cancelled. Reading repeated idle health/counters reduces uncertainty but
does not mathematically exclude that race. An edit on disk cannot add a latch
to the already running Python process. ROOT must use an actual quiet
maintenance window or defer maintenance while a request is active; verify
cancelled0 afterward. Do not describe a live source edit as protecting the
already running gateway.

## Frozen regular Stock8K cohort

Reuse the already frozen ordinary greedy cohort, not startup arithmetic,
serial draft, a legacy 4K qualification, or the component probe:

- Prompt SHA `0fb44189491024eb0c3f1715828303dd6ba6073641d08ce7a8261f9a3a22c3a1`,
  8192 input tokens from the retained prose prompt.
- `model=halogen-v2`, temperature0, seed1, streamfalse, cache_promptfalse,
  enable_thinkingfalse, reasoning_effortnone, chat template thinkingfalse,
  max_tokens128, draftermtp.
- One warmup and three measured requests per window; 128 output tokens,
  unchanged full-vocabulary MTP2 and PLD3,3, no NPU.
- Preserve full response/output hashes, prompt/decode timings, native response
  acceptance numerator/denominator and supplemental matching backend log bounds, actual input/output
  counts, owned engine identity, and reserve minima.
- Report actual measured prompt tok/s, decode tok/s, and aggregate acceptance;
  state any output-parity failure or contaminated window. No retries inside a
  failed window, no speed claim from the component medians, and no adoption
  from idle CPU alone.

The successful component candidate used about 0.011-0.012 idle CPU cores
versus about 1.9-2.0 in the controls. Its original RMS medians were about
11.7-11.9% slower than installed stock, while its source-control ratios were
0.9692 for A and 1.0104 for B. Its single Python-observed async wake was
1363.733 microseconds versus 174.178 source-stock and 185.887 installed stock.
These tradeoffs motivate the regular engine cohort; they do not predict its
token rate or acceptance.
