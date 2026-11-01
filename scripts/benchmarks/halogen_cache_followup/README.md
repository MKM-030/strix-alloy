# Offline preparation for Halogen prefix-cache follow-ups

These standard-library Python modules contain no HTTP client, model runner,
service control or automatic measurement entry point. Python 3.10 or newer is
required. They prepare request bytes and account for supplied SSE recordings.
The tests use artificial fixtures; their times and token counts are not local
Halogen measurements.

```powershell
python -B -m unittest discover -s scripts/benchmarks/halogen_cache_followup -p "test_*.py"
```

The portable export passes **40 CPU tests**.

## Workload preparation

`workload_bundle.build(document)` creates four two-question pairs: one warmup
pair and three measured pairs for a future experiment. Each pair has its own
first system-message marker, followed by a stable document and a different last
question. Four separate A/B/A/B sentinel requests have explicit expected answers.
Markers are not engine cache namespaces; coldness, hits and isolation still
require observation.

`write_bundle(output, document, provenance)` freezes 12 request files and a
manifest in a new directory. It refuses an existing directory. Full input token
counts remain unknown, and `requests_sent` remains zero. The intended profile
comparison changes only Cache Off to Flexible; requests use default cache policy,
streamed usage, MTP, temperature 0 / seed 1, Thinking Off and max 128 output tokens.
Actual positive output counts may be shorter than 128.

## Stream accounting

`OfflineChatStream` consumes caller-supplied bytes and QPC receipt ticks through
`feed(data, received_qpc)`; `finish()` requires a complete chat stream. It checks
UTF-8/SSE framing, stable response identity, final-choice/usage/DONE sequencing,
Thinking Off, token counts and the explicit native speculation ledger. Native
head, lookup and grammar counts stay separate. Missing native counters cannot
be reconstructed as zero.

First-content latency excludes the empty assistant-role frame. It ends when the
first complete event with nonempty content arrives. Whole-request latency ends
at DONE. Both describe API delivery, not GPU phase clocks. Full input must equal
cached plus processed input; native phase rates remain unqualified observations.

`summarize_followups` requires one warmup plus three complete pairs. A Flexible
follow-up must show an actual hit and positive newly processed input; Off must
show zero reuse. It pools native acceptance counts rather than percentages.
Every result remains explicitly unqualified as a hardware measurement. Runtime
identity, memory, inter-arm output parity, cancellation and conversation
isolation require separate evidence.

See the [ServiceNow preparation note](../../../docs/integrations/halogen-servicenow-prefix-cache-20261101.md)
for the source findings and remaining runtime work. No profile or instance
change is deployed by these modules.

A separate authorized Root collector has since completed the
[actual cache comparison](../../../docs/benchmarks/halogen01822-cache-followups-20261101.md).
Its live evidence and quality checks are external to these offline modules.
