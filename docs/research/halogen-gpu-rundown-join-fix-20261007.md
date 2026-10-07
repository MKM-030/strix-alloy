# GPU rundown parent joins

The attribution parser now treats `DC_Start` as an observation of an existing
object. Windows can enumerate a context before its device, or a guest process
before its VM. Requiring the parent to have been observed at the child's original
observation incorrectly rejected later work even when its full chain was known.

The correction permits a unique later **rundown** parent only for work strictly
after every required observation. It preserves original timestamps and rejects
teardown barriers, reused handles and ambiguous generations. True creation
events still require a parent at creation. Packet completion must remain inside
the same context/device/guest/VM lifetimes. Allocation-origin joins use the same
rule. No System/PID4 or `DxgProcess=0` ownership exemption was added.

Root reproduced the positive regression before implementation. All 41 focused
parser tests passed after the correction, including the five new regressions for
reversed observations, same-tick refusal, true creation, unmatched teardown and
VM reuse. An independent source review passed.

A CPU-only replay of the retained 49,118-event trace completed with zero reported
loss. All 180 Copy spans remain unresolved and none is attested to the serving
process. The correction does not invent a guest owner for missing metadata;
the prior trace also lacks a verified serving post-exec identity. No new engine
request, GPU trace or NPU operation was performed for this replay.

Raw evidence is retained under
`server/.local/optimization9h-20261004/serving-identity-capture-ecf5bd3a65054eb6bb89c959ff3ed3f2/serving-copy-attribution-rundown-final-20261007.json`.
Its input seals include the final parser, decoder output, recorder receipt,
installed SDK header, native node metadata and namespace bindings.

This is a correctness repair for future attribution of later work. It provides
no measured Prefill, Decode or MTP-acceptance improvement.
