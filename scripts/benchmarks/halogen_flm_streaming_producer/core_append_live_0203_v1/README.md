# Halogen 0.20.3 NPU integration: source delta

This archive is **off by default**. It is a source delta, not an installer or a
standalone server. Files unchanged from the existing 0.20.2 archive are listed
by exact path and SHA256 in `source-manifest.json`, rather than copied again.
The five unchanged native-model wrappers retain their earlier explicit source
references. Follow each `materialize_as` entry to reconstruct the private source
layout; the archived helpers still require new local paths and Root-owned seals.

The actual 0.20.3 Flash executable, API and four inspected CPU providers are
byte-identical to 0.20.2. This is a fresh version binding, not a new Flash kernel
or a demonstrated speed improvement. Exact ELF pin bytes, complete relevant
FDEs/CFI and clock-provider code were rechecked against the extracted files.
Historical inspector captures are explicitly reused through whole-file identity.

Both experimental Linux DSOs were built afresh. All 21 Root-owned CPU build and
fixture commands exited successfully. The consumer retains `cold_addresses.h`,
which derives the patch, fallback and consume addresses from the same validated
pin rows. Its callback keeps `-mgeneral-regs-only`, `-fno-builtin`,
`-fno-stack-protector` and `-fno-tree-loop-distribute-patterns`. The complete
3,035-byte callback has no SIMD/x87/MMX/opmask dependencies, undefined symbols
or indirect calls. The RAW observer's ordinary chrono ABI and external loader/
`memset` calls remain separately documented; no transitive SIMD claim is made.

The actual live attempt is terminal: **one excluded stock warmup, zero measured
requests and no NPU producer start**. The unchanged 22 GiB request-entry reserve
was not reached after warmup. It provides no qualified NPU prefill/decode rate,
NPU acceptance or speed difference. The normal server was restored with NPU
integration disabled. See the [terminal report](../../../../docs/benchmarks/halogen0203-real-npu-core-append-20261111.md).

The intended comparison remains stock / real NPU v4 / stock, each with one
excluded warmup and three measured requests: natural 8,192 input tokens,
128 output tokens, temperature 0/seed 1, Cache/Thinking/Vision Off, 32K capacity
and both prefill settings 8192. Native-T parity, RAW/HTTP-QPC accounting and
native head/lookup/grammar counters remain distinct from HDO2 hits/proposals.
Specific HDO2 acceptance is undefined. Component milliseconds are not converted
into measured engine token rates. Startup 30/131 GiB, request entry 22/22 GiB
and continuous runtime 18/18 GiB reserves are retained.

Only source and source-proof metadata are included. There are no binaries,
models, SDK/provider payloads, credentials, runtime profiles, executed bindings,
live process handles or logs. Source/proof path references describe historical
local preparation; they do not redistribute those files. Nothing here enables
the integration. The local verifier performs file/hash checks only and runs no
compiler, engine, hardware or HTTP request.
