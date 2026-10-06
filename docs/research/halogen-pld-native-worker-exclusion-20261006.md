# Native worker exclusion for a finite PLD owner

**The disk-cache worker has a concrete source-level bypass, the construction timer is joined before serving, and the parallel-copy worker exposes a real pre-join callback risk.** The indexed workers also join on normal return; their backend vtables are now resolved, but the large executor's complete transitive alias proof remains open. These findings narrow the worker residual in the [owner and capture audit](halogen-pld-native-owner-capture-path-20261006.md). They do not establish that the required native observations are installed or make `CallerTruth.ownership_qualified` true.

For the selected finite mode, exclude the disk family using the actual cache-manager holder and its startup allocation history; admit only after successful model construction; retire on postseed command/prefill callback entry; and retire on postseed indexed-dispatch entry. A copy-helper activity observation additionally prevents a nested capture from being admitted before its joins. Those are boundaries in the pinned native code, with specific mutations and completion paths below. A profile named **Cache Off**, one queued record, one handler/thread, and a stable slot are supporting context, not independent evidence of these exclusions.

This is a source-only audit of retained ELF, text disassembly and unwind frames. No compiler, test, native runtime, WSL, hardware, process-management or server lifecycle action was used. No production file, credential, staging or commit operation is part of this audit. Device placement and serving metrics remain `null`.

## Actual identities and worker inventory

Use `A` for the actual argument aggregate saved at handler outer `RSP+0` by `0x171c276`, `M=*(A+0)` for the native model/context object, and `C=*(A+8)` for the prompt-cache manager. At `0x171c28b..0x171c28f`, the handler loads `A`, then directly loads `M` from its first field. This is the earlier audit's `**(outer RSP+0)`, without a further dereference of `M`.

Startup allocates `C` as `0x158` bytes at `0x171a1a1..0x171a1ab`. Its constructor receives `RSI=&main RSP+0x6d8` at `0x171a1b8..0x171a1c8` and stores that exact value at `C+0x60` (`0x173bddf`). Startup also writes that address into `A+0` at `0x171b3b8`, and writes the cache manager saved at main `RSP+0x38` into `A+8` at `0x171b3c5`. Thus `*(C+0x60)=*(A+0)=M` on this constructed path. Check the selected request's `+0xd8` against this actual `M`; do not derive the cache manager from a packet or frontend label.

All encoded calls to thread start `0x18d3630` in the retained text are:

| Start call | State vtable | State run | Family |
|---|---|---|---|
| `0x173eac3` | `0x18d4fd8` | `0x1745730` | Optional prompt disk-cache queue |
| `0x176cb6a` | `0x18d5bd0` | `0x17ec240` | Construction memory/progress timer |
| `0x17d7cd6`, `0x17d7dee` | `0x18d7ec0` | `0x1847cb0` | Parallel native model-buffer copies |
| `0x188dba7`, `0x188dc98` | `0x18d8648` | `0x189b030` | Indexed repacking/hashing jobs |

The vtable slots are ELF `RELATIVE` relocation addends. The corresponding destructors are `0x1745710`, `0x17ec220`, `0x1847c90` and `0x189b010`. The `0x1745706` address supplied at thread start is a one-byte `ret` linkage argument, not the queue worker's run method. An encoded direct-call scan is not a proof that arbitrary indirect invocation is impossible; the finite mode must bind its observed construction and dispatch history to these actual objects.

## Optional disk-cache queue: allocation, enqueue and teardown

The `0x240` payload `W` is a separate cache object, not the selected request's `0x1f8` allocation. Startup calls cache-tier initializer `0x173c200` at `0x171a299`, before the serving handler path. Its first operation reads the ELF literal `HALOGEN_CACHE_DIR` through `getenv` at `0x173c21a`:

