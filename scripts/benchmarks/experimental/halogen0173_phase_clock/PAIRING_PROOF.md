# Decode ownership pairing revision 2

The original pointer-based Decode pairing failed in the real cohort. Request IDs 3–6 began Decode on reused stack object 140720885412480 and ended on heap object 97485392864432. Missing-pair status 3 and duplicate-begin status 5 rejected that cohort. The original private directory, delivery seal and runtime evidence remain unchanged. Revision 2 is a separate sibling delivery and does not qualify that historical cohort.

## Pinned native ownership

Engine SHA256: `af4f07bbe3759206013eb6f1328095ca2105cfda5127c5b9a2ab93e1aea987b7`, 26,188,824 bytes. Cached source: `../updates-20261009-0202/runtime-data/usr/local/bin/flash_serve.data`.

Decode start call `0x17490b6` returns at `0x17490bb`; native code stores RAX at `[R14+0x198]`. Main passes stack request `SP+0xa00` at `0x173d4f4/0x173d4fc`, then inserts it into the vector at `SP+0x1d0` at `0x173d711..0x173d726`. Source destruction follows at `0x173d726/0x173d72e`. An alternate insertion occurs at `0x1732c7e..0x1732c93`.

Vector append `0x1749670` invokes move constructor `0x1747c40` at `0x174968e`, `0x174971d`, and `0x1749736`, including growth relocation. The constructor copies the first 16 bytes, preserving the signed 64-bit request ID at offset zero. It then copies exactly 0x81 bytes from source+0x188 to destination+0x188. This includes Prefill milliseconds at +0x190 and the exact native Decode start at +0x198.

Main places `&vector` into `SP+0x820` at `0x172ed03/0x172ed0b`. Completion helper `0x1745e50` obtains `vector.begin + index*0x308` in R15 at `0x1745e64..0x1745e7b`. It passes this heap element as formatter RDX at `0x1745f6d` or `0x1746205`, with the formatter call at `0x174620e`. Formatter `0x174c9a0` sets RBX=RDX at `0x174c9c4`, reads ID at `0x174c9cf`, and loads R15 from `[RBX+0x198]` at `0x174c9fa` before the selected end call.

Completion compacts the vector through move assignment `0x174a0f0` at `0x174628a`. Assignment also copies the first 16 bytes and the same 0x81-byte scalar interval. Thus both ID and exact native start survive insertion, growth and compaction.

The independent ownership reviewer compared eleven bounded mover/linkage windows against the pinned ELF. `static-pins.json` records the actual bytes, mapped offsets and unwind-function SHA256 values. The constructor validates all 15 windows, including the four original measurement sites. The launcher validates 14 distinct RVA windows: the separate formatter-native-start window is contained in the larger Decode-end window at the same RVA.

Unwind-bounded function hashes independently reported:

| Function | End-exclusive range | SHA256 |
|---|---|---|
| Move constructor | 1747c40..1748182 | 86e617d375a9b787fc65e3dc3d4ede1106c671d5b0b0cfa937f6bdd58d9453f2 |
| Vector append | 1749670..174979c | 6cd20e284268cf4f0749ac5d111c95d35851060f33786b57bdc8f2a51b283c60 |
| Move assignment | 174a0f0..174a9a4 | 3c725ccefaeaf954f7b5cf9929bd4821b9bdc04c9e6f93f5c4b6312aeca5e90d |
| Completion helper | 1745e50..1746464 | 065964b8060108e9d4b25ea13fa3570c25d7648f46afc2d48d8a6ddf9299a44b |

## Identity and failure behavior

The C lookup scans every active record. Decode matches phase 2 plus signed request ID. Exactly one active match is required; ambiguous active IDs invalidate matching records and emit nonzero status 7. A duplicate begin emits status 5 and cannot silently overwrite a valid open begin. A missing end emits status 3. End validation requires the original pair ID/start, the exact R15 native start, and the current object+0x198 native start. Mismatches produce native fallback and an error journal. Prefill continues to require identical object, caller stack and thread ID.

This does not assume global uniqueness for arbitrary native-protocol clients or multiple API instances. The tested singleton API allocates sequential IDs and the declared run has one slot. Unambiguous active identity and exact saved native start are always enforced by the adapter itself.

The journal records actual endpoint object/thread/stack, the original `begin_object`, actual signed endpoint request ID, and observed native start. Decode begin records object-native-start zero because native code writes the new timestamp only after the start call returns. Decode end records the observed object timestamp. `decode_pairing_version=2` marks activation and is mandatory in the new verifier.

The verifier preserves contiguous sequences, pair IDs, duplicate/missing rejection, all begins consumed, Prefill ownership, exact integer RAW delta/returned-end translation, stored Prefill-double agreement, completion through Decode, token counts, native D rounding and complete D coverage. It permits Decode object movement only with matching active pair identity and exact native start evidence. Every nonzero status rejects qualification.

## Scope and offline validation

Only `_ZNSt6chrono3_V212steady_clock3nowEv@@GLIBCXX_3.4.19` is exported. Real starts remain unchanged; selected valid ends return native_start+RAW_delta. Scheduling and other callers forward to the exact versioned real provider. Provider SHA256 remains `972bb2a18b71140dab0240f8a1f68ab3fb1d56bcd4c4f824a91b70888faf5a00`; constructor pin failures terminate with exit 125. Deferred arming and default-off/residency behavior are retained.

The red regression failed under the unchanged pointer verifier with `Unpaired or mismatched end`. It passes under revision 2. Focused checks cover moved Decode objects, reused source object with distinct active IDs, duplicate active signed IDs, incorrect observed/object start, Prefill object/thread/stack mismatches, incomplete pairs and D coverage, and all original environment/arming checks. The Windows DLL tests the same C identity lookup: 7 pairing cases, 1,000 integer delta vectors, 5 invalid delta cases, and 42 SHA vectors. Only numeric host code was loaded.

No WSL, upstream ELF, Linux adapter, GPU or NPU was executed by this delivery. Runtime qualification remains false until root's fresh cohort passes the strict revision-2 verifier. Instrumentation is measurement only and provides no acceleration claim.
