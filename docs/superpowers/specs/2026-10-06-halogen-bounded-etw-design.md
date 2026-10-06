# Bounded GPU-copy capture for the Halogen optimization

The full objective remains higher measured Halogen Prefill, Decode and useful
draft acceptance. This tool addresses one specific unresolved comparison: the
checked-copy candidate's partial +1.19% Prefill / +2.17% Decode observations were
not qualified because System GPU-copy activity had no proven owner and the final
stock window was missing. Instrumentation alone is not an acceleration result.

The user authorized autonomous implementation and measurements, including normal
server restarts. The existing HistoricalStock server must remain ready and open.
This design makes no serving change and starts no second engine. The actual token
has enabled Performance Log Users membership; ordinary ETW session access is
eligible, but the installed DxgKrnl provider's enable ACL remains unknown.

Use two small Windows-native programs, built with the already installed x64 MSVC
and Windows SDK. A recorder uses ordinary documented ETW session APIs. A separate
offline decoder streams the recorder's own ETL through ProcessTrace and TDH.
Preserve exact event descriptors, timestamps, schema types and raw property
bytes. Implement no automatic ownership resolver: current evidence does not
establish allocation namespaces, all DMA bridges or Linux task identity.

Recorder inputs are an absolute new ETL path, a duration of 1..30 seconds and a
validated keyword mask (default 0x845). Use the fixed descriptive session name
StrixAlloy-GpuCopy. Refuse an existing session or output; never adopt, reconfigure
or stop another session. Stop only the successfully returned owned trace handle.
Use QPC timestamps, sequential file mode, 64 KiB buffers with minimum/maximum64,
NO_PER_PROCESSOR_BUFFERING and a64-MiB disk cap. OS-adjusted pool above4 MiB,
event/buffer loss, file-full, interrupted duration or failed cleanup invalidates
coverage. CAPTURE_STATE requests do not prove rundown completeness. This small
pool is not yet proven loss-free at high event volume; do not silently expand it.

Require22 GiB free physical and commit at capture start; retain18 GiB throughout.
Monitor native recorder private commit against16 MiB and Windows reserves at
intervals no longer than250 ms. The decoder's private-commit ceiling is32 MiB;
bound TDH metadata to256 KiB, a property to64 KiB and output to64 MiB. Decode one
event at a time without loading or mapping the ETL. Guard total memory separately;
these component budgets do not guarantee Windows file-cache usage.

Unknown schemas, unsupported structures, missing relationships and TDH errors
stay explicit and unresolved. Header host PID, matching time, equal-looking
field names and provider state requests cannot establish exclusive Halogen
origin. Relevant adapter/object lifetimes, allocation provenance, guest process
fields and retained Linux task/container identity would all be needed later.

Root exclusively coordinates execution. Compile and review first. Then one
short, bounded capture may establish whether the provider can be enabled and
materialized under the actual token. No privilege change, UAC, driver/firmware
install, rejected native audit retry or unchanged engine cohort is permitted.
If access or provenance fails, retain the evidence and do not repeat unchanged
captures or call this a speed gain. A new serving comparison requires a concrete
changed supported attribution path and the original frozen workload/bookends.

Sources: [installed-schema contract](../../research/halogen-copy-attribution-contract-20261006-evening.md),
[access feasibility](../../research/halogen-etw-access-feasibility-20261006.md).
