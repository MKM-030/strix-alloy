# Optional owned round-cost sidecar

This private source copy adds bounded copied timing metadata to the tested,
default-off 0.17.3 observation adapter. `shadow_wire.h`, `ledger.py`, relay
assembly/header/linker sources, and all nine native pins are preserved. The
library does not alter native choices, widths, counters, tokens or accelerator
placement. It adds no hook site. No engine, API, GPU, NPU, build or test was run
by the source author; the root task owns qualification and capture execution.

The old two-argument `Collector::configure` call remains untimed. Disabled
callbacks return before native dereferences and never sample the clock. Timing
requires both the original `HALOGEN0173_SHADOW=owned-ledger-v1` activation and:

```text
HALOGEN0173_SHADOW_COSTS=monotonic-raw-v1
HALOGEN0173_SHADOW_COST_JOURNAL=/tmp/owned-shadow-capture.h0173sc
```

Use the same newly built library and existing owned launch/lifecycle. The cost
path must be an absolute, distinct, nonexistent regular-file destination. Open
uses `O_EXCL|O_NOFOLLOW`, permissions 0600. Both journal headers carry the same
runtime pin and nonce. The original journal remains 128-byte Header plus
512-byte Event v1; the sidecar is 128-byte CostHeader plus 96-byte CostEvent.
Its schema is in `shadow_cost_wire.h`. Each record includes exactly copied
birth/cookie/epoch/round/wire ID, native event sequence, source/flags, cumulative
native drop count, raw timestamp and explicit clock status. No native pointers,
borrowed frames, or native objects leave the callback.

The collector samples Linux `CLOCK_MONOTONIC_RAW` after owned Request/slot
admission and before the Begin or Outcome snapshot. The observed interval
includes the rest of the Begin callback, relay return/replay, the native stock
path, and the Outcome relay/admission work before its sample. It excludes work
before the Begin sample and after the Outcome sample. This scope includes
observer overhead, scheduling and any waits in that native interval. It does
not isolate draft generation, verification, selection inference, or device
execution. PLD opening rejection closes its existing censored candidate and
begins neural at the same sampled observation. Both remain separate rounds.

No absolute native phase comparison or MONOTONIC-to-RAW conversion is made.
RAW nanoseconds are local observed durations, not end-to-end token rates or
counterfactual savings for an unchosen width. Host QPC request wall time remains
the separate authority for future delivered-throughput comparisons. Acceptance
rows still label only prefixes that stock actually attempted.

Cost records share the event ring's slots and critical section; they cannot
overflow or drain independently. Native relay/producer losses remain visible
in v1 and the whole joined collection becomes incomplete. Clock read failure,
invalid timespec/overflow, and per-round reversal remain explicit status flags.
Timestamp failures do not change native loss counters or decisions. Missing
sidecar records produce unavailable costs. Sidecar write/fsync/close failure
stops observation and makes cost closure unqualified. Native journal closure
qualification stays separate from cost qualification in the same close receipt.

Close as before: with the API idle, write the exact startup nonce plus newline
to `JOURNAL.close-request`. Wait for `JOURNAL.close.json`; retain both journals,
startup status, and close receipt before stopping through the normal lifecycle.
Require matching nonces, original qualified close, `cost_capture_enabled`,
`cost_closed`, and `cost_qualified_close`; cost failures must be zero. There is
one writer and one nonce-bound close request, not a second runtime controller.

## Root CPU qualification recipe

Run from this directory inside the already available Linux CPU build context.
No installer is linked into either collector harness. The production library
links the real clock; GNU clock wrapping is confined to the timing fixture.

```sh
c++ -std=c++20 -O2 -g -Wall -Wextra -Werror -fPIC -fcf-protection=branch -fstack-clash-protection -pthread -c shadow_collector.cpp -o shadow_collector.o
c++ -std=c++20 -O2 -g -Wall -Wextra -Werror -fPIC -fcf-protection=branch -fstack-clash-protection -pthread -c shadow_cost_clock.cpp -o shadow_cost_clock.o
c++ -std=c++20 -O2 -g -Wall -Wextra -Werror -fcf-protection=branch -fstack-clash-protection -pthread shadow_collector_cpu_harness.cpp shadow_collector.o shadow_cost_clock.o -o shadow-collector-cpu-harness
./shadow-collector-cpu-harness collector-fixture.h0173sl
c++ -std=c++20 -O2 -g -Wall -Wextra -Werror -fcf-protection=branch -fstack-clash-protection -pthread shadow_cost_cpu_harness.cpp shadow_collector.o shadow_cost_clock.o -Wl,--wrap=hgn_shadow_cost_stamp -o shadow-cost-cpu-harness
./shadow-cost-cpu-harness timed-fixture.h0173sl timed-fixture.h0173sc
python3 -B -m unittest test_ledger.py test_cost_ledger.py
python3 -B cost_ledger.py timed-fixture.h0173sl timed-fixture.h0173sc --output timed-fixture-decoded.json
```

The last command deliberately does not assert runtime closure: the fixture has
no installer/writer. Verify its single row has `cost_status=observed`, integer
`observed_begin_to_outcome_ns`, `round_costs_complete=true`, actual attempted=2
and accepted_prefix=1, with `cost_close_verified=false`.

The timing fixture samples the real RAW clock through the production function,
checks errno/native-memory transparency, and exports real copied collector
events for offline joining. Its link-local wrapped cases exercise clock read
failure, invalid sample, reversed order, partial native output, retirement with
a pending round, ring overflow/loss, disabled bogus-pointer safety, and timing
off with zero clock calls. Offline tests cover exact causal joins, missing
stamps, native censor/loss, nonce/identity mismatch, and corrupt sidecar tails.

Retain existing copied-relay CPU qualification using unchanged relay sources.
Build the production objects with the same flags as above:

```sh
c++ -std=c++20 -O2 -g -Wall -Wextra -Werror -fPIC -fcf-protection=branch -fstack-clash-protection -pthread -c shadow_install.cpp -o shadow_install.o
c++ -g -fPIC -fcf-protection=branch -c shadow_relay.S -o shadow_relay.o
c++ -shared -pthread -Wl,-T,shadow_relay.ld shadow_collector.o shadow_cost_clock.o shadow_install.o shadow_relay.o -lcrypto -ldl -o libhalogen0173_owned_shadow.so
```

Use exactly `shadow_relay.o`; the linker script pins this basename. Preserve the
retained relay harness instructions and compare the linked island byte for byte
with the validated copy. The only added production object is the raw clock.

## Root native read recipe

```sh
python3 -B cost_ledger.py JOURNAL COST_JOURNAL --close-receipt JOURNAL.close.json --output timed-native-rows.json --require-complete
```

The reader returns unchanged acceptance rows plus
`observed_begin_to_outcome_ns`, `cost_status`, `cost_clock`, and `cost_scope`.
It also preserves `causal_depth_low` and `causal_depth_high` from the exact joined
Begin event for offline fixed-profile checks. Raw neural `stock_width=-1` stays
unchanged; the reader never substitutes outcome attempts as predecision width.
Exact join keys are session_nonce/owner_birth/slot_cookie/slot_epoch/round and
begin_seq/outcome_seq. `transported_delta` keeps its original transport scope;
it is not renamed as wall-time committed tokens. Censored terminal/partial
native pairs never become complete training rows even if their clocks worked.
External asset/document metadata still requires the root's owned provenance
receipt; global command-line metadata does not prove loaded assets. Join the
16 sequential requests by their owned nonce/wire/birth provenance, retaining
all actual rounds and censor counts without selecting on acceptance results.