| Native branch | Effect |
|---|---|
| `0x173c21f..0x173c222`, result null | Branches to `0x173c3e9`; returns false without allocating `W` or starting a thread. |
| `0x173c22b..0x173c22e`, first byte zero | Takes the same preallocation return. |
| `C+0xd9 != 1` or signed `int32(C+0xb0) >= 0`, `0x173c234..0x173c248` | Returns after the diagnostic that disk tier needs the in-place snapshot and no cache file. |
| Enabled allocation at `0x173c2ae`; constructor `0x173dcb0` at `0x173c352` | Starts the queue thread and stores `W` at `C+0xe0` (`0x173c357`). |
| Constructor result `W+0x50 == 0`, `0x173c381..0x173c389` | Calls teardown `0x173ee90`, frees `W`, then clears `C+0xe0` at `0x173c3a0`. |

Cache-manager construction zeros `C+0xe0/+0xe8` at `0x173be9e`. The reviewed initializer is the sole encoded direct caller of `0x173dcb0`; startup is the sole encoded direct caller of `0x173c200`. The absent/empty environment branch dominates the allocation and start in this initializer. No current environment was read for this audit.

The narrow exclusion therefore requires the **actual** `C=*(A+8)` and `*(C+0xe0)==0`, together with the observed successful startup path that either skipped allocation or completed the failed-construction teardown. If `C` is absent, the adapter needs observed construction provenance establishing that no cache worker for this `M` was published. A late null holder alone cannot rule out a previously detached or unobserved worker. Retire on any later cache initializer `0x173c200`, worker constructor `0x173dcb0`, or cache-manager teardown `0x173c950` entry associated with this `M`; do not reconnect a retired birth when the holder becomes null. No enabled disk worker is admitted under this bypass.

`W` construction stores the borrowed `M` at `W+0` (`0x173dcca`). It creates mutex `W+0xd8`, condition `W+0x100`, result-vector storage `+0x130`, cache trees `+0x148/+0x178`, a deque around `+0x1b8`, queue begin/end `+0x1c8/+0x1e8`, stop byte `+0x218` and thread handle `+0x220`. The `0x10` thread state gets vtable `0x18d4fd8` and payload `W` at state `+8` (`0x173ea9b..0x173eaa5`). Run `0x1745730` loads that payload and jumps to `0x1745740..0x1745fce`.

The upstream enqueue function is `0x1754240..0x1755032`, with sole encoded direct call `0x1753bc1`. That caller loads `RDI=*(C+0xe0)` at `0x1753b9e`. Enqueue requires positive `ECX` and `W+0x50 != 0` (`0x1754259..0x1754268`). It builds a `0xe0` job at enqueue `RSP+0x40`, allocates/copies strings and vectors, then transfers the owned buffers into the deque under `W+0xd8`. It advances end `W+0x1e8` by `0xe0` at `0x1754dd4`, unlocks at `0x1754de6` and notifies `W+0x100` at `0x1754df5`.

The snapshot helpers have concrete copy semantics: `0x17563d0` and `0x1756510` copy the `R8/R9` input ranges into the job's own vector descriptors at enqueue `RSP+0xd8/+0xf0` (`0x1754b44/0x1754b68`); `0x1756a60` copies the supplied vector into the descriptor at `RSP+0x108` (`0x1754b80`). Their destinations allocate/resize and copy bytes; they do not save the input-range pointer as the vector's owned begin. Earlier `memcpy` calls at `0x1754710`, `0x1754870` and `0x17549cd` also populate job-owned buffers. This excludes a direct borrowed-vector lifetime argument for those copied fields, but does not erase the borrowed `M` in `W+0`.

The run loop moves a deque entry into its own `RSP+0x88` job, destroys the moved-from entry, pops it, unlocks the queue mutex and calls `0x1746300(W,&job)` at `0x1745a56`. It relocks and transfers its result into `W`'s result vector. No indirect call occurs in the reviewed run span. Job destruction `0x1746a20..0x1746af0` releases owned vector fields `+0x50/+0x68/+0x80/+0x98/+0xb0/+0xc8` and strings `+8/+0x28`; it does not invoke the selected request destructor.

Executor `0x1746300..0x1746a1b` computes sizes/checksums from job vectors, prunes cache trees through `0x1746af0`, builds filenames through `0x17437f0/0x17444c0`, and writes disk data through `0x17472c0`, `0x1747600` and `0x1747cd0`. Its reviewed instructions do not directly dereference `W+0`. Enabled-mode transitive exclusion would still need to close those helpers and their descendants against the borrowed `M`, selected slot and request aliases. It is unnecessary for the absent-worker finite mode; it is not declared proved here.

