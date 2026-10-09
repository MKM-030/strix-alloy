# Frozen real-request selector preparation

This directory contains 16 newly authored realistic tasks, frozen before
collection: 10 train requests and six held-out requests. Each has a unique source
document; no whole document, request, or derived round may cross the split.
These are natural task inputs with code and quantitative reasoning, not a
harvested human corpus or a representative benchmark. They have 409–500
whitespace-delimited words. Actual token counts are unmeasured and must come from
the returned API usage. No request was sent by this preparation.

`manifest.json` hashes the exact UTF-8 document and payload files. All payloads
select `halogen-v2`, temperature 0, seed 1, Thinking Off, Cache Off, `drafter=mtp`,
and `max_tokens=128`. MTP depth 2 and PLD `3,3` are engine/profile controls rather
than invented request-body fields. A 128-token limit does not guarantee 128
output tokens: early EOS remains an observed result. Inputs are intended to be
roughly 512–2048 actual tokens, without padding or repeated calibration units.
Root records actual usage rather than claiming a tokenizer estimate is actual.

The prepared manifest SHA-256 is
`76de0b548bfb48f028e50bf8517e8f9514d2cbbc03eb48668d445b834b59960c`.
The generator checks existing frozen files for byte equality and will not
silently replace a different input. The collection manifest is a separate file;
populate its null observed bindings and retain this prepared manifest unchanged.

## Identity facts from retained 0.17.3 source

The staged upstream source is
`../updates-20261009-0202/runtime-data/halogen/tools/serve_api.py.data`,
SHA-256 `1c74729e3484e0e4eee9f6a9f3f9447f71b0d8d32fa5af2dd4e3726f216212e9`.

* `Engine.__init__` starts `self.req` at zero. `Engine.generate` increments it,
  constructs `GEN <req> ... <prompt token IDs>`, and accepts only `T` and `D`
  replies carrying that integer. See lines 675 and 1063–1154.
* The admitted HTTP response ID is generated independently with `uuid4` at
  lines 3648–3650. It is not the native ID, a hash of it, or a join key for it.
* Optional `request_records.py.data` receives that HTTP ID through
  `Rec.admitted(cid, ...)` and serializes it. It records text units and API timing
  data, but it does not preserve `GEN req`. Enabling it alone cannot establish
  this provenance and is unnecessary for the bounded collection.
* Gateway `RequestTrace.request_id` is another independent UUID. The gateway
  creates its upstream headers and does not forward a client request-ID header
  as a native command identity. It rewrites only the selected model identifier
  in the forwarded JSON. A caller-chosen header cannot manufacture a native ID.
* The existing native Birth callback copies the full Record+0 64-bit bit pattern
  into `wire_request_id`. Pointer ownership is separate: `owner_birth`, slot
  cookie, epoch, and begin/outcome sequences remain part of the join. Native log
  lines contain `flash_serve: req <integer>`. In the retained validation log IDs
  1 and 2 belong to startup serial smoke requests; the MTP capture has ID 3.
  Do not hard-code 3 for another session or infer IDs from HTTP UUIDs.
* Startup smoke calls are made directly against the backend before gateway
  ready. They increment the frontend's counter but legitimately produce no
  owned MTP Birth. INFO/PING/health calls do not increment `Engine.req`.

The source hashes and bounded excerpts are retained in `source-evidence.json`.
The native identity statement also relies on the existing exact ELF admission
and the independently retained Record+0 formatter/source proofs, rather than
assuming a pointer address is a durable request identifier.

## Bounded collection using the existing log and journal

Root owns all runtime operations. Use its private authenticated gateway on
8842, private frontend/backend credential files, the ordinary lifecycle, one
frontend, one native engine, one slot, and the existing default-off capture
adapter. The normal 8840 gateway is down during collection. Preserve the normal
credential files. No other client may call either backend HTTP or the native
TCP engine. Gateway concurrency one alone cannot establish that isolation.

1. After startup probes finish, retain the root-owned launch/profile/manifest,
   frontend and native process identities, loaded-asset receipt, startup status,
   and session nonce. Snapshot an idle health response. Record the retained
   engine-log byte position and journal byte position at a complete frame.
2. Send one exact frozen payload. Retain the response, HTTP status, start/end
   times, actual prompt/completion usage, reasoning/cache counters, exact content
   hash, and full-request accepted/drafted counters. No automatic retry.
3. Wait until the journal shows the request's Retire and is frame-aligned before
   the next request. Its asynchronous writer drains every 20 ms, so API return
   alone is not a journal flush barrier. A stable file size alone also cannot
   substitute for observing Retire. Record the next byte positions and idle
   health: completed must increase by exactly one and cancelled must not change.
4. Bind the unique native log request ID in that interval to the unique journal
   Birth/Retire owner in that interval. Store full integer `wire_request_id`,
   `owner_birth`, birth/retire sequences, nonce, and unchanged process/launch IDs.
   The native log's reported token count is not the API output count: the
   retained MTP log reports an initial generated chunk of two while the API
   completes 128. Use the log for its ID, not as the final token denominator.
5. Repeat sequentially in the frozen order, then obtain the existing
   nonce-bound qualified close receipt while idle. Copy journal and receipts
   before normal stop/container cleanup. Decode and verify the complete journal,
   then restore the user's normal server through root's lifecycle.

