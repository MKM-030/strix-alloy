# E-backed lookup placement feasibility — 4 October 2026

One authorized synthetic lifecycle established that this guest can mount a new
ext4 image backed by E: without Windows administrator access or a WSL
configuration change. It establishes neither Halogen speed nor native VHD
storage. No model payload was accessed by the lifecycle, and no engine or NPU
ran. The 51.2-GB lookup extraction remains a separate experiment.

The raw script, operation state and final receipt are ignored local evidence:
`server/.local/lookup-loop-20261004/probe-7f83041c86c14b63a08f8c339702aa05.*`.
The final JSON receipt records every command, exact backing identity and cleanup.

| Observation | Result |
| --- | --- |
| Guest | Ubuntu 24.04; kernel `6.18.33.2-microsoft-standard-WSL2` |
| Required support | `CONFIG_BLK_DEV_LOOP=y`, `CONFIG_EXT4_FS=y`; tools already installed; `sudo -n` succeeds |
| Fresh image | `E:\AI\halogen-experiments\lookup-loop-20261004\7f83041c86c14b63a08f8c339702aa05\synthetic-64m.ext4` |
| Image size | 67,108,864 logical bytes; sparse creation, not a 64-MiB allocation claim |
| Returned owned loop | `/dev/loop0`, device `7:0`, backing inode `1407374883785146`, backing device `0:64` during the lifecycle |
| Fresh mountpoint | `/home/revn/.local/strix-alloy/lookup-loop-20261004/7f83041c86c14b63a08f8c339702aa05` |
| Mounted filesystem | ext4; mount ID 407; `rw,nosuid,nodev,noexec,noatime` |
| Synthetic marker | 4,096 bytes, read back byte-for-byte after fsync |
| Marker SHA-256 | `c8f5d0341d54d951a71b136e6e2afcb14d11ed8489a7ae126a8fee0df6ecf193` |
| Loop direct I/O | `DIO=false` |
| Recorded lifecycle duration | 0.570 seconds, excluding WSL command launch |
| Cleanup | Exact owned mount unmounted; exact verified loop detached; independent later queries found neither |
| Retained artifacts | Image, marker inside image, mountpoint directory, script and receipts preserved |

The script refused existing unique image/mountpoint directories, created the
image exclusively, and rechecked its regular-file identity and the returned
loop's backing path, inode, device and zero offset before formatting. It repeated
those checks before marker creation and cleanup. Work had a 100-second internal
deadline; cleanup had an additional bounded window; outer `timeout` provided a
120-second absolute stop. No timeout or retry occurred.

The E: mount reported `9p`, `cache=0x5` and `msize=65536`. The actual path is
**ext4 → buffered loop → 9p/DrvFS → E: NTFS**. Linux's loop implementation reads
through the backing file, so putting ext4 above that file does not remove the
9p transport. Extra guest caching is a possible confound, inferred from buffered
loop I/O and the backing mount's file cache. The
[Microsoft kernel loop source](https://raw.githubusercontent.com/microsoft/WSL2-Linux-Kernel/linux-msft-wsl-6.6.y/drivers/block/loop.c)
illustrates that backing-file mechanism; it is not a claim that this 6.18 guest
uses the linked 6.6 revision. The
[kernel 9p documentation](https://www.kernel.org/doc/html/latest/filesystems/9p.html)
describes `cache=0x5` as the mmap caching mode. Attaching a VHD through
`wsl --mount` instead requires administrator access according to
[Microsoft's disk mounting guidance](https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk).

A separate later metadata query saw the same image inode and size with guest
device 73, rather than lifecycle device 64. File identities must therefore be
qualified in the filesystem namespace/lifetime where they will be consumed.
The stock lookup source's current WSL identity still exactly matched its existing
`ngram-integrity.json` in a subsequent metadata-only check; no checksum was
recomputed.

## Implemented opt-in standalone lookup support

The managed profile option is exactly
`engine.lookup_tuning={"receipt":"<absolute Windows receipt path>","receipt_sha256":"<independently reviewed lowercase SHA-256>"}`.
It is limited to Halogen 0.16.2 with the v2 checkpoint. The receipt must remain
under that backend's `.local` directory or `server/.local`; path traversal,
symlinks, junctions/reparse points, extra configuration keys and malformed
digests are refused. The PowerShell launcher takes `-LookupReceipt` and
`-LookupReceiptSha256` together; the service receives `--lookup-receipt` and
`--lookup-receipt-sha256`. Omission preserves the stock manifest, installed
machine configuration and original `ngram-integrity.json`.

The new `scripts/lookup_source.py` first binds a bounded JSON read to the
independently pinned receipt digest. It requires the extractor's strict schema,
pinned complete-source SHA-256 and full file identity, exact tensor name,
storage 10, rank-three shape `[128,2500012,160]`, variant zero, payload length
51,200,245,764, verified XOR32, payload SHA-256, standalone data offset 320,
complete output size 51,200,246,144 and output SHA-256/identity. It reads the
source's existing qualified integrity receipt without replacing it. A receipt
for a different installed stock source is refused.

Guest metadata inspection reads only a 104-byte header and 160-byte tensor
entry from each file. It checks the retained source entry at index 27, canonical
single-entry output header/entry, source header digest, regular files, path
symlinks, and identities before/after the metadata reads. The output entry must
equal the original entry with only its tensor offset changed to 320.

For a new output identity, qualification independently reads the entire output
with the existing `bounded_hash.py`: bounded 8-MiB buffers and range-limited
`POSIX_FADV_DONTNEED`. A Windows physical/commit monitor publishes host frames
every 0.2 seconds with a strictly increasing sequence and unique run identity.
The guest requires an observed sequence renewal before reading payload, then
checks the 18-GiB floor and maximum two-second age of observed sequence progress
before and after each block. Qualification has a 600-second guest monotonic
deadline and an outer bounded guest timeout; Windows/WSL UTC offsets are never
compared. No GPU allocation occurs in
this phase. The observed full-file digest and identity must match the trusted
extraction receipt, followed by another metadata/receipt check.

Successful qualification creates its own exclusive, read-only identity seal in
the backend's `.local/lookup-qualifications` directory. An unchanged receipt and
output identity can reuse that seal; malformed cache contents or changed
identities fail closed. The per-attempt manifest records the complete
qualification and overrides only that attempt's `/ngram-w4b.hgn` mount and
`HALOGEN_NGRAM_TABLE`. Source/output metadata and the pinned receipt are checked
again immediately before container creation and before engine startup.
`runner.py`, `portable.py`, installed configuration and original lookup receipts
were not changed.

Offline validation passed: five focused receipt/source/CLI/real-PowerShell and
simulated-clock checks, plus a stock-versus-opt-in manifest check. The earlier
complete Windows backend suite passed 159 tests with 19 platform-specific skips;
after the sequence-clock correction, only the five focused module checks were
rerun and passed. The clock check accepts a simulated 35-second UTC offset,
refuses a frozen sequence after two guest-monotonic seconds, and enforces the
600-second guest-monotonic deadline. These tests read small
fixtures, not model payloads. No large extraction or readback has yet qualified
the actual standalone lookup, and no profile was promoted.

The next step is the separately controlled extraction/readback and engine
window, retaining the 18-GiB physical/commit guard and recording qualification
I/O, first-prompt lookup, prefill, request wall time and warmed calls separately.
The extractor's range-limited source cache advice and qualification readback
must be recorded when interpreting subsequent cache state. Canonical extraction
also changes the tensor's page alignment, so comparing the same standalone
layout across placements would better isolate a storage effect. No throughput
estimate follows from the synthetic lifecycle or these offline checks.
