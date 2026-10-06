# Independent Prefill HT capture audit, 2026-10-06

This finite source audit binds the proposed ordinary QKV capture entry points,
descriptor layout, and store dispatch. It performed no engine, hardware, WSL,
model-payload or lifecycle operation. Live allocations, route and stream remain
capture observations; this note grants no runtime admission or speed claim.

## Source identity and byte extents

Pristine local ELF `backends/halogen-wsl2-0.16.2/.local/flash_serve` is
26,052,768 bytes, SHA-256
`ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b`.
Retained `mtp-route-static-20261004/host-text-disassembly.txt` SHA-256 is
`523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9`.

Function bytes were independently reconstructed from that text, checking every
address for continuity and excluding bytes outside the retained FDE interval.
These are pristine source hashes, not fresh live executable hashes.
Bounded direct reads of the pristine ELF at FC file offset178bf90/8215 bytes
and packed offset17f7280/2913 bytes also reproduce their hashes and 32-byte
entry signatures exactly.

| Routine | Half-open RVA extent | Bytes | SHA-256 |
|---|---|---:|---|
| FC dispatcher | `[178cf90,178efa7)` | 8215 | `f8f9d77041011251d11d0b97d7298926aa053d5435310826a00c408e5bff24e9` |
| Packed helper | `[17f8280,17f8de1)` | 2913 | `0624974055273bd4dee85357d971b3a4b32930d96c03bcd833b0fd2d860e48f3` |
| Native HT | `[18092f0,1809ba4)` | 2228 | `fda51e1d8cf5008e6e5e61a85ee33199a008a4833799452d1e6db9786350e231` |
| Original preparation | `[17ec6e0,17ecede)` | 2046 | `34bb1998a74e03c63c714ea1e43d505eb88e59ff1c6266f39ba997a6f174d12d` |
| BF16 library wrapper | `[18c6b80,18c6be6)` | 102 | `6336433c1a337ff1faf7f72767ea869bfab343355ce74130226bd0ba76651a7d` |

## Hook and call binding

Both FC and packed entries begin `55 41 57 41 56`, the complete instructions
`push rbp; push r15; push r14`. A five-byte patch/trampoline returns at entry+5,
before `push r13`, with no relocated relative-address instruction. A later
implementation must independently prove its relative relay distance, preserve
all original arguments, and validate pristine live bytes before patching.

Ordinary QKV call `17913fb -> 178cf90` returns to `1791400`. Its FC ABI is
`D, X, Y, int N, int M, int64_t K` in `RDI, RSI, RDX, ECX, R8D, R9`.
FC call `178cfbb -> 17f8280` returns to `178cfc0`. Packed ABI is
`D, X, Y, bool output_float32, int N, int M, int64_t K`, with the seventh
argument on the stack. The ordinary FC supplies `output_float32=0`.

The first selected shape must be `M8192/N10240/K2560`, with both caller edges
and the independently identified `layers.0.linear_attn.in_proj_qkv.weight`.
Both hooks must retain exactly one original call, output and return behavior.
The packed helper returns a boolean in AL (`17f8b4a..17f8b4d`); its successful
result does not by itself identify which internal preparation branch ran.

## Descriptor and HGN mode linkage

The fixed `[D,D+78)` prefix contains packed pointer+30, signs+38, scales+40,
mode32+48, N32+4c, K64+50, and diagnostic name pointer+70. Native HT and
original preparation select template3 for mode==3 and template4 for every
other value; independent capture admission must reject values outside3/4.

Descriptor initializer `17eefa0` reads runtime tensor store32 at+10 and
variant32 at+44 (`17ef41e/17ef422`). Store dispatch at `17ef470..17ef489`
uses the signed relative jump table at RVA45e7c. The exact local pristine ELF
is ELF64LE, program headers at64, entry size56, count11. PT_LOAD index2 has
file offset0, RVA0 and file-backed size24,216,748, mapping the store16 slot
RVA45ebc directly to file offset45ebc. Its four bytes are `5f977a01`, signed
relative offset+24,811,359; adding tablebase45e7c yields **17ef5db**. The
four-byte slot SHA-256 is
`f939428b7e1f401181dbde61c6d4c5343bed5e58c03f4fdf5605b23b821cf4cf`.

