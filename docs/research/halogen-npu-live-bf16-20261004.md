# Real live-route BF16 NPU candidate — 4 October 2026

This new approximate candidate uses two actual captured MTP routes. It keeps
the earlier failed lossless BF16 qualification unchanged. It is a routed-expert
graph, not complete MLP, full NPU MTP, or a measured acceptance improvement.
CPU export/replay completed. The subsequent guarded NPU attempt failed strict
provider admission and executed zero NPU calls.

The [probe](../../scripts/benchmarks/halogen_npu_v2_live_bf16_gather_probe.py)
selects the first two distinct ordered routes, calls 0 and 1, from the
[live capture](halogen-mtp-routing-live-20261004.md). Their union contains
16 experts. It decodes only those experts, rounds weights to BF16 nearest/even,
and stores 150 MiB in two external constant tensors. Two runtime Gathers and
two Casts precede the previously frozen eight expert operators. Runtime input
contains 10,360 bytes: the exactly widened captured BF16 input, host-derived
bank indices, and the original ordered FP32 coefficients. No weight tensor is
fed per call. Compiler prepacking and internal NPU placement are unproven.

## CPU qualification

All twelve replay calls pass the strict independent BF16-weight graph reference
and the separately declared original-FP32 approximation contract. Four warmups
are excluded from the eight measured calls. Original strict mismatches remain
visible; approximation does not establish parity with the complete native MLP.

| Reference contract | Route A maximum absolute error | Route B maximum absolute error | Result |
| --- | ---: | ---: | --- |
| Independent BF16-rounded weights, rtol 3e-5 / atol 3e-6 | 8.94e-7 | 1.85e-6 | Pass |
| Original FP32 weights, rtol .03 / atol .003 | .00266546 | .00330877 | Pass |
| Original FP32 weights, strict CPU contract | .00266546 | .00330877 | 2515 / 2535 element violations |

Mean CPU host/run time is 17.709825 / 17.6996 ms with one BLAS/OpenMP thread.
All 132 profiled Node events use CPUExecutionProvider. CPU private-memory
increase peaks at 510,889,984 bytes; minimum physical/commit headroom is
43.629 / 197.927 GiB. These are subgraph timings, not GPU or end-to-end rates.

Frozen artifacts are under
`C:\AI\halogen-mtp-npu\v2-live-bf16-gather-offline-20261004`.

| Artifact | SHA-256 |
| --- | --- |
| Probe source | `6d665ec8d88df6cc177c8c0747329714183825ed80f23e87a347701d91d9d53d` |
| 1798-byte ONNX | `fc238448ba77fcc63cf109e762ecf0c9361cb9b028bb756feafa71741eaf66ff` |
| 157,286,400-byte external data | `bf47a0989cbbb038d57c7daf22bfb06b887e5c6052e4cdaa6d5c584e8777b8fa` |
| Build receipt | `28bc4f16814efb0b4007937e4bde429a6d2eb6320745935362d427bdf57d9d21` |
| CPU receipt | `f2942413a0f9f78ec1f13b8f9fb84c0bd83f531af9f3103921cec43b0818d9f1` |
| CPU profile | `e6e7910a4919350ab78dba68c5318e1081974ff028696ec55348b77eaf027325` |

The old FP32 bank and old exact-conversion rejection remain separate evidence.
NPU replay requires strict provider attribution and disabled CPU fallback in a
root-owned bounded hardware window. A successful NPU run would still need a
live GPU comparator, complete MLP, persistent state, and acceptance measurement.

## Missing dense MLP pieces

The new [dense reader](../../scripts/benchmarks/halogen_npu_v2_dense_mlp.py)
exports the real v2 BF16 router and q8g64 shared gate/up/down weights, plus the
q4c scalar shared gate. Its decoded arrays total 24,913,920 bytes. The native
checkpoint identity and the pinned header/table match before and after bounded
reads. This is CPU weight preparation, not NPU execution.

An FP32 router reference using the 73 captured BF16 MLP inputs reproduces 72
expert sets and 69 exact rank orders. The matching-set coefficient maximum
absolute difference is .00044992566. Call 1 chooses expert 66 at the tenth
position while native chooses 372; the reference boundary margin is .00089908.
The native path can use a separately prepared FP32 router input. The BF16
expert input therefore does not universally reproduce native routing.

Dense artifacts are under `C:\AI\halogen-mtp-npu\v2-dense-mlp-20261004`.
The NPZ SHA-256 is
`e1103b576f60a5fbaf1059abd26b37d4bdf967c091f79fc80a8cee0bcae441f3`;
the dense source SHA-256 is
`507ec5dd339038a06876b974ccfd0494d4caf463574f9a03dc43a5afc15c3202`.
The saved shared outputs allow a complete-MLP comparison without decoding
the expert weights again. No native output parity or acceptance claim follows
from the routed graph's approximation gate.

The completed two-call comparison adds the saved original-FP32 routed and
shared outputs and compares them with the captured complete BF16 MLP output.
It fails the strict contract for 2543 / 2541 elements and the existing
approximation contract for 2 / 1 elements. Maximum absolute error is
.00837874 / .00879204; relative L2 error is .00332363 / .00328232. Rounding
only the final output to BF16 still leaves 1453 / 1432 BF16 bit mismatches and
does not remove the approximation failures. Cancellation between routed and
shared contributions occurs at the three failing elements. The complete output
does not isolate which component or native intermediate rounding caused them.

This comparison starts no session and decodes no weights again. Receipt
`C:\AI\halogen-mtp-npu\v2-complete-mlp-comparison-20261004\complete-mlp-comparison.json`
has SHA-256 `0c17413c30269ccfd103feabaf4787af3bb062c399da91281caf3084d5123f40`;
its source has SHA-256
`5aa791235fc51e4f832db39dd3127109912fe16edcab7ff1457437e87995e20c`.
The dense q8g64 reader's layout matches the existing canonical decoder;
no material layout issue was found. A complete-MLP replacement remains
unqualified, even if the routed NPU subgraph passes its own gate.

## Guarded NPU outcome

Root rebuilt the same pinned ONNX and BF16 external data in a separate guarded
directory, then ran sequential CPU and NPU stages. The CPU stage passed.
The NPU provider compiled part of the model but ORT refused session creation:
some graph nodes were assigned to the CPU while CPU fallback was explicitly
disabled. There are zero replay calls and no qualified NPU latency. Compiler
messages alone do not establish which internal operator configuration failed.

No guard error occurred. All three owned jobs closed with terminal exit codes;
provider unregister, DLL-directory close and bootstrap shutdown completed.
Minimum physical/commit headroom was 43.77837 / 198.14746 GiB. The final GPU
state was terminal/idle. The new ignored guard source SHA-256 is
`6348794c27a4aad772c9fb5842d506f7d18b83dddba3157ead6bdbff789de6cd`.

Artifacts are retained under
`C:\AI\halogen-mtp-npu\v2-live-bf16-gather-guarded-20261004`.

| Guarded artifact | SHA-256 |
| --- | --- |
| Failed NPU receipt | `f6d3ec3ba925e978cf665cbeca32cd1321865d4075b12aa323614e57079557ab` |
| Guard result | `9ffcaaab46f0ab4353ff3c5e41a13bc2c40a18f74c01b393ca060425ee8282bb` |
| Cleanup receipt | `0660a9738ec51fb76cd72b5d6be4054c44be6e4d20c8926e835533c5e0165898` |

This rules out promoting this exact graph with the installed verified provider.
It does not assert that all BF16 Gather configurations are unsupported. The
original failed FP32-bank attempt and lossless-conversion gate remain unchanged.
