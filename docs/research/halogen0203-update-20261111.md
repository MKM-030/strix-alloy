# Halogen 0.20.3 — installed and online, 11 November 2026

**0.20.3 is installed and left online.** API and engine both report 0.20.3,
with version agreement. Authenticated chat returned HTTP 200 and **`READY`**
at **16:04:57 UTC** on 11 November using the existing endpoint
`http://127.0.0.1:8840/v1` and public model alias `halogen-v2`. The initial
normal lifecycle completed successfully and retained the running server.
The Windows PowerShell 5.1 launcher remains active, with a verified visible
window titled `STRIX ALLOY - Halogen 0.20.3`. The ServiceNow credential remains
unchanged.

[Machine-readable installation and runtime evidence](halogen0203-update-20261111.json).

The user's update request was checked again at **17:47 UTC**: official main and
the release metadata still identify **0.20.3**, matching the running container,
API and engine. A fresh authenticated chat returned HTTP 200 and `READY`, with
zero reasoning tokens. The normal instance and existing credential were
preserved. The current restored launcher/controller still share a console, and
a visible terminal window matches its automatic title. The window check uses
title matching rather than an explicit Windows Terminal tab identity. This functional
check is not a throughput benchmark. [Recheck evidence](halogen0203-online-recheck-20261111.json).

## What the release changes

The manufacturer reports **7–9% faster `d3-nano` decisions on the NPU**, with
less energy use. This is the separate NPU classifier, not the Flash language
model's MTP decode path. Scores may differ in their final digits; the publisher
reports unchanged accuracy in its checks. **Everything else is unchanged from
0.20.2.** No new Flash prefill, decode or MTP-acceptance improvement is claimed
by these release notes.

