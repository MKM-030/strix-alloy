# Original BF16 weight-preparation decomposition

This default-off, root-owned screen compares two kernels already present in the
pinned Halogen0.16.2 gfx1151 object. It does not change the user server or compile
a replacement GPU shader. Source and launch bindings are recorded in
[`halogen-next-prefill-mechanism-20261006.md`](../../../docs/research/halogen-next-prefill-mechanism-20261006.md).

The fixed original layer0 QKV matrix has N10240/K2560, mode4/PRE1/KFAST1.
Both kernels launch grid20x80/default stream with zero dynamic shared memory;
W16 uses512 threads and the alternative uses256. The complete prepared BF16 W
is52,428,800bytes. Static arithmetic equivalence is unproved. Different output
poisons ensure common untouched holes cannot pass the full raw-byte oracle.

The native program reads only the original executable/object/runtime and three
immutable captured packed/sign/scale inputs. Two excluded qualification calls
must agree across all26,214,400 output words before any timing. One failure
retires the candidate without a timing cohort. If qualified, it runs exactly
four excluded warmup pairs and sixteen balanced measured pairs. Each arm uses
one launch and a full completion boundary. Every output is checked; there are
no primers, input fitting, tolerance changes, extra shapes or retries.

`image_wrapper.py` binds source, executable, runtime and input hashes inside the
pinned image. `owned_run.py` requires the verified server already stopped,
22GiB physical/commit admission and18GiB continuous reserve. It owns only one
UUID-labelled no-model container and suspended Windows job. The external normal
lifecycle coordinator must preserve current identities, resume confirmed live
handles after observation timeouts, and restore the user instance ready/open
after cleanup. Do not run this worker directly against an active user engine.

The outer lifecycle helpers use the existing server venv launcher and its
`upgrade0162/vendor` plus `venv/Lib/site-packages` import paths. A default Python
or the bare base interpreter does not meet that runtime contract. The fixed
image contains the regular `libamdhip64.so.7` file; no unversioned symlink is
required. Its original hash is checked before native execution. The small
host-only `test_image_wrapper.py` regression checks that package layout without
loading HIP or interrupting the server.

GPU offers the concrete native decomposition change. CPU owns submission,
metadata and checking; no faster CPU replacement is qualified. The NPU lacks
an exact compatible prepared-W consumer and a useful GPU publication route;
no NPU work is included. This preparation-only screen cannot establish Prefill,
Decode or native acceptance gains. A useful exact result is a prerequisite to
a complete preparation-plus-unchanged-GEMM comparison, then a frozen serving
comparison. Failed or defeated candidates remain disabled.

The existing validator does not yet admit `HALOGEN_HT_DEQ_W16`; the module
oracle does not require a production validator change. If qualified for a
serving experiment, admit only explicit0/1 values and retain absent/default1.
KFAST/PRE and the normal user profile remain unchanged.
