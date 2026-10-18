# Optional GUFO request-policy source patch

This is a source extension to [pixmaate's GUFO Windows port](https://github.com/pixmaate/gufo),
separate from the llama.cpp patches in the parent directory. It adds the
opt-in `--request-policy ar4k-service-v1`; omitting it preserves GUFO defaults.

The profile permits framed chat/responses/messages with one active request and
one queued request, context 4096, at most 2304 complete rendered input tokens
and 256 requested output tokens. It refuses raw completion, MTP, thinking,
explicit effort, vision, prompt lookup and cache lookup. Invalid requests are
rejected, not silently clipped or stripped. See patched `docs/CLI.md` for the
required companion flags and API restrictions.

All three implementation tasks and the final complete patch passed independent
source review. Four focused native Windows CPU policy tests passed. A separate
GPU-capable build now also compiles the HIP-only adapters, typed loaders and
setters; four non-HIP test binaries from that build passed, including the MTP
sampling and prompt-lookup tests. **This is not a GPU-runtime-qualified server,
persistent launcher or installer.** The separately staged service candidate
subsequently loaded the model, answered the fixed request correctly and exited
code 0. That attempt **failed memory recovery** because available Windows RAM
did not return to 49 GiB; its failure and consumed-attempt records remain.
The old benchmark binary/package are unchanged, and their performance results
do not qualify this service revision. See the [recorded status](../../setup/GUFO.md#finite-service-policy-smoke).

## Reproduce the source

Use a separate clean GUFO checkout at base commit
`cff564964e8506c0abb3e530cecb55332187ac6c`. Do not apply this to a working runtime
or to the preserved evidence checkout. In that separate source checkout:

```powershell
git rev-parse HEAD
git status --short
git apply --check 'C:\Path\To\StrixAlloy\engine-patches\gufo\ar4k-service-v1.patch'
git apply 'C:\Path\To\StrixAlloy\engine-patches\gufo\ar4k-service-v1.patch'
```

Verify the base identity and clean status before applying. Verify the patch's
SHA-256 against [manifest.json](manifest.json). Application intentionally leaves
source modifications in this separate checkout; it does not produce the local
review commit identities. The manifest's reviewed tree identifies the complete
expected source content. Applying the export to an isolated Git index at the
pinned base reproduced that exact tree without modifying the preserved working
files or their normal index.

Rollback: stop using the separate patched checkout. Do not reverse patches or
reset an existing working installation. Keep the original GUFO source/runtime
and the existing Halogen, native Strix Alloy and 27B backends intact.

## Remaining gates

The separate [build entrypoint](../../setup/GUFO.md#build-the-reviewed-source-extension)
has completed a real two-job HIP build and verified reuse on this host. Its
output differs from the already staged candidate and has not been executed
or accepted by the exact-hash runtime policy; build success is not runtime
qualification. [Static staging](../../setup/GUFO.md) supports the original
binary and the explicit `service-ar4k-v1` candidate as separate identities.
It neither compiles the patch nor accepts arbitrary rebuilt binaries.

The installed-profile store, lifecycle monitor, authenticated control channel
and start/print-only/status/stop commands have passed offline tests and
independent review. Real service qualification remains unfinished and public
activation refuses. Offline command tests do not qualify model-backed lifetime,
memory recovery or a production service. Do not clear the failed finite run's
records or replay its consumed profile.

Cache bypass is not zero snapshot retention. One active plus one queued request
does not limit HTTP prompt preparation to two simultaneous callers. Model
asset auto-discovery and lifetime memory accounting remain separate checks.
The request policy alone is not a memory monitor or an allocation guarantee;
do not use this source example to bypass the approved guarded launch process.

The upstream MIT notice is retained in [LICENSE.upstream](LICENSE.upstream).
No model weights, compiled binaries or AMD runtime files are included here.