Teardown `0x173ee90` locks `W+0xd8`, sets `W+0x218` at `0x173eec0`, unlocks, notifies at `0x173eed6`, and **joins `W+0x220` at `0x173eede` before freeing queue/cache/buffer state**. Calls include failed initialization `0x173c38e` and cache-manager destruction `0x173c967`. Destruction entry retires the private feed before the native join/free path; a future observation may record successful join but must not revive that birth.

## Construction timer: borrowed stack, no request role, joined return

Timer state `+8` points to constructor `0x176b800`'s local payload `L` at outer `RSP+0x460`. `L+0` receives the constant rodata label **reserving working memory** (`0x176ca45..0x176ca4c`), not a native model pointer. Other fields hold the interval, memory metrics, start time, mutex `+0x38`, condition `+0x60` and stop flag `+0x90`. Environment literal `HALOGEN_RESERVE_TICK_S` at `0x176cab8` controls creation; a nonpositive interval skips the start.

Run `0x17ec240..0x17ec3d7` waits on the timed condition, unlocks and invokes `0x17e63e0` with its own stack scratch at `0x17ec305`. That helper initializes its supplied 24-byte output and reads memory-stat text, including literal `/proc/buddyinfo`; it does not receive the selected request, vector or model slot. Progress printing uses the output `FILE` global at `0x18d91a8`. The reviewed worker's pointers serve local payload/scratch and printing roles.

Creation `0x176cb6a` is within constructor FDE `0x176b800..0x17702db`; its sole encoded direct caller is startup `0x171a13f`. Normal completion sets stop `L+0x90` at `0x176f3ee` under its mutex, notifies at `0x176f406`, **joins the local handle at `0x176f413`**, destroys `L` at `0x176f43c` and reaches normal return `0x176f477`. Native model reset `0x1779250` at `0x176f3c6` occurs before this teardown.

Successful construction return therefore closes this timer's borrowed-stack lifetime and concurrent mutation scope before selected request birth. A later construction/reset entry for `M` retires an active finite feed as in the owner audit. An exceptional or unobserved constructor completion is not a successful admission boundary.

## Parallel copy: model mutation and callback reentry before join

Run `0x1847cb0..0x1847d85` receives a `0x48` state with borrowed pointers to the enclosing helper's stack: atomic next index `+8`, count `+0x10`, native model `+0x18`, stride `+0x20`, index-array descriptor `+0x28`, mutex `+0x30`, outstanding count `+0x38`, and condition `+0x40`. It claims blocks of 256 using `lock xadd` at `0x1847cc9/0x1847cea` and calls `memcpy` at `0x1847d3b`:

```text
destination = *(M+0x6b8) + stride * i
source      = *(M+0x678) + stride * indices[i]
bytes       = stride
```

This is actual native model-buffer mutation. The state has no direct request/vector field, but a model alias is sufficient to make a blanket worker exclusion false. At completion it decrements the enclosing outstanding count under the mutex and notifies if zero (`0x1847d51..0x1847d79`).

Enclosing helper `0x17d76b0..0x17d9657` receives `RDI=M`; its sole encoded direct caller is target-forward machinery at `0x17dd721`. Both start variants, `0x17d7cd6/0x17d7dee`, use the same run. The helper waits for outstanding count zero at `0x17d81d0..0x17d81e0`, then **joins every handle in its vector at `0x17d8210..0x17d821f`**, verifies each handle is zero at `0x17d8230..0x17d8241`, frees the vector and destroys the condition. Its only ordinary return is `0x17d92da`, after joins; an empty handle vector legitimately skips the join loop. Exceptional cleanup calls `0x1859bb0` at `0x17d9607`; that vector destructor terminates if a handle remains nonzero (`0x1859bd0..0x1859bf3`). It supplies no normal capture continuation with a live joinable host thread.

