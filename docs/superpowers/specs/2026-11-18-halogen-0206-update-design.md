# Halogen 0.20.6 Update Design

## Intent

Update Strix Alloy from the managed Halogen 0.20.3 integration to the latest verified upstream release, Halogen 0.20.6, adapt the WSL/DXG bridge to the new binary and frontend contracts, leave a verified managed endpoint available for ServiceNow, and publish the reproducible source, tests, and evidence to the GitHub repository.

## Goals

- Pin the exact upstream tag, OCI manifest, image configuration, engine, entrypoint, API tools, runtime providers, and locally built bridge products.
- Revalidate the finite WSL memory bridge against the 0.20.6 engine instead of carrying 0.20.3 offsets or hashes forward.
- Preserve the public `halogen-v2` alias, port 8840, stable ServiceNow token, 32K text profile, paired 8192 prefill controls, PLD `3,3`, MTP gate `0.90`, and the existing admission/reserve policy.
- Preserve the upstream 0.20.6 r2 drafter selection so the release's decode improvement is available when the publisher's r2 asset is present and verified.
- Pass offline contract tests, build/install verification, authenticated discovery, one bounded functional request, and runtime reserve checks.
- Commit and push the complete tracked change and update documentation with exact claims and limits.

## Non-goals

- Do not terminate or adopt the foreign Ornith server, Riot processes, or other user programs.
- Do not claim upstream performance numbers as local measurements.
- Do not enable experimental DNZ, RAW, NPU handoff, overclocking, voltage, BIOS, driver, or global WSL changes.
- Do not remove historical backend packages or retained failure evidence.

## Constraints

- Upstream release: tag `v0.20.6`, manifest `sha256:f68892a56d8a1182645042574d702374bff402bb986ec4d49304cbe89483dbaf`, config `sha256:3f5f2337842b8003f9826e226adcd4ad4a620dd3ed2e3f780dfb9f00dae4dfa6`.
- Default `CurrentText32K` startup admission remains 30 GiB physical and 124 GiB commit headroom. Explicit capacity opt-in retains the 30/131 GiB floor; request entry remains 22/22 GiB and runtime reserve remains 18/18 GiB.
- Official WSL remains unsupported, so the local bridge must fail closed on any unknown binary or ABI.
- The existing 0.20.3 terminal failure state is evidence and must not be rewritten as a successful stop.
- A server start is attempted only after exact ownership and memory checks; if the foreign model makes runtime reserve impossible, the update remains installed and the precise coexistence blocker is reported without killing it.

## Approaches

1. **Reuse the 0.20.3 bridge unchanged.** Fast, but unsafe because hashes, RVAs, entrypoint text, API layout, and provider ABI are version-specific. Rejected.
2. **Run the stock 0.20.6 container.** Avoids local maintenance but the official entrypoint rejects WSL/DXG and would remove the ServiceNow-managed lifecycle and reserve controls. Rejected.
3. **Create a fresh versioned 0.20.6 package from the proven adapter architecture.** Extract the immutable image passively, prove the changed contracts, update only the affected pins/transforms, then promote it through the managed launcher. Chosen because it preserves fail-closed behavior and produces reviewable evidence.

## Architecture

The new `backends/halogen-wsl2-0.20.6` package retains the established controller and bridge architecture but owns independent 0.20.6 identities. Passive extraction supplies the exact engine, entrypoint, API files, HIP headers, and providers. Offline analysis establishes a new semantic bridge binding; tests lock the new binary/API/entrypoint contracts before the server and launcher accept 0.20.6. The managed controller remains the sole owner of the live Halogen process and restores the same ServiceNow-facing API contract.

## Success criteria

- Every tracked source member is represented in the new source manifest and passes its package tests.
- Bridge and entrypoint adapters accept only the verified 0.20.6 inputs and reject altered identities or ABI shapes.
- Server and PowerShell launcher tests prove 0.20.6 is the default while historical versions remain selectable.
- Installation verifies all artifact hashes and provider identities.
- The final state records either a ready authenticated 0.20.6 endpoint on port 8840 with a successful bounded request and reserves intact, or a concrete foreign-resource blocker after all offline work is complete.
- The intended diff is committed and `origin/main` is updated.
