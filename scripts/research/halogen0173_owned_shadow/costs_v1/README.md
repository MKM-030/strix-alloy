# Halogen 0.17.3 owned shadow capture

Experimental, default-off observation of native MTP rounds. This code does not
change draft width, token selection, target weights or GPU kernels. It does not
execute a policy model or use the NPU. It is not loaded by the normal launcher.

The installer admits only the exact 0.17.3 `flash_serve` ELF with SHA-256
`af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`, checks nine
native instruction spans, and installs in its cold constructor. There is no
running-process patcher. Its copied relays preserve the admitted architectural
state and carry registered unwind information. Missing stack state, contention,
overflow and incomplete ownership remain explicit losses, never guessed labels.

Activation requires this exact environment inside the owned engine launch:

```text
LD_PRELOAD=<existing adapters>:<built library>
HALOGEN0173_SHADOW=owned-ledger-v1
HALOGEN0173_SHADOW_JOURNAL=/tmp/owned-shadow-capture.h0173sl
HALOGEN0173_SHADOW_STATUS=/tmp/owned-shadow-status.json
```

Keep the normal engine lifecycle and resource guards. Compile C++ objects with
`-std=c++20 -O2 -g -Wall -Wextra -Werror -fPIC -fcf-protection=branch
-fstack-clash-protection -pthread`. Assemble `shadow_relay.S` into the exact
basename `shadow_relay.o`; link the collector, installer and that object with
`-shared -pthread -Wl,-T,shadow_relay.ld -lcrypto -ldl`. CPU harnesses are separate
executables; the relay harness does not link the installer or collector.

When the API is idle, write the startup status's exact 32-character session nonce
plus newline to `JOURNAL.close-request`. Wait for `JOURNAL.close.json`, require
qualified closure, and copy the journal and receipts **before** normal SIGTERM
or container cleanup. A normal stop need not invoke DSO destructors. The copied
Header, startup status and close receipt must have the same nonce.

Read the retained validation journal without loading an engine:

```powershell
python -B scripts/research/halogen0173_owned_shadow/ledger.py docs/research/halogen0173-owned-shadow-20261009/journal.h0173sl --output decoded.json --require-complete
```

Wire v1 copies a bounded host token suffix, PLD offers and native counters. It
joins begin/outcome records only under live request/slot/epoch ownership. Neural
and PLD counters stay separate. Terminal, constrained and partial rounds do not
become complete training labels. A label covers only a prefix actually attempted
by stock; it cannot describe an untried depth.

`--require-complete` validates journal structure. It does not certify loaded
model/tokenizer assets or bind requests to documents. Caller-supplied metadata
does not provide that proof. Wire v1 has no per-round timing labels.

See [the validation report](../../../docs/research/halogen0173-owned-shadow-validation-20261009.md)
for actual capture results and the remaining policy work. The report establishes
capture correctness, not a throughput improvement.