**The helper invokes `M+0x250` before those joins.** Calls `0x17d8045` and `0x17d816c` are guarded by `*(M+0x248) != 0`; the former passes saved outer `RSP+0x158`, the latter passes the address `M+0x238`. The serving handler installs callback `0x1736aa0` at `M+0x250`. That callback polls root commands through `0x1730890` at `0x1736ab7`, so command/cancellation/lifetime processing can reenter while copy workers retain `M` and enclosing-stack pointers.

The finite policy retires **before command processing** on any postseed `0x1736aa0` entry under the selected handler/model identity. Observe helper `0x17d76b0` entry and retain an active-depth fact until successful return after the joins; never admit a nested capture while that depth is nonzero. The current outer handler cannot assume exclusive mutation merely because the callback uses its thread. Successful helper return establishes cessation of this host-copy family, not ownership of every other native alias or asynchronous device operation. No native callback behavior needs to be changed by this private retirement policy.

## Indexed workers: joined host scope and resolved backends

Dispatcher `0x188da30..0x188dff3` has direct callers `0x188b117`, `0x188e8a9` and `0x189030a`, contained in FDEs `0x1889580..0x188d531`, `0x188e070..0x188eebc` and `0x188fae0..0x189083a`. Their printable labels are **repacking GGUF**, **repacking** and **hashing**. They supply caller-owned stack work contexts `T` at `RSP+0x180`, `RSP+0xa0` and `RSP+0xe0`, respectively, with separately allocated record/index/scratch storage.

Run `0x189b030..0x189b19e` has a `0x38` state: worker index `+8`, atomic job-index pointer `+0x10`, index-vector descriptor `+0x18`, `T` at `+0x20`, byte-progress pointer `+0x28` and completion-count pointer `+0x30`. It claims one index with `lock xadd`, calls `0x189b1a0(T,index,worker_index)` at `0x189b0d4`, updates progress and performs the mapped-memory advice operation on spans based on `*(T+0)->+0xd8`. It does not carry a direct selected-request field.

Dispatcher starts the requested workers, stores their handles, waits for progress and **joins every handle at `0x188def0..0x188deff`**. It asserts handle zero at `0x188df10..0x188df1d`, frees the vector and reaches its only ordinary return at `0x188df5b`. Empty-vector control branches through `0x188df5c` to the same return. Exceptional cleanup calls terminating handle-vector destructor `0x1859bb0` at `0x188dfa8`; it does not return normally with a joinable thread.

The executor's indirect backend is exactly `B=*(T+0x30)`. Representative calls are `0x189b449` through `vtable+0x10`, `0x189b47c` through `+0x18`, and `0x189fad0` through `+0x20`. The three caller constructions resolve these slots:

| Dispatcher caller | Backend binding | `+0x10` | `+0x18` | `+0x20` |
|---|---|---|---|---|
| `0x188b117` | `T+0x30=&caller RSP+8` at `0x188b0af..0x188b0b4`; vtable `0x18d85b0` at `0x188af70..0x188af77` | `0x1899ab0`: address from mapped base and `0x98` record offset | `0x1899ad0`: checksum into backend-owned per-record vector | `0x1899b54`: `ret` |
| `0x188e8a9` | `T+0x30=&caller RSP+0x58` at `0x188e865..0x188e86a`; vtable `0x18d86d8` at `0x188e6b3..0x188e6ba` | `0x18a3f40`: per-worker scratch address/resize | `0x18a3f80`: checksum, then positional output-file write | `0x1899b54`: `ret` |
| `0x189030a` | `T+0x30=&caller RSP+0x58` at `0x18902c5..0x18902ca`; vtable `0x18d8728` at `0x188ff61..0x188ff68` | `0x18a4050`: scratch address/resize | `0x18a40d0`: checksum/hash accumulation | `0x18a42c0`: hash finalization and owned string/result moves |

Scratch resize helper `0x1753f70` allocates/copies owned vector bytes. File writer `0x188f8d0` loops over positional writes at `0x188f90b` until the supplied byte count is consumed; error paths throw. Hash compression `0x18a45f0..0x18a481f` has no call instruction; hash finalizer `0x1890840` operates on supplied hash state and local output, allocating its returned string. The reviewed backend methods expose no thread start, serving callback, retained selected-request pointer or asynchronous dispatch. This resolves the formerly unidentified virtual backend methods; it does not assert that every path of the large executor `0x189b1a0..0x18a06c6` has been exhaustively reviewed.

