# Stock wrapper reconstruction — 2026-10-04

The earlier and current tracked wrappers produce identical native launch and
request paths for the retained stock profile. This source-only reconstruction
found no wrapper change that explains the real prefill decline from 1731.31 to
1605.07 tok/s. The earlier ignored outer runner bytes are unavailable; thermal,
competing-load and cache causes remain unproven.

The old service source at `b77a3bd` and current version at `1c5e198` were
evaluated using only their selected pure manifest-building functions. Both
reproduced their corresponding retained manifests exactly. Regenerating each
entrypoint also reproduced its retained bytes exactly. Comparing container
arguments normalized only run identity and its `/services/<id>` directory.
The PowerShell argument prefix stopped before command discovery or any Python
launch. No engine, process controller, provider or device was started.

| Reconstructed old/current payload | Elements | Identical SHA256 |
|---|---:|---|
| Controller to PowerShell arguments | 10 | `742b2dbe7f8f2fb91a1da9cbcd36f10c00fa83a2993138ede393e6ffd89854fc` |
| PowerShell to Python arguments | 13 | `27113688a580e2c8d9a47f7dcbd3613edc0109edc78d40b9d10177ec2454a3fd` |
| Service to native container arguments | 116 | `9a88498f6a14706176844063a7e954ee0f66b8bd514e7eeeb3f00240ead263d8` |
| Generated entrypoint bytes | — | `f3ee2640146141aa87b0455e01384c93a1c41fcfa256a9d30ba04105b46564b0` |

Argument hashes use compact JSON arrays. The native environment, entrypoint
transformation and container command functions have identical ASTs, as do
`controller.run` and the service ready-to-serving block. The latter AST hash is
`91cedf151b06262b4dc3cacd5516e77ddb0f6134df4540c908e4d5a0aecce556`.
Request forwarding and the entire `server/gateway.py` are byte-identical,
SHA256 `3b4443b8d103dd0aad77061c04cac031abf75f3224a65f64b1e9fa0a5d834b95`.
New optional imports, sealing and revalidation of `None` support receipts occur
before ready. No changed measured request path was found.

Source locations in the reviewed current versions are controller argument
construction line247, backend `Start.ps1` line33, backend `scripts/service.py`
environment line195, entrypoint line232, container command line279 and
ready-to-serving line593; gateway forwarding is line146. Corresponding old
controller/PowerShell locations are `b77a3bd:206` and `b77a3bd:30`, with the old
ready-to-serving block at lines545–563.

No rollback A/B recipe was prepared because there is no identified differing
tracked execution path to isolate. This excludes changed native flags,
entrypoint or forwarding as a direct tracked-wrapper explanation; it does not
establish the actual cause of the prefill drift. See the
[retained stock comparison](halogen-dn-fused-pair-negative-20261004.md) for
cohorts, wall-clock evidence, clock corrections and artifact identities.
