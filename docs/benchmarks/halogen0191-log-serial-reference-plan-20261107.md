# Frozen log performance study with a recorded serial reference

This study sends the original Halogen 0.19.1 log request and sampler in every arm. It compares PLD 3,3, then 3,4, then 3,3 in the previously measured single-slot 2048 profile. Each arm has one excluded warmup and three measured requests.

The earlier serial pilot returned 4933 UTF-8 bytes and 1259 generated tokens for 3539 input tokens. It matched all requested log content but omitted the required final LF. The original 4934-byte task oracle and its failed result are preserved.

The new performance reference is the exact recorded 4933-byte serial response. Every compared response must match its bytes and actual generated token count. This criterion measures preservation of the existing serial behavior. The original task-format failure remains a separate result.

Responses are compared byte for byte at the full requested length. Every attempt is retained. The input request, recorded serial response and reference hashes are frozen in the accompanying JSON before candidate execution. Native-head, lookup and grammar counters are reported separately. Positive measured lookup activity in every arm is required before interpreting a lookup mechanism result.

Unadjusted RAW phase rates and complete-request QPC times will be reported separately. Native token-sequence identity requires additional evidence beyond equality of visible bytes and token counts. A useful result would establish a gain for this copied-log workload and profile. General prefill improvement and a beneficial NPU contribution remain open.

This prospective registration precedes candidate execution. The selected normal server will be restored after the finite experiment. [Frozen study parameters](halogen0191-log-serial-reference-plan-20261107.json).
