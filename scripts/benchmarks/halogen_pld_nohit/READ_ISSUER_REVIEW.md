# Native host read issuer source review

**No blocking implementation defect was identified in the frozen default-off read issuer under its documented real paused-owner capability contract.** The source connects privately supplied real registers and held host objects to bounded owned copies and an unqualified result. It does not implement the upstream native entry, cache-startup absence observation, worker-join observations or held mapping authority needed to exercise that read path. The current stock register-only installer therefore remains unable to enable it.

## Scope and source pins

This review read `native_owner_read_issuer.h/.cpp` and `NATIVE_OWNER_READ_ISSUER.md`, checked the adjacent capture and value-result contracts, and compared the concrete field bindings with the retained [host publication](../../../docs/research/halogen-pld-host-publication-20261006.md), [owner serialization](../../../docs/research/halogen-pld-live-owner-serialization-20261006.md), [worker exclusion](../../../docs/research/halogen-pld-native-worker-exclusion-20261006.md) and [positive owner scope](../../../docs/research/halogen-pld-positive-owner-scope-20261006.md) evidence. The earlier [capture review](NATIVE_OWNER_CAPTURE_REVIEW.md) remains frozen.

| Reviewed file | SHA256 |
|---|---|
| `native_owner_read_issuer.h` | `9c2046d6ab7873d699725cbc3486e7bbf42e73f3dcbbeaf2849b176b0e37ece8` |
| `native_owner_read_issuer.cpp` | `adb1791a50e07f5d81c5803a6e6ca64b5e2fa50349fe1987ff20b5b095ee377f` |
| `NATIVE_OWNER_READ_ISSUER.md` | `e88c47e84dca0d173b6d63174edd73f38c50dc369596f7408f1015211e825278` |

The reviewer used only source reads and local hashes. No compiler, linker, tests, runtime, WSL, engine/model, hardware, process/lifecycle, staging or commit action ran. The reviewer wrote this new report and separately persisted the already completed complement reconstruction's stored results; no reconstruction was rerun. Root owns emitted-object inspection and any finite build or execution receipt.

## Entry and authority boundary

Implementation lines 68-77 return before native reads when disabled, when the entry pointer is null, or on an unsupported platform. The public constructor's enable bit alone cannot obtain a `PausedNativeOwnerEntry`. The entry is noncopyable/nonmovable, contains references to the real register image and immutable token definitions, and has no public constructor. Its documented lifetime ends before the genuine synchronous native CALL returns.

The `NativeOwnerReadConnection` declaration has no definition or installed caller in this source. Its contract must establish actual startup model/cache identity, image/hash/token binding, held stack and heap mappings, coherent spans, real entry/state/unwind/signal qualification, and exclusive owner serialization. The named disk enum is a description of an already observed native event; recognizing its value at lines 89-90 cannot observe startup absence or a successful join. These semantics must come from the absent connection, rather than user flags or a synthetic frame.

The initial documentation called the connection the “sole friend allowed to construct.” Header lines 30-31 also friend `NativeReadBoundary` so it can inspect the private entry fields; that friendship also grants constructor access. Root corrected the documentation to identify the intended external issuer and acknowledge the observing boundary's friendship. The final documentation pin above includes that correction. The frozen boundary implementation never constructs an entry and exposes no minting method. A future boundary or connection definition still requires its own review and cannot inherit this disposition merely by using the friend declaration.

The local `reading_` scope rejects synchronous reentry and resets on all ordinary returns. It is not a cross-thread lock; concurrent use would violate the expressly required exclusive handler ownership. The owner-issued nonzero namespace is fixed for the boundary after initial binding, and the monotonically increasing sequence refuses exhaustion before incrementing. Rejected later validations consume their sequence rather than reuse it. These values identify a lexical observation, and supply no request birth, loaded-model authentication, generations or prefix continuity.

## Native reads and bounded copies

Before the first native dereference, lines 86-97 require a recognized event, immutable-token ID limit, finite image-relative constants, finite outer range, and actual supplied stack bounds covering `[outer,outer+0x365a)`. The latter covers the full model at outer `+0x2d58` through its `0x902` copied bytes, along with all stack-resident fields subsequently read. The bounds are safe arithmetic checks under the private mapping contract, not evidence that a stack mapping was actually held.

