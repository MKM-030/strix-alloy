# Bounded Halogen ETW Implementation Plan

> **For agentic workers:** Use independent implementers for the two native files;
> root integrates, reviews and exclusively executes capture/hardware work.

**Goal:** Enable a supported, bounded prospective GPU-copy evidence path for the
unqualified checked-copy candidate, without claiming instrumentation is speedup.

**Architecture:** An owned native recorder writes a small sequential ETL. An
offline TDH decoder preserves installed-schema properties incrementally. No
ownership resolver or serving modification is included.

**Tech Stack:** Existing x64 MSVC14.44, SDK10.0.26100, Windows ETW/TDH.

**Spec:** [design](../specs/2026-10-06-halogen-bounded-etw-design.md).

## Global Constraints

- Preserve the ready/open server and all foreign processes/sessions.
- One engine; no GPU/NPU benchmark, privilege change, install or audit retry.
- Capture admission22 GiB physical/commit; continuous reserve18 GiB.
- Requested ETW pool4 MiB, sequential ETL64 MiB, duration1..30 seconds.
- Recorder/decoder private-commit ceilings16/32 MiB; unknown evidence unresolved.

## Review Focus

- Existing output/session must not be overwritten, adopted or stopped.
- Enable denial after successful start must stop that exact owned session.
- OS-adjusted pools, trace losses and early termination invalidate coverage.
- TDH variable arrays/unknown structures must preserve raw evidence or errors.
- QPC, host PID and similarly named handles must not become ownership claims.

## Tasks

- [x] Implement `scripts/benchmarks/halogen_dxg_trace_record.c`: documented
  owned ETW lifecycle, JSON receipts, reserve/budget guards and a no-session plan
  mode. Source agent performs no capture.
- [x] Implement `scripts/benchmarks/halogen_dxg_trace_decode.c`: bounded offline
  EVENT_RECORD/TDH materialization, exact schema/raw bytes and loss/error summary.
- [x] Root builds both with installed MSVC/SDK, checks CLI plan behavior and
  independently reviews ownership/cleanup/bounds. Do not run broad test suites.
- [x] Root revalidates live native server handles, actual container, memory and
  foreign GPU load; performs at most one short owned capture if access remains
  eligible. Retain actual API errors/adjusted limits/loss counters and cleanup.
- [x] Decode only a completed own ETL. Inspect actual record coverage/remaining
  unresolved joins; decide whether any future engine comparison is justified.
- [x] Save sources and receipts, reseal continuation, leave server ready/open.
  No Prefill/Decode/acceptance claim follows without a qualified engine cohort.

**Actual result:** one idle five-second trace and offline decode completed with
zero reported recorder losses. All 8,454 Dxg events materialized; actual37/v2
fills the allocation-stop schema, while all nine attribution groups remain
unresolved. No engine comparison admitted. See
[result](../../research/halogen-etw-bounded-result-20261006.md) and
[coverage](../../research/halogen-etw-observed-coverage-20261006.md).
