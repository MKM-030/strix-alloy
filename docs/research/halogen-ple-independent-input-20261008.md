# Independent PLE input preparation from the original general table

The new default-off CPU worker reconstructs the complete frozen M8192 PLE
input using owned raw tokens, explicit preceding history, constants extracted
from the original checkpoint and rows read from the actual general FP8 table.
Root independently compared every byte of the 40 MiB BF16 input with the
original GPU input and every byte of its 80 MiB FLOAT widening with the frozen
reference: both are identical. This covers 20,971,520 input values. No captured
sparse atlas or expected input was read by the worker.

The independently extracted constants occupy 280 bytes: multipliers 24 bytes,
offsets 128 bytes, moduli 128 bytes in physical artifact order. Native function
argument order remains multipliers, moduli, offsets. All three arrays equal
the prior native capture. General-table binding freshly checked the native
Windows file identity, 191,784 index bytes and four scale bytes; it read no
table rows. The 51,200,245,760-byte table contains 320,001,536 rows of 160 bytes.
Neither stage rehashed the full model; retained full hashes are provenance.

The single guarded input worker completed with child and guard exit zero,
errors empty and the owned Windows job closed. Minimum physical reserve was
26,386,874,368 bytes (24.57 GiB); minimum commit headroom was 122,511,228,928
bytes (114.10 GiB). Admission was 22 GiB with runtime floors of 18 GiB each.
There was no GPU/NPU call, server restart or live mapping read.

| Recorded scope | Seconds |
|---|---:|
| Complete external CPU guard, excluding PowerShell startup | 24.9553 |
| Worker through final checks/output renames, excluding receipt publication | 24.7030 |
| Serialized bounded table-read scope | 20.0378 |
| Row scatter | 2.8037 |
| Deduplication and page planning | 0.1016 |
| Row IDs and their hash | 0.0366 |
| Unique-row FP8 decode | 0.0218 |
| Final input scatter and FLOAT widening | 0.0652 |

The plan read 431,407,104 payload bytes in 90,778 serialized batches for
95,009 unique rows (15,201,440 logical bytes): 28.38 times the unique row
payload. Reads are sorted/coalesced, at most 1 MiB each, with a 16 KiB gap
bound and a total 1 GiB payload ceiling. Exact row coverage, output extent,
source identity, metadata, input pins and output hashes passed. Root freshly
rehashed both complete outputs and native row-ID/FP8/history reference files;
the receipt's row-ID and FP8 digests match. The worker does not persist its
row-ID or dense FP8 stream, so those two comparisons are digest checks.

The table-read timer contains cancellation-file existence probes, deadline
checks, seek and read. It includes 181,556 cancellation probes; additional
probes occur after every batch and in row-scatter tiles. The evidence cannot
attribute 20.0378 seconds exclusively to SSD latency. The next source-level
hypothesis is a bounded cancellation-probe cadence with separate timing for
checks and reads. Concurrent I/O remains a separate untested option. This
window has no controlled warm/cold-cache comparison and will not be repeated
unchanged.

Correct input reconstruction does not repair the separate strict CPU
projection mismatch and does not establish serving quality of approximate
NPU output. It also does not prove guest token/history ownership, later-chunk
publication, a readiness lead, persistent NPU multi-feed or GPU consumption.
The approximately 25-second preparation cost is currently unsuitable as a
one-block producer for an approximately six-second 8K Prefill chunk.

The original server remains ready/open on port 8840. Both installed current
backends retain the authorized 35 GiB physical startup floor, 131 GiB commit
floor at context capacity 262144 and 18 GiB runtime reserves. Root freshly
verified their source pins, actual process births, run IDs and authenticated
health. No startup was needed. This proves configuration and current health;
it does not prove safe startup at exactly 35 GiB under every load.

This is a CPU input-parity and preparation-cost result. It supplies no new
Prefill tok/s, Decode tok/s, native MTP acceptance or NPU-on/off throughput
comparison. The full acceleration goal remains unachieved and the automation
remains paused.

Evidence: [complete report JSON](halogen-ple-independent-input-20261008.json).
Prior actual NPU projection result: [component report](halogen-ple-npu-component-20261008.md).