That branch (`17ef5db..17ef60c`) directly stores runtime tensor.device+8
at descriptor+30, stores `(variant >> 1) & 7f` at descriptor+48, and copies
rank2 N/K to descriptor+4c/+50. Thus runtime store16/variant1208 follows
the direct packed-pointer branch and yields mode4. Capture must still record
and bind the current descriptor; metadata cannot substitute for that observation.

The header/table-only receipt
`server/.local/optimization9h-20261004/prefill-qkv-metadata-only-20261006.json`
has SHA-256
`634ef8141548695c41d1fc71f085e78b28d4e89094957bea69e735583ef7f55c`.
It independently declares the exact first ordinary QKV store16/variant1208,
N10240/K2560, packed size13,107,200, signs5120 and scales20480 bytes.
It does not establish current GPU allocation extents or a payload checksum.

## Stock route and complete native work

At M>8, direct native admission is attempted only for output_float32=0,
18dd260 enabled, 18dd208 clear, and M<=18dd310 (`17f83d3..17f841f`),
after lazy control initialization. Native HT separately needs populated
18dcf30 and M*K<=18dcf28 (`1809301..1809321`). These controls must be
recorded without changes; admission on another branch cannot be assumed.

The direct original-prepared branch to17f860a requires bit0 of18dd270 and
18dd260, output_float32=0, 18dd208 clear, router18db4d8 nonnull, and
N*K<=(uint8_t18db4d0)<<27 (`17f843b..17f849a`). With cache control
18dcf41==1 it tries180c4e0; a nonnull return skips17ec6e0. Otherwise it uses
18db4c8 and calls17ec6e0 at17f865c. Both join the BF16 library call at17f8696.
The alternative transformed paths cannot be labelled as this direct route.
Snapshotting controls alone is insufficient to prove the observed branch;
later replay requires actual preparation/cache/library receipts and stream.

The original rotation argument array at18093b4..1809409 is
`(X, D.signs, rotated_X, M, K)`, followed by native packed multiplication and
any required completion. The design note's swapped first two arguments was
corrected. Direct native_ht(D,X,Y,...) replay preserves the original assembly.

## Capture implementation review

The independently reviewed source is
`scripts/benchmarks/halogen_prefill_ht/capture.c`, SHA-256
`bd06d7fcfab41d950aaafe2a504b33bb5a7c91275cd7984941371278d5c41e82`.
Its accompanying README SHA-256 is
`09dbfb0ddb2dcdd72bf0915a1b94033c2ce540f4c3df160a27f8a394f9011d3e`.
No compilation or runtime was performed by this reviewer.

The implementation's two-hook ABI, whole-instruction trampoline, hash and
signature validation, canonical seven-assignment receipt parser, modes3/4,
TLS caller/shape/identity scope and exactly-one original forwarding agree
with the retained source. It preserves original results and errno. Its
observer adds no tensor writes or GPU allocation. Failed original submissions
invalidate the fixture rather than silently count as successful observation.

The initial draft delegated all pointer spans externally. The reviewed revision
resolves `hipMemGetAddressRange` and requires five successful complete allocation
coverage checks after pre-original completion before input copies, plus five
checks after original completion before reference Y copy. Short-circuit checks
guard overflow and subtraction, and both boundaries must return identical base
and extent. Missing symbols, failed queries, incomplete coverage and changed
ranges reject the fixture. These receipts combine with root's exclusive,
immutable process/model lifetime; they do not authorize competing calls.

No source correctness blocker remains for root compilation and one admitted
capture of this exact revision. Runtime admission, parent request success and
cleanup remain root responsibilities. Library preparation/cache branch,
algorithm bytes/identity and native controls remain explicitly unbound. This
review does not qualify frozen replay, a numerical tolerance, Prefill or Decode
token rates, or native acceptance change.