The planned capture budget is 16 calls, at most 2048 generated tokens, 90 seconds
per call, and 30 minutes total including bounded evidence handling. The root
collector may use a shorter budget when it has concrete measurements. Stop a
failed or ambiguous collection instead of guessing an ordinal mapping. Retain
failed evidence and actual handles. No extra model download, calibration corpus,
or second training collection is implied.

Normal/capture parity uses the same frozen payloads and engine settings. Retain
one normal result per request if this comparison is run, and compare exact
UTF-8 output-content hash plus full-request accepted/drafted counters. This is
up to 16 additional calls and 2048 additional output tokens, separate from the
capture budget. Existing observer validation for one synthetic request does not
claim parity for this whole cohort. Missing normal results remain explicitly
unobserved; they cannot become a passed parity flag.

## Loaded assets and token evidence

The v2 complete-file receipt is
`backends/halogen-wsl2-0.17.3/.local/v2-integrity.json` under the repository root.
Its size is 66,687,678,432 bytes and SHA-256 is
`71246c6ab3fc1de2cf06326f18e275fe9c2a18366d646ed3357d194c884fc687`.
The N-gram receipt at the corresponding `ngram-integrity.json` pins
124,068,083,904 bytes and
`9c116bbc01f77b7a15464c1a124eb3325b286089b8a2a6f2856c9b246a235bd6`.
Root must match fresh source-file identities to those receipts, exact container
mounts/environment, owned process and loaded-path evidence; an old receipt alone
does not establish which asset the new process loaded.

The actual frontend uses `HALOGEN_TOKENIZER=/models/tokenizer` and
`AutoTokenizer.from_pretrained(args.tokenizer)`. Its mounted host directory is
`/home/revn/halogen-models-native/tokenizer`. A complete checkpoint hash must not
be relabeled as a standalone tokenizer SHA. The Windows directory
`C:/AI/models/halogen-flashnext/tokenizer` is a historical candidate, not proved
equal to that loaded native directory. It contains `tokenizer.json`,
`tokenizer_config.json`, `chat_template.jinja`, `generation_config.json`,
`merges.txt`, and `vocab.json`. Root hashes the actual loaded directory and
retains before/after identities for its complete file set. The optional
`candidate-tokenizer-assets.json` receipt names the Windows candidate honestly;
it is not a loaded-asset certificate.

Pin the frontend tokenizer file set, chat template, config/added tokens, loader
source and versions together. A hash of tokenizer.json alone cannot prove the
template or loader options. If checkpoint-native vocabulary assets matter to a
later model, retain their enclosing checkpoint pin and explicitly named member
evidence; do not invent a member SHA that was never computed.

The API supplies text and usage, not a complete output-token tape. Owned native
Begin events copy a bounded host history suffix (up to 64 IDs), current/opening
IDs, PLD offers, and causal bounds. Those copied IDs are sufficient inputs for
the proposed bounded token-history selector. Never retokenize the generated
text and call that the native output tape. A replay of the exact loaded
frontend tokenizer/template can be retained as an additional prompt-tokenization
receipt, including its actual options and first copied-suffix match, but it does
not replace the native ownership join.

Neural `stock_width=-1` in wire v1 is an intentional unknown. A policy may use a
separate causal fixed-stock width 2 only when the loaded profile is depth 2 with
adaptive disabled and the exact Begin has depth_low=2, adaptive=0,
and native_allowance>=2. Depth_high is retained as evidence; with adaptive
disabled it need not equal two. Preserve the raw field. Do not infer this width from the
outcome attempted count. PLD remains a separate source. Terminal/censored rows
are excluded by the reader, not relabeled as negative outcomes.

## Collection contract and offline review

`provenance-receipt-template.json` defines
`halogen0173.selector-request-provenance.v1`.
`loaded-assets-receipt-template.json` defines
`halogen0173.selector-loaded-assets.v1`. Null fields and template status are
deliberate: preparation has no observed runtime qualification. Each file
reference is `{path, sha256}` with optional bytes. Resolve a relative path from
the JSON file containing that reference. Collected manifest entries must supply
the same request/document/split and observed nonce/wire/owner as their receipt.
The decoded file may contain the whole journal; each request is selected by all
three identity fields, not by a caller-supplied decoder document field.

Use `check_cohort.py <collected-manifest.json> --output <new-review.json>` for
read-only hash/owner review. It imports only the existing offline ledger and
uses no API, process control, model load, or accelerator. It validates retained
native events rather than accepting arbitrary qualified booleans. Root's
exclusive-client and actual loaded-file snapshots remain the trust boundary;
this offline checker cannot attest live GPU weight bytes. It reports counts,
actual usage and missing parity instead of imposing an arbitrary request-count
or class-balance rule.

Cost sidecars are optional evidence references and must share the native nonce
and qualified closure. Wire v1 itself has no clocks. Observed begin-to-outcome
intervals include observer overhead and are neither unchosen-width costs nor
end-to-end throughput. This cohort can fit/evaluate a small exploratory policy;
placement or speed still requires the root's actual CPU/GPU/NPU comparison.