[Pinned official changelog](https://github.com/peonist-ai/halogen-flash-server/blob/631d0b1c3091b60478ed4c461152bc700febb177/CHANGELOG.md),
[release commit](https://github.com/peonist-ai/halogen-flash-server/commit/631d0b1c3091b60478ed4c461152bc700febb177).

## Published identities

| Item | Verified published identity |
| --- | --- |
| Release | `v0.20.3` |
| Public tag target | `631d0b1c3091b60478ed4c461152bc700febb177` |
| Annotated tag object | `18be88c7a59a6dfb2dda745bd34a85bde34e5208` |
| Manifest digest | `sha256:be5624fe83c1cecb1f4a025bf169988103044263224c1bfcb4ce54697f98ce69` |
| Raw OCI config digest | `sha256:25c1924ef3ec07cc03fee754906626455baf3b6acf4bd72da29543ef6e1ee7a6` |
| Installed Flash executable SHA-256 | `bf84053705d1e89c214ff64c79ad1276c5fe353d80a9bb0f38ef3bac6645b97c` |
| Image config version label | `0.20.3` |
| Image config revision label | `54a488ef3224` |
| Platform | Linux / amd64 |

The manifest and config bytes were read and independently hashed without
downloading image layers in the source-review task. The public tag target and
the image's revision label are recorded separately; they are not interchangeable.
The tagger timestamp is **14:07:48 UTC** and the commit timestamp is
**14:01:38 UTC** on 11 November. The config's **12:47:07 UTC** creation value
is a build timestamp. An exact registry-publication timestamp was not exposed;
none of those timestamps is treated as its substitute.

[Official published package](https://github.com/peonist-ai/halogen-flash-server/pkgs/container/halogen-flash-server/1543581228?tag=0.20.3).

A Docker/Podman runtime image ID can differ from the raw OCI config digest.
Local preparation therefore binds a private container to the actual image ID
in its fresh extraction receipt and verifies the raw config separately against
the copied image-inspect values. A published digest alone does not prove that
the corresponding engine or adapter is installed or running.

## Installation and serving checks

The version-specific staging, source preparation and CPU provider inspection
helpers are prepared. The provider helper passed **18 CPU-only tests** and an
independent source review, including separate manifest/runtime/config identities,
the dynamically pinned preservation helper, controlled-stop preservation,
retained failure evidence and unchanged memory reserves. These tests use fake
commands and host snapshots; they establish no actual provider-load, model,
hardware or throughput result.

The actual passive image extraction, CPU provider inspection, adapter build and
local installation completed at **15:49:30 UTC**, with **47 source files**
verified. The installed source manifest is
`c32138235c3847dfe29576d9ed634e4686f2ddc203ac718395444b7784804492`.
The installation receipt has SHA-256
`68e6089068b5bf4683fa9dd565cf115b67b8121fdfcb07ceccad956b9490d81b`.
Existing model identities matched their complete integrity receipts; no model
was downloaded or rehashed for the installation.

The Windows PowerShell 5.1 launcher now selects installed 0.20.3 by default.
Its two portable test suites passed **5 and 17 tests**. The canonical managed
integration passed **15 tests**, and the separate source review passed **10 CPU
tests**. The backend portable suite recorded **19 passes and 8 skips**; those
skips remain explicit. These are integration checks, not performance measurements.

The normal lifecycle waited for and passed the unchanged **30 GiB physical /
131 GiB commit** startup admission. The **18 GiB physical/commit runtime
reserve** remains unchanged. Read-only inspection of the actual running engine
matched its executable, loaded HIP/crypto/C++ providers and both loaded adapters.
The Flash executable and API are byte-identical to 0.20.2; this agrees with the
release's unchanged Flash scope. Experimental hooks are not loaded.

Normal serving retains **32,768 context/pool positions, one slot, both prefill
controls at 8,192, MTP gate 0.90 and PLD `3,3`**. Cache, Thinking, Vision and
decode prefetch are off. Console request/response tracing is enabled. The
existing public credential, port 8840 and model alias are preserved, and the
server remains ready and online.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -ConsoleTrace
```

Use that command after stopping an existing managed session through its normal
controls when a new session is needed. The server is already running.

A separate private 0.20.3 RAW/NPU integration was subsequently rebound to the
verified executable/API identities and freshly built consumer/observer products.
Its [actual partial attempt](../benchmarks/halogen0203-real-npu-core-append-20261111.md)
did not reach NPU execution. Normal serving was restored with experimental hooks
disabled; the private preparation does not establish a live speed gain.

## Performance status

There are **no qualified new 0.20.3 prefill, decode or acceptance measurements**
in this update record. The authenticated functional request used **17 actual
input and 2 output tokens** and returned `READY`. It establishes serving only;
its response timings and single draft acceptance are not benchmark values.

The [completed 0.20.2 API observation series](../benchmarks/halogen0202-normal8192-20261111.md)
retains its excluded warmup, three measured requests per input, clock limitations
and exact workload identities. Those figures remain 0.20.2 observations. The
[earlier installation record](halogen0202-update-20261111.md) and
[partial 0.20.2 real-NPU attempt](../benchmarks/halogen0202-real-npu-core-append-20261111.md)
retain their own outcomes. No historical value or component duration is
relabelled as a 0.20.3 result or a measured NPU engine-speed gain.

## Subsequent private attempt: no qualified NPU measurement

The [independently checked terminal report](../benchmarks/halogen0203-real-npu-core-append-20261111.md)
and [numeric evidence](../benchmarks/halogen0203-real-npu-core-append-20261111.json)
record **one excluded stock warmup, zero measured requests and no NPU producer
start**. The successful entry checks occurred before that warmup. The following
120-second wait before the first measured request retained **470 samples with
zero eligible frames**: physical reserve ranged from **21.492 to 21.722 GiB**,
below the unchanged **22 GiB** entry requirement. This is an admission failure,
not a measured NPU slowdown or a token-rate result.

The coordinator exited and normal 0.20.3 serving was verified ready on port 8840
at **16:39:02 UTC**, with all **47 normal source hashes restored**. The complete
export was reconstructed independently, including the excluded warmup's raw
journal, native token IDs and whole-request clock evidence; seven offline tests
passed. No warmup value is promoted to a benchmark headline, and the unchanged
cohort is not repeated.

The wider prefill/decode acceleration goal remains unachieved.
