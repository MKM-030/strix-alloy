# Halogen 0.20.7 SSD prompt-cache restore after restart

The first measured request after restarting the private process restored
**8,448 of 8,498 input tokens** from the SSD. Halogen processed the
remaining 50 input tokens and returned the same answer bytes as the
in-memory hit. Complete Windows HTTP time was **0.743 s** after restart
and **0.253 s** for the in-memory hit. Each observation is one request.

| State | Input / reused / SSD restored | Output tokens | API prefill tok/s | API decode tok/s | Native MTP | Complete HTTP (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Cold seed | 8,498 / 0 / 0 | 3 | 1,157.17 | 65.79 | 2/2 | 7.424 |
| Frozen question, RAM hit | 8,498 / 8,448 / 0 | 3 | 273.08 | 70.92 | 2/2 | 0.253 |
| Same question, SSD hit after restart | 8,498 / 8,448 / 8,448 | 3 | 161.97 | 71.60 | 2/2 | 0.743 |

The two hit rows used identical `/v1/responses` request bytes and
generated the expected revision number, byte for byte. Their Prefill
rates count the 50 new tokens. The cold seed asked a different
question. The [earlier system-prefix comparison](halogen0207-responses-system-cache-20261123.md)
timed the same frozen follow-up with Cache Off at 4.298–4.403 s in
another campaign. The single restart establishes the restore mechanism.

## Native storage and process evidence

The private launcher used the v2 checkpoint, BF16 KV, r2 HT4, a single
32,768-position slot, paired 8,192 prefill settings, Flexible cache and
Thinking Off. Both private starts used the same profile and executable
with different controller and backend run IDs. The initial ready cache
was empty. Before stopping the first process it held 292,633,688 bytes.
The next process opened the same cache and its native disk hit counter
advanced from 0 to 1. The response's native timing reported 8,448
restored tokens in 367.3 ms.

The experiment bound one private native WSL ext4 directory read-write.
The directory identity and permissions were verified. The cache budget
was 1 GiB and cross-build pruning was off. The checkpoint and other
ordinary bindings remained read-only. The lowest request-sampled
physical or commit reserve was 25.19 GiB.
[Upstream persistent cache options](https://raw.githubusercontent.com/peonist-ai/halogen-flash-server/dea807d22a638c67553abea876344a8192054a94/docs/FLAGS.md#speed-levers)

The Direct I/O preflight wrote and read a separate 223 MiB test file on
the native filesystem, then verified its checksum and removed the file.
The sum of read syscall durations was 0.158 s. The application restores
its own prompt state and its request timing includes engine and serving
work as well as storage.

Raw requests, responses, native cache counters and lifecycle receipts
are retained locally under
`server/.local/halogen-update-20261122/primary0207/ssd-prompt-cache-prep-v1/ssd-prompt-cache-restart-run-v1`.
Both private processes closed. The ordinary 8,192-token prefill
profile on port 8840 and the Native voice endpoint reported ready
afterward, with ASR and TTS available.

| Evidence | SHA-256 |
| --- | --- |
| Completed lifecycle handle | `2861e0afcd967f3638c0f4585697b2ee7b1b90b10c0706093990e460b098d736` |
| Independent request and counter audit | `ddcfa5b7c05840fe9092c705d92f0af34db2cc62c5f374b9eb42db3dc13a8146` |
| Final serving verification | `f363c2cebf16bef43cc9454c9951754b63877b855cd46392072edd0f6a1d5ba1` |
| Direct I/O filesystem probe | `e401321891e5a63ba8d07f25cab48953bed427328df634f769890a59e84a6026` |

## Managed launcher validation

The [managed PowerShell option](../../backends/halogen-wsl2-0.20.7/README.md#persistent-prompt-cache)
passed a separate startup on a private port. The service verified the mounted directory's
device and inode, the native cache path and the 1 GiB budget. It passed both built-in
functional requests and reported ready. The native cache contained zero persisted records
after the startup smoke checks. The restore observation above came from the
earlier two-process experiment.

The first managed observation stopped before readiness when Windows temporarily denied
access to the status file during its atomic replacement. The later run retried transient
status reads and waited for both controller and backend readiness. Its verification receipt
has SHA-256 `9468610b4b394d921a21f163f13c5daf3ece5d3a9f49d0ff9bcc29e6c7d85651`.
