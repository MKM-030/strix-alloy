# Smallest remaining concrete callback connection

The next small implementation is one ordinary noexcept helper adapter between
the real four-miss relay's `hgn01816_relay::Helper` ABI and the already joined
`hgn01816_bridge_on_native` dispatcher in
`current-pld-native-attachment-v4/dispatch.h`. The copied architectural island
and the owner/consumer dispatcher exist separately; their frame representations
are not connected. This adapter is actual plumbing, not another gate suite.

It should perform only these synchronous operations:

1. Zero the relay's scratch `Outcome.count` before any decline, preserve errno,
   and accept only the four frozen miss-site RVAs.
2. Copy the actual const pushed `relay::Frame` into the dispatcher's
   `SavedNative`: map all15 explicit GPR fields to `Registers` enum indices,
   set `Registers[Rsp]` from the actual relay-supplied original RSP, and copy
   the original saved RFLAGS. Never cast one frame layout to the other.
3. Call `hgn01816_bridge_on_native(site,&saved,nullptr,&offer)` exactly once.
   The local Offer lives below the native frame and is not a writable pointer
   into native IDs. Do not pass native stack storage as Offer output.
4. Only if the real dispatcher returns `Result::Offered`, count is1..3 and
   resume is exactly `kNativeFilters`, copy the owned IDs/count into the local
   relay Outcome. All other results leave count0. Restore errno and return.

The adapter must not write native IDs/RBP, call the verifier itself, perform
Torch inference, read asynchronous native pointers or fabricate a Frontier.
The existing architectural relay alone applies its permitted native edits
after restoring xstate. A CET-compatible helper entry and measured aggregate
compiled stack budget are part of that actual connection.

A finite CPU check can invoke this adapter through the already-real copied
island and existing dispatcher fixture using its real Linux socket/owner
sequence. Existing stale/cancel/reuse semantics need not be duplicated in
another modeled validator. The useful new assertion is that a genuine joined
dispatcher Offer reaches the actual relay Outcome, and a decline preserves the
native bytes through that actual call chain.

This helper connection does not supply the other still-uninstalled phase,
initial constructor and verifier/commit/history callbacks. The existing Bridge
must receive those genuine boundaries to become ready. Consequently an
observation-only attachment should continue returning count0 until that native
coverage, owned feature publication, completion and trained producer are
connected. Startup image/Jcc binding, headroom/CET domain and transactional
branch publication remain Root's separate installer work. No additional live
permission, native authority or performance claim follows from this note.
