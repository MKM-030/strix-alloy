# Passive 0.18.1 aggregate phase observer, source delivery

Default OFF, measurement only. Exact engine SHA:
`d946e7b32a46400884ee7309b909da73f4a6586140cd9f9b94fa9ff583b3c3ab`.
Source maps were independently decoded from actual 0.18.1 bytes. This package
changes no native time fields, counters, durations, divisors, arithmetic or kernels.
All real chrono returns, including valid ends and diagnostics failures, remain
unchanged. No observer build, live binding or phase qualification is claimed.

- `static-map.json`, `evidence/`, `phase_clock_pins.h`: 8 complete FDE functions,
  26 instruction-boundary windows, phase transfer/move/formatter closure and
  the exact image's root-produced CPU chrono-provider receipt.
- `phase_clock.c`, `observer_core.h`, `phase_clock_entry.S`, `phase_clock.map`:
  single versioned chrono interposer source. Four endpoint return RVAs only;
  dual RAW brackets, move-safe native-start pairing, retained request epochs,
  same-ID reuse/collision rejection and bounded 256-request ownership ledger.
  Default-off/unrelated calls simply forward. Enabled constructor pin failures
  are terminal; runtime capture I/O failure disables observation and preserves
  native returns, leaving evidence unqualified.
- `observe_api_done.py`: explicit default-off companion wrapping the actual,
  hash-bound stock D parser once and journaling after its return. Root must bind
  the exact API callable in a measurement-only wrapper. It returns the same
  stock result object, including after diagnostic failure.
- `compose_environment.py`: pure opt-in environment composition; it neither
  launches nor inspects a process. Residency probes omit this observer entirely.
- `verify_phase_journal.py`: file-only identity/native-field/D/RAW-bracket reader.
  It requires the expected API source pin, copied D closure and successful close;
  its optional actual capture receipt hashes saved request/reply bytes and binds
  signed ID/epoch/counts to complete-response QPC and final journals. It reports
  observed durations and partial internal overhead and emits no tok/s.
- `test_phase_tools.py`: meaningful offline fixtures. `core_host_test.c` tests
  the actual C producer with mock syscalls/counter values; root owns its build/run.
- `OVERHEAD-PROTOCOL.md`: mandatory source, clock and measured A/B/A overhead
  evidence before any later instrumented rate claim. No clean serving gain.
- `CPU-BUILD.md`: exact root-only Ubuntu-24.04/revn GCC13.3.0 CPU compile,
  mock harness, ELF inspection and output receipt command; not executed here.

Runtime opt-in variables are `HGN0181_OBSERVER_ENABLE=1`,
`HGN0181_OBSERVER_JOURNAL=/fresh/file.jsonl`, `HGN0181_OBSERVER_NONCE=32hex`,
and optional `HGN0181_OBSERVER_ARM_FILE=/fresh/owned.arm`. Both journals must be
new, distinct files. The API companion takes matching explicit nonce/API hash
and its own fresh journal. Nothing here changes the installed serving configuration.

Offline checks:

```powershell
& 'C:\Projects\strix-alloy-clean\server\.local\venv\Scripts\python.exe' -B 'C:\Projects\strix-alloy-clean\scripts\benchmarks\experimental\halogen0181_phase_clocks\test_phase_tools.py'
```

`map_source.py` is a source generator that runs only pinned Windows objdump and
reads saved ELF/provider receipts; it does not build or load Linux code. Preserve
the delivered map/evidence; do not rerun it over live or updated input bytes.
Root can use `source-pins.json` to freeze this delivery before CPU build.

For a future actual capture, pass `--journal`, `--native-d`, `--api-source` and
optionally `--capture-receipt` to the file-only verifier. Without the trusted
actual request receipt, matching journals establish consistency only. Even a
coupled receipt leaves RAW/QPC calibration, measured overhead and token rates
unqualified. Decode begin/end native counts are observed, but first-token phase
count scope requires minimal runtime proof; the reader never assumes128/t.
