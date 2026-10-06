# Explicit GPU counter windows

The explicit-path collector passed two bounded idle API checks under the existing
HistoricalStock server. These checks executed no model inference, NPU operation
or server lifecycle. They establish counter acquisition and owned cleanup, not
an LLM speed improvement or attribution of Windows GPU packets to a Linux task.

The wildcard raw-array collector had previously returned eight duplicate VM
instance-name groups and was rejected before baseline acknowledgement. That
unchanged collector was not retried. The corrected collector follows Microsoft's
documented sequence: add the English wildcard counter, obtain its localized full
path, expand it, then add each explicit provider path. Persistent handles retain
the provider occurrence index; enumeration rank does not assign identity.
[Microsoft API sequence](https://learn.microsoft.com/en-us/windows/win32/api/pdh/nf-pdh-pdhaddenglishcounterw).

| Idle API check | Counter entries | Raw JSONL bytes | Native exit | Owned job closed |
| --- | ---: | ---: | ---: | --- |
| Explicit paths, verbose source descriptions | 358 | 6,045,082 | 0 | Yes |
| Explicit paths, fixed registry references | 358 | 2,254,390 | 0 | Yes |

Both checks had nine collection points. The compact output reduces repeated
counter descriptions by approximately 62.7%. This is a serialization result;
it is not a measured reduction in inference time. A replay also reconstructed
all nine original points without any logical field difference. Removing a
counter and its pair was rejected by the fixed-registry coverage check.

The compact baseline preserves each exact full path, parsed instance name and
provider occurrence index. Subsequent raw values and calculated pairs reference
that registry. Topology records preserve the provider's original order, exact
indexes, acquisition brackets and any unmapped path literals. The consumer
requires every registered counter exactly once in each raw array, pair list and
topology. Invalid, changed or unmapped coverage rejects the whole window. The
original JSONL stays unchanged on disk.

Resource limits remain 64 MiB total output, 8 MiB per line, 16 MiB private memory,
500 ms nominal sampling, 1,500 ms maximum collection gap, and a 100 ms memory
monitor with a 250 ms gap limit. The collector reserves the complete row before
writing bytes. Admission requires 22 GiB physical and commit headroom; the
continuous floor is 18 GiB for both. A lock serializes the memory statistics.

The measured-window contract is unchanged: validate an excluded warmup and idle
state; acquire and durably acknowledge a fresh baseline; retain every interval
through a final collection strictly after all measured request brackets. No
request-interior filtering or idle-margin exclusion is used. An unadmitted
counter exceeding 2% Copy or 1% on another engine rejects the window. System
PID 4 remains unadmitted.

Because native query access to the VM processes is unavailable to this tool
token, the coordinator separately labels their local `CIMWin32.Win32_Process`
birth evidence. It brackets that census with ToolHelp observations and preserves
the complete DMTF timestamp, provider, host, namespace and class. These records
explicitly say that native handles and executable images were not verified;
they provide boundary continuity for admitted proxy aliases, not guest packet,
allocation or generation ownership. The owned collector and serving processes
still use actual native process handles.

Raw directories, source and binary seals, replay receipt and the new frozen 16K
comparison plan are retained in the accompanying JSON. The original explicit C
source is archived byte-identically in its build directory. The compact C build
passed `/W4 /WX /O2 /MT`; both runtimes ended via their own marker, closed their
owned jobs, and verified authenticated gateway readiness afterward.

There are no new Prefill, Decode or acceptance figures from these idle checks.
The separate fresh 16K comparison uses one warmup and three measured requests in
each of Stock-before, checked-copy candidate and Stock-after, with unchanged
input, request, output parity and memory rules. Its result is reported separately.
