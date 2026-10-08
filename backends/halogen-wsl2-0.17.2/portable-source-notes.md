# Halogen 0.17.2 source and installation evidence

The package derives from the sealed 0.17.1 sources, with 0.17.2 runtime identities and an independently reviewed exact preflight rebinding. The reviewed engine pin is `ac73b1df48510a34e0246a77bd984f1df0e02e5fa6cf1530d3d77c91d3c0e913`; its bridge site is RVA `0x18964d0`, file offset `0x18954d0`. Source-only generation reproduced the five reviewed patch-source pins. The sealed bounded static-audit receipt has SHA-256 `41aaf149774ab1bd173d41cb31a1a736dd69d733de8683a9189fc808653e6778`.

The runtime image revision `8351ef2dc12d` and inspected public documentation commit `3bd33c6f6c203e429282239e69d04147016c59db` have separate provenance roles. The exact reviewed sources are sealed by [sources.json](profiles/sources.json); runtime and artifact identities are recorded in [release.json](profiles/release.json).

Normal `portable.py install --install` completed with exit code 0. The canonical install manifest records version 0.17.2 and `completed: true`. These four installed artifacts were hashed read-only and matched the release pins and CPU-build receipt:

| Artifact | SHA-256 |
| --- | --- |
| `libhalogen0172-preflight.so` | `07265c9a7ce86ea17dd24e8c82d5d893dbb5f152690351d221b5ce07f00644ef` |
| `libhalogen0172-v2-preflight.so` | `d061e7c2ff1cb5052b695658d7844fd791f2652e20a7a07173969fedb8dcbb95` |
| `hip-register-private-rw.so` | `815b677ad7e4a2708ed8390222b41ba93ca38bd400064d2b946ff2ae495611fa` |
| `halogen0172_hip_probe` | `e721fd39ae88bd08be040ca8278e9689087ffabb1797c652c03027c1f87194f6` |

Preparation evidence is retained under `server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008`: `static-compatibility-audit/static-audit-final-receipt.json`, `cpu-build/receipt.json`, `normal-install.json` and `api-lifecycle-audit/root-integration-review.md`.

The raw upstream entrypoint is byte-identical to 0.17.1. The API adds draft shortlist counters while the reviewed request options, timing/acceptance reconstruction, health and version functions are unchanged. This source finding does not establish unchanged engine behavior.

The normal launcher preserves explicit MTP depth 2, PLD `3,3`, context 262144, one slot, paired 8192 prefill limits and cache Off for the frozen comparison. V2 admission is 35 GiB physical / 131 GiB commit at this context; the independent service guard retains the 18/18 GiB runtime floor. Installation does not download models or edit drivers or global WSL settings.

The [fixed-depth-2 runtime comparison report](../../docs/benchmarks/halogen0172-fixed-depth2-20261008.md) records runtime results separately. The static audit, successful compilation and completed installation do not establish global adapter runtime qualification, a speed gain or NPU acceleration.