The initial stack reads bind the saved main return at outer `+0x2678` to image `+0x171ba1f`, aggregate `A=outer+0x2800`, model `M=outer+0x2d58`, connection `outer+0x2968`, and independently retained startup model identity. The retained synchronous main-to-handler path supplies these offsets and completed construction/lifetime provenance. The cache pointer must equal both the aggregate field and main's retained `RSP+0x38` at outer `+0x26b8`, match the separately observed startup cache, and have a finite aligned `0x158` extent before any cache field is read.

Lines 119-137 bind real `R15` to exactly one `0x308` queue record, real `RBP` to its request, the request's model origin to `M`, and record/model slot values. Ordered queue capacity is checked but no capacity storage is followed. The queue-capacity field at outer `+0x180` is outside the later `0x180` outer copy; its direct issuer read is nevertheless within the already held, larger stack range. This distinction is deliberate and not a copy overrun.

The completed-prefill checks read vector descriptors and cursor only; they do not follow a prefill pointer. The scope then declines unsupported phase/sampler/constraint/suppression, transient model head state, nonnull disk/pending holder, unknown progress binding, and any of the five nonempty optional model-hook pairs. These match the source-closed narrow host interval. Equality and nullness check current layout; they do not independently exclude earlier worker activity, nested copy-worker callbacks, new dispatch or concurrent owner release.

The request's PLD vector is required to be nonempty, four-byte aligned, ordered `begin<end<=capacity`, and bounded in both current length and allocation capacity to 262,144 IDs. Ordered unsigned subtraction cannot underflow. The last `min(current_length,512)` IDs produce a suffix of at most 2,048 bytes wholly inside that owned vector; no omitted-prefix scan, hash or native map traversal occurs. Rejecting a larger allocation capacity is a documented conservative restriction even if the current length would fit.

The issuer creates a lexical `NativeReadInterval` with exact host spans `N:0x1f8`, `M:0x902`, `R:0x308`, outer `0x180`, and the bounded suffix. The unchanged capture copies all 6,018 maximum native bytes to preallocated member buffers before decoding. It then validates copied relationships, defined IDs/current tail and native policy/allowance through the existing decoder. No driver, tensor or staging allocation is followed.

Integer-to-pointer reads in this issuer are intentional direct native accesses, unlike the downstream decoder's value-only checks. Finite extents, pointer equality, saved-return matching and sequence values do not make those reads safe when supplied objects are freed, unmapped or concurrently mutated. Their safety remains conditional on the real connection's earlier owner/mapping/exclusion proof covering the whole CALL.

## Unqualified result and remaining connection work

Both observed owner and acknowledgement are explicitly null at implementation lines 182-183. The internal handoff is private and default disabled. The unchanged capture therefore either rejects decoding or publishes `OwnedUnqualified`; it cannot reach `initialize`, `adopt_round`, `consume_at_seam` or proposal admission through this issuer. The implementation writes only its own metadata and preallocated owned storage. There is no native object, register, stack or XSAVE copy-back.

`ReadIssuerObservation` and its nested `OwnedObservation` contain value facts/status only. They expose no native origins, saved register image, span descriptor or capability. `NoHitFacts.window_origin` denotes a logical token origin rather than an address. The source does not publish a qualified full-prefix seed, acknowledgement, proposal packet or native outcome authority.

Before enabling a separate native read entry, the missing connection still must:

1. Retain actual `C/M` from preallocation exit `0x173c3e9`, or failed-init continuation `0x173c3ab` after native teardown/join and holder clear `0x173c3a0`; a later null `C+0xe0` alone is insufficient.
2. Establish successful joins/quiescence for any pre-serving indexed dispatch, exclude new owner/dispatcher threads during the CALL, and admit only the genuine ordinary main/handler path after construction-timer and relevant forward copy-worker completion. Nested progress callbacks are excluded.
3. Provide held coherent host mappings, real register/extended-state preservation, compatible placement and restoration, sufficient stack below the original seam, complete emitted CALL-tree stack usage, and unwind/signal policy.

The issuer's above-outer bound does not prove the entry's below-outer capture or C++ CALL budget. Its roughly 2 KiB returned observation plus capture/decoder call tree cannot use the frozen leaf observer's 256-byte budget. The frozen register-only observer and a saved first register image read after resume cannot supply this connection.

Successful birth, model/tokenizer authentication, reset/slot generations, complete prior prefix acknowledgement and continuity remain separate authorities before any qualified handoff. Native acceptance, readiness, CPU copy cost, GPU/NPU placement, Prefill/Decode and total time per committed token remain unmeasured. This review closes the bounded source issuer under its explicit contract and leaves the actual native-entry/event connection unresolved.
