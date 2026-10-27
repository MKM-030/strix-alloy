# Halogen 0.18.15 deferred Z experiment

**Implemented and CPU tested; no GPU correctness or speed result yet. Default
off.** This adapter is specific to engine SHA256
`ce1c375eb2d92a4c7b2b0e1d969acd865bb72bb248c52498eedb170cbaea8a89`.
It preserves the original native BF16 projection, weights, convolution and
recurrence kernels. The scheduling idea comes from the independently reviewed
[Gufo overlap work](https://github.com/gufo-org/gufo/pull/758); Gufo FP16 kernels
are not substituted for Halogen kernels.

The admitted operation is the existing separate Z projection for 8,192 rows.
It runs after the original alpha/beta projections on a private nonblocking
stream. Original convolution or gate work can run on main only after exact
function, argument, geometry, allocation and alias checks. Every unknown
operation joins before forwarding. Native prefetch must be explicitly off;
the engine's prefetch stream and event are never borrowed.

The ordinary fresh-prefill route uses the original TB2 convolution with grid
`{10,512,1}` and block `{256,1,1}`. Its history is a bounded 60-KiB view within
the native arena. Treating the entire arena as the accessed history would
incorrectly report an alias with Z and produce zero overlap. The CPU fixture
covers this shared-arena case, adjacency, one-byte overlap, actual Z aliases and
incorrect geometry.

One private stream and three events are owned per eligible DN invocation. All
creation, synchronization, redirection, validation and destruction costs belong
to actual elapsed time. No component milliseconds are converted to token rates.
Shapes outside this experiment must retain stock behavior.

Decode and other ineligible DN calls use a stock passthrough before any
Run/Trace initialization, observer installation or HIP binding. The existing
process mutex still protects shared FC workspace; a same-thread owner token
allows native FC calls without taking that mutex again. Both ownership tokens
reset on normal return and exceptions. The eligible candidate's larger stack
frame is isolated in a separate non-inlined helper.

For each new exact tuple, a cold stock operation precedes an observed stock
reference. The side-stream operation must match its native launch closure and
all 96 MiB of Z output before the tuple is remembered. This requires two bounded
96-MiB host buffers during validation. Validation is excluded from steady-state
benchmark rates and is reported separately. It does **not** qualify complete DN
state, final model quality, or a throughput gain.

## Build and CPU checks

From `deferred-z-installer` in the existing Linux toolchain:

```sh
sh build-linux.sh
```

This builds the DSO and runs three CPU fixtures with warnings treated as errors.
It does not invoke the engine, load model weights or submit GPU work. The stream
ownership and interposer fixtures also build with the existing MSVC toolchain;
`cpu-stubs/dlfcn.h` is a test-only include and must never enter a Linux build.

Root independently built the final Linux DSO, ran the three fixtures, and checked
default-off loading, inherited helper passthrough and rejection of a fake engine.
The reviewed installer source SHA256 is
`0b0d5d46b2935192371ebd4d48197005f2ecf4f1bfa599da303f0806311fd913`.
The corresponding Linux DSO is 1,460,128 bytes, SHA256
`60365174dc91b2f94b12094b93b535865624cf75b6a8a0a7bdc93b2ee567ee09`.
The three Linux fixtures include stock decode, same-thread FC forwarding,
mutex ownership, exception cleanup and reuse. This package's `source-pins.json`
seals every copied source and fixture; raw build/test receipts remain in the
private continuation directory. CPU success does not establish device parity
or performance.

## Serving integration and next measurement

The normal 0.18.15 lifecycle has a bounded opt-in control
`HALOGEN_DEFERRED_Z=1`, requiring `HALOGEN_DECODE_PREFETCH=0`. Its helper verifies
the exact locally built DSO before prepending it to the unchanged bridge/private
preload stack and binding it read-only at a fixed path. Omission or zero adds
no preload or mount. Existing source seals and memory admission remain enforced.
The normal serving profile does not enable this experiment.

The device qualification must compare actual Z bytes, complete affected native
state/output and total cost. Only a successful component result permits the
fixed request control/candidate/control comparison. Use identical requests,
one excluded warmup and three measured repetitions per case, no cache reuse,
unchanged sampling, actual token counts, output hashes and separate native draft
counters. Retain independent whole-request timing; native phase clocks remain
unqualified until separately checked. A failed batch or a warmup is not a post
result. Restore the fastest qualified normal configuration and leave it online.

The separate 4,096-token chunk/arena candidate is an independent experiment.
Do not bundle it with this scheduling change or merge historical phase peaks.