The bounded executor reads show transformed destinations based on metadata field `+0x78` (for example `0x189b44c..0x189b464` calls `0x18a0c70` with that destination plus byte offset). The remaining enabled-concurrency proof is therefore specific: trace every executor branch, its metadata destinations and direct transformation callees, and prove those buffers cannot alias the selected `M`/slot/request vector or publish further work. Normal dispatcher return closes the identified host threads, but a broad “loader only” inference does not replace that proof.

The immediate finite bypass is to retire on **postseed `0x188da30` entry** before any start. If it ran before admission, require actual observed successful return after joins and no active dispatcher depth. If a new dispatcher begins during the finite feed on any thread, retire independently of its printable label. This retains native execution and requires no synthetic job, runtime probe or fixture qualification.

## Result and evidence pins

The source-level worker conditions for a future installed observer are now finite: actual absent disk worker with startup provenance; successful completed construction timer; no nested copy-helper capture and retirement before postseed callback processing; and no postseed indexed dispatch. The owner audit's destructor, cancellation, reset/import and slot observers are still independently required. This report does not claim their installed completeness, so `serial_owner`, `lifetime_held`, `reset_excluded` and `ownership_qualified` remain false for source fixtures. Device placement, latency, throughput, acceptance and serving equality are `null`.

Pinned inputs were rehashed for this audit:

| Input | Bytes | SHA256 |
|---|---:|---|
| [ELF](../../backends/halogen-wsl2-0.16.2/.local/flash_serve) | 26,052,768 | `ac123b7ff5134e527368fc0644598379bcd976630691d36e9a469d55bee23f3b` |
| [Retained text](../../server/.local/optimization9h-20261004/mtp-route-static-20261004/host-text-disassembly.txt) | 22,406,098 | `523467ac08e576e770a9fcffdb59ffa9542f82d58958bd03d74743f8caccb8f9` |
| [Retained frames](../../server/.local/optimization9h-20261004/mtp-route-static-20261004/host-frames.txt) | 3,177,351 | `03b9bef6fd4182013dcec8ecb9c850dcc5c5ae474b57ecf2925934359115b923` |

Text RVA minus file offset is `0x1000`; the relevant data PT_LOAD difference is `0x2000`. The low rodata literals above lie in an identity-offset load segment. Vtable methods use ELF relocation addends, not unrelocated file bytes. The following instruction bytes pin the principal allocation, mutation, callback and completion boundaries:

| RVA | Bytes | Meaning |
|---|---|---|
| `0x173be9e` | `0f 11 87 e0 00 00 00` | Initial null disk holder |
| `0x173c222` | `0f 84 c1 01 00 00` | Absent directory skips allocation/start |
| `0x173c22e` | `0f 84 b5 01 00 00` | Empty directory skips allocation/start |
| `0x173eaa5` | `4c 89 70 08` | Actual queue payload in state |
| `0x173eac3` | `e8 68 4b 19 00` | Queue thread start |
| `0x173eede` | `e8 7d 47 19 00` | Queue thread join |
| `0x176f413` | `e8 48 42 16 00` | Construction timer join |
| `0x1847d22` | `49 03 be b8 06 00 00` | Copy destination native model buffer |
| `0x17d8045` | `41 ff 95 50 02 00 00` | First pre-join model callback |
| `0x17d816c` | `41 ff 95 50 02 00 00` | Timed pre-join model callback |
| `0x17d8213` | `e8 48 b4 0f 00` | Copy-family handle join |
| `0x188def3` | `e8 68 57 04 00` | Indexed-family handle join |
| `0x189b449` | `ff 50 10` | Indexed backend source/scratch method |
| `0x189fad0` | `ff 50 20` | Indexed backend completion method |

Verification is bounded local byte comparison, retained-call/frame checks, input/document hashing, local-link resolution and whitespace inspection. No execution-based worker exclusion or serving result was produced.
