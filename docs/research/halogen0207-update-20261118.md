# Halogen 0.20.7 update and runtime qualification - 18 November 2026

**Halogen 0.20.7 is installed and qualified for the managed one-slot 32K text profile.** API and engine both report 0.20.7, the new `r2-ht4` head and automatic concurrency mode were selected, both corrected WSL/DXG preflight phases completed, and an authenticated request returned exactly `HALOGEN_0207_FINAL_READY`. The instance remains online on `127.0.0.1:8840`. The machine-readable record is [halogen0207-update-20261118.json](halogen0207-update-20261118.json).

| Evidence gate | State |
|---|---|
| Official tag, public commit and OCI identity | Pinned |
| Passive never-started capture and static seam audit | Complete |
| Four CPU products and installed package | Bound |
| Managed one-slot 32K text start | Qualified |
| Authenticated model discovery and functional request | Qualified |
| Loaded provider identities | Unqualified |
| Capacity opt-in, two slots and vision | Unqualified |
| Local 0.20.7 performance benchmark | Not measured |

## Official identity and upstream changes

The official `v0.20.7` tag object is [`b7c4c928f2dc908be37193cf9836d9ba18a51025`](https://api.github.com/repos/peonist-ai/halogen-flash-server/git/tags/b7c4c928f2dc908be37193cf9836d9ba18a51025), pointing to public commit [`dea807d22a638c67553abea876344a8192054a94`](https://github.com/peonist-ai/halogen-flash-server/commit/dea807d22a638c67553abea876344a8192054a94).

- OCI image: `ghcr.io/peonist-ai/halogen-flash-server@sha256:773073448dc9ff4a8c6b6c278802e254fd5f1546764e27531aeb3b77cb13482e`.
- Engine: 43,105,992 bytes, SHA-256 `523804e4aab8a6203f277fe3632663f91c0aa008bdb187413b6ef4f139415640`.
- Upstream entrypoint: 102,803 bytes, SHA-256 `71bfab8eaaea0bc10c9e5e8010af8ed8e537cbca7f61ddae7fc4a32f422a75d9`.
- API: 346,839 bytes, SHA-256 `71240612de5013fa49780de9243adbf60516afe81729f73aa67f98f9fde75c9f`.
- Image platform: Linux amd64, ROCm 10.1.0, Python 3.12.15.

The pinned upstream changelog says 0.20.7 makes the compatible concurrency path the v2 default, prefers `qwen38-flash-next-drafter-r2-ht4.hgn`, and improves single-request decode by about 4-6% relative to 0.20.6. Those speed figures are upstream claims. This update verifies path selection and functionality but does not present a local throughput benchmark.

## Bridge correction

The new 54-tensor HT4 file is 1,488,276,864 bytes with SHA-256 `f9aa330800cc921fe20f4cf997d660f519c67b0052af0c8078b6b648972b07e6`. A fail-closed diagnostic start showed that its registered payload begins at byte 8,192, rather than byte 4,096 used by the earlier r2 layout. The final plan is:

| Phase | Registered range | Registered bytes | Cumulative copied bytes |
|---|---:|---:|---:|
| Shortened v2 main | `319488:65164120064` | 65,163,800,576 | 65,163,800,576 |
| External r2 HT4 | `8192:1488276864` | 1,488,268,672 | 66,652,069,248 |

The final live log contains exactly one completion for each phase with `host=0`, and no preflight rejection. The bridge binds the canonical file path, size, mapping identity and exact range before device registration. It remains fail-closed for different engine bytes, instruction bytes, phase order, mapping generation or aggregate size.

Final bridge artifacts:

- Hybrid source: `4be0d14bcf8fe0a88c18edb50e9111da1852b2db24182ede32451a1e5c8cef64`.
- V2 bridge: 35,400 bytes, `cf20533b1d92df9499b132c27a7a7c638093bb4802c0992822c5068772f17b18`.
- Non-V2 bridge: 30,904 bytes, `f99df4ddf51bff18d8e1f371bacbc2c688f9f63f714be55ffca4195798eee2c3`.
- Private bridge: 16,848 bytes, `d3994249e6034812c9cb6f103355c0479324e4259f9a47c08e2a9429b1d90b60`.
- HIP probe: 16,376 bytes, `78dbb43e45cd96d4e4098d0d602bf09f1db8e3972482a064255ee1429816a5cb`.
- Final GCC build receipt: `server/.local/halogen-update-20261118/primary0207/final-build-v1/build.json`, SHA-256 `6aeadfc91ac2016311fd5e4a2c953b22e93a0e4dea898e02e82a6c37ce859da7`.

The static seam audit still has a finite scope: it proves the pinned FDE, patch site, frame contract and encoded direct-transfer checks. It does not prove every indirect control-flow target or the identity of every provider loaded later by the engine.

## Qualified runtime

The normal profile used v2, text only, one slot, context/slot/KV pool 32,768, paired 8,192 prefill controls, Cache Off, PLD `3,3`, MTP gate `0.90`, Thinking Off and Vision Off. `HALOGEN_CONC_MODE` remained unset so the 0.20.7 entrypoint selected its automatic mode.

| Field | Qualified value |
|---|---|
| Gateway | Run `14b6e48fdfa84b98a424c6cec98b5aef`, PID 41740, `127.0.0.1:8840` |
| Backend | Run `89a648ff47e94dfb8324f171280f55f7`, PID 25196, `127.0.0.1:8731` |
| Container | `282944de6e3cec107a863bc14b62c6fd24e90e42081d32afaaabc9110250304d` |
| API / engine | 0.20.7 / 0.20.7, match |
| Public alias / engine model | `halogen-v2` / `halogen-qwen3.8-flash-next` |
| Drafting | MTP default, HT4 weights loaded, automatic concurrency selected |
| Functional request | `HALOGEN_0207_FINAL_READY`, `finish_reason=stop`, zero reasoning tokens |
| Minimum observed reserve | 20.172 GiB physical / 112.425 GiB commit headroom |

The runtime qualification receipt is `server/.local/halogen-update-20261118/primary0207/runtime-qualification-v2.json`, 7,309 bytes, SHA-256 `48ab390cad454f804cfb644314a2e668bc44130f408eaefdb306b9003b77504c`. The final authenticated smoke receipt is `server/.local/halogen-update-20261118/primary0207/final-auth-smoke-v2.json`, 2,539 bytes, SHA-256 `a52c19bca78f1f330217040a2dacf29556c066f1583089eec00a35220f9c5642`.

The installed manifest contains 161 members, is 18,211 bytes, and hashes to `2e899618d131931eec7033201f4851b62473200c13fb011c0a457ece149a1ffb`. The live service manifest binds intended mounts and environment. It does not capture loaded-object identities, so `actual_engine_provider_binding_qualified` remains false.

The final service manifest exactly matches the frozen package sources: `service.py` `7ea5cc4e...`, release profile `c74797d7...`, source manifest `3efff4c1...`, hybrid bridge source `4be0d14b...` and preflight source `e24d0bdb...`. Run-specific identities live only in the external JSON evidence. The release profile deliberately leaves its embedded runtime flags false; this avoids changing `sources.json` after qualification and invalidating the observed source revision.

## Operation and limits

Use the normal profile without capacity selectors:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\Start-Halogen-ServiceNow.ps1 -Profile CurrentText32K -ConsoleTrace
```

Passing `-KvPoolPositions` explicitly selects the separate capacity policy and raises startup commit admission from 124 to 131 GiB. The normal one-slot profile uses 30/124 GiB startup admission and retains 18/18 GiB runtime reserves.

The exact authenticated response is a functional check, not a benchmark. No new 0.20.7 prefill, decode or acceptance rate is published here. Capacity opt-in, two-slot operation, vision, performance and actual loaded-provider binding remain outside this qualification.
