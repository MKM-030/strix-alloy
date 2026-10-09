# Halogen 0.17.3 same-width PLD tail source archive

This is a **default-off source archive** of the implemented PLD tail consumer
contract and a **future-label oracle** used to prepare a consumer experiment.
The oracle is not an NPU producer. This archive contains no model weights,
native libraries, captured token journals, oracle tables or runtime results.
It carries no serving-gain claim or live native-state qualification.

## Implemented components

- `tail_adapter.h`: a generic, allocation-free ready-tail consumer. It preserves
  proposal zero and width, validates the full copied frontier binding, and
  writes only existing tail entries after every guard succeeds.
- `oracle_format.h`: the packed, versioned oracle header and 300-byte records.
- `readylist_oracle.h`: a bounded CPU ready-list provider, loaded only at cold
  startup. Its stock mode returns the original offer; its oracle mode consumes
  labels reconstructed from later committed output.
- `generate_readylist_oracle.py`: an offline label reconstruction tool. It
  requires a complete retained raw-ID dataset and externally verified model
  and exact tokenizer-file SHA256 pins. It never imports or executes a model.
- `prepare_native_sources.py`: a source-only integration preparer for seven
  exact, pinned owned-hook base files. It requires explicit input and fresh
  output directories, copies the three adapter headers, and reproduces the
  prepared collector/installer/relay sources. Importing it has no side effects.
- `tail_adapter_cpu_test.cpp` and `test_oracle_generation.py`: the existing
  CPU-only decision and oracle reconstruction tests.

The core headers, oracle generator and existing tests are byte-for-byte copies
of the sealed private preparation. The source preparer was adapted only to
accept explicit directories, validate all inputs before writing, copy its
header dependencies and run behind a main guard. `source-manifest.json` records
the archive hashes and the original source pins.

## Consumer contract

An `Adapter` starts disabled. Its configuration is cold-start-only and requires
exact native pins, nonzero session/model/tokenizer pins, a frozen ordinary-ID
bitmap and a ready-result provider before enablement. Disabled operation does
not dereference the offer, bitmap or provider.

`Snapshot` contains copied values. `Candidate.binding` must equal the complete
snapshot key: session and model/tokenizer pins, owner birth, slot cookie/epoch,
round, wire request, current token, model position, transported count, complete
retained suffix and its total length, stock offer, allowance and width. Stale,
unavailable, invalid, lost-owner or changed-input results keep all stock IDs.
Only existing entries `1..width-1` may change; opening, native count, registers,
request and model remain unchanged.

The provider must return an already-ready result immediately. It must not
dispatch an NPU operation, call native model code, allocate or wait in this
callback. A future real producer must separately establish state ownership,
token conversion, rollback, transport and scheduling. No such producer is
implemented here.

The owned collector must retain normal serialized same-owner native control,
recheck owner/slot/loss and borrowed input after the provider returns, and drain
all in-flight relays before releasing provider storage. Its observation lock
alone is not a mutex for concurrent native model mutations.

## Native source preparation

The native integration is pinned to engine SHA256
`af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`.
Its copied PLD offer seam is `0x17413ff`; the proposal buffer is original
RSP+`0x6a0`, count is RBX, request is original RSP+`0x10`, and replay bytes are
`48 8b 44 24 10`. Retired 0.17.2 seam addresses do not apply.

The original owned-hook base sources are an explicit external input, checked
against `PINS` in the preparer. The archive does not silently select a local
private directory or install a hook:

```text
python prepare_native_sources.py --source-dir <pinned-owned-hook-source-dir> --output-dir <fresh-source-dir>
```

Preparation writes source files and a hash receipt only. Compiling a separate
Linux DSO, cold-start installation and live output/state-parity qualification
are separate work. The native opening gate and normal linear verifier,
accepted-prefix comparison, correction/bonus commit, output/history and
stop/EOS processing must remain intact. The prepared path admits only complete,
unconstrained greedy stock PLD hits of width two or three within allowance; it
does not create an offer on a miss or extend a stock offer.

## Explicit oracle modes

Keep `HALOGEN0173_PLD_TAIL` unset for the inherited observation path. With
`HALOGEN0173_SHADOW` unset too, the installer publishes no hook. Oracle file
reads and configuration occur only at cold startup.

An explicitly controlled consumer experiment may use one of:

```text
HALOGEN0173_PLD_TAIL=readylist-stock-v1
# or readylist-oracle-v1: future-label intervention, not NPU drafting
HALOGEN0173_PLD_TAIL_LIST=/absolute/read-only/oracle-readylist.bin
HALOGEN0173_PLD_TAIL_ID_MASK=/absolute/read-only/allowed_ids.bin
HALOGEN0173_PLD_TAIL_MODEL_SHA256=<externally-verified-model-SHA256>
HALOGEN0173_PLD_TAIL_TOKENIZER_SHA256=<exact-tokenizer.json-SHA256>
```

The source preparer preserves the original separate cold-start owned-hook
enablement and lifecycle. Tail mode alone is not a hook installer. The generator
requires these explicit offline inputs:

```text
python generate_readylist_oracle.py --decoded <complete-decoded-journal.json> --target-tokenizer-json <tokenizer.json> --model-sha256 <verified-SHA256> --tokenizer-sha256 <exact-file-SHA256>
```

The sealed generator writes `oracle-readylist.bin`, `allowed_ids.bin` and
`oracle-preparation.json` beside its script. Run a disposable copy when preparing
those data files; they are not part of this source archive.

Labels come only from later committed suffixes of the same retained owner and
slot generation, with prefix overlap, stock opening and ordinary target-ID
checks. Conflicting identical frontiers are removed. A changed trajectory may
leave the frozen table and immediately falls back to stock. Oracle availability
or acceptance never establishes real producer coverage, cost or speed.

## CPU validation

Run the three offline oracle reconstruction checks:

```text
python -B -m unittest test_oracle_generation.py
```

The freestanding C++ test exports `run_cpu_tests()` from a Windows test DLL.
Compile it with LLVM for `x86_64-pc-windows-msvc`, C++20, `-O2`,
`-ffreestanding -fno-builtin -fno-stack-protector -fno-exceptions -fno-rtti`, then
link with `lld-link /dll /noentry /nodefaultlib` to a disposable output directory.
Calling only that exported test must return zero. It tests disabled invalid-pointer
bypass, unavailable/stale binding, opening/width/ordinary-ID rejection, unchanged
offers, owner loss, changed input, constraint gating and width-two write bounds.
It has no device initialization or model dependency.

The original private preparation reported that CPU suite and the three Python
checks passing, with no Linux integration build, hook install, engine request or
GPU/NPU execution. Later runtime findings belong in separately bound receipts.
