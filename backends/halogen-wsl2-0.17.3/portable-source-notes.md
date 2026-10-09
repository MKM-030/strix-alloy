# Halogen 0.17.3 source migration

This separate package derives from the existing 0.17.2 backend. The old backend is unchanged. Image revision d1e50853b278 and digest3bca0132db3c859c997d52d148e6ea4b7b497b8a695c5ccab97135193fde592a supply the current upstream sources.

The preflight site is RVA0x1898d20/file0x1897d20; the complete22-byte signature and stack slots remain unchanged. Eight direct preflight functions totaling7573bytes have identical normalized instructions and referenced object identities. The entire17765424-byte native GPU object is byte-identical to0.17.2. The entrypoint preflight body and API default/adaptation seams remain compatible. The new entrypoint environment filtering and matching API/tool modules are preserved.

All version identities, process names, profile names and mounted probe/library paths are scoped to0173. Host bridge SHA/RVA, source generator function range/hash, entrypoint and API pins are rebound. Planner limits, memory admission budgets, model choices, numerical controls and trampoline instructions retain the existing implementation.

The initial source migration left the four compiled-artifact pins pending. Root subsequently completed the 0.17.3 CPU builds using the existing portable.py compile commands and populated the current [release pins](profiles/release.json):

| Root-built artifact | SHA256 |
| --- | --- |
| libhalogen0173-preflight.so | `0a2eabefd3d44dafba1532320cfeddaaad5f7213ae51509f9db36908cf280b28` |
| libhalogen0173-v2-preflight.so | `a7a33b2ba57b90df6566d5e035106e2ab3e63b49586c671179c3b087b6142f46` |
| hip-register-private-rw.so | `d20e6d86eb0c5796a8f9b99f06d619637381afdbeca44c8375c407349010ffd0` |
| halogen0173_hip_probe | `5c9b242f8306fcb8177205d1e9ed5a87df20f4ff2e02a9377e4e08c9d4637be9` |

These pins identify the newly built 0.17.3 artifacts; no old compiled-artifact hash is represented as a new build. The generated adapted entrypoint hash is exact. The inherited HIP header and stock rocroller pins remain checked by ordinary extraction; no new admission condition was added.

Source audit and generated entrypoint artifacts are retained under server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/halogen0173-compatibility-20261009. The initial source-audit scope performed no native build, model run, lifecycle, STATE or controller edit. Root later verified normal managed 0.17.3 startup, authenticated readiness and ordinary API requests, and completed the candidate process's normal stop with cleanup and memory recovery confirmed. Those later root-owned checks are separate from the preserved initial migration artifacts. They establish the observed build/start/lifecycle behavior; they do not establish BN64 activation, a serving gain, production qualification or completion of the broader goal. Runtime qualification flags and their final disposition remain root-owned.
