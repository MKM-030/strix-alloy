# Halogen / AMD update checkpoint — 4 October 2026, 07:00 UTC

Checked **2026-10-04 07:01–07:02 UTC** (09:01–09:02 Europe/Berlin). This is a read-only upstream check for the authorized nine-hour optimization run. Installed versions below are the existing observations supplied to this check; no device inventory or accelerator work was repeated.

## Halogen

The live [main commit API](https://api.github.com/repos/peonist-ai/halogen-flash-server/commits/main) returned HTTP 200 and `7f31bbd4021f217a1be9776bdb7304bcf8eca62d`, message `0.16.2`, commit time 2026-10-03 04:29:22 UTC. The [tag API](https://api.github.com/repos/peonist-ai/halogen-flash-server/tags?per_page=5) returned HTTP 200 with `v0.16.2` first, pointing to the same SHA; the next entries were v0.16.1 and v0.16.0. Both responses had server Date headers around 07:00:53–54 UTC.

The [releases API](https://api.github.com/repos/peonist-ai/halogen-flash-server/releases?per_page=5) returned HTTP 200 and the empty array `[]`; [latest-release API](https://api.github.com/repos/peonist-ai/halogen-flash-server/releases/latest) returned HTTP 404. The repository currently publishes tags/changelog without a GitHub Release record. Thus main and the newest observed tag remain exactly the existing 0.16.2 pin. The [pinned changelog](https://github.com/peonist-ai/halogen-flash-server/blob/7f31bbd4021f217a1be9776bdb7304bcf8eca62d/CHANGELOG.md) is the release-history authority, rather than a missing Release object.

## AMD Windows channels

| Official channel | Current finding | Existing installed observation |
|---|---|---|
| [Ryzen AI Max+ 395 downloads](https://www.amd.com/en/support/downloads/drivers.html/processors/ryzen/ryzen-ai-max-series/amd-ryzen-ai-max-plus-395.html), Windows 11 | Newest listed package remains **Adrenalin 26.9.2 WHQL Optional**, 2026-09-29; 26.8.1 remains WHQL Recommended | GPU `32.0.32015.2008` |
| [26.9.2 release notes](https://www.amd.com/en/resources/support-articles/release-notes/RN-RAD-WIN-26-9-2.html), Packaged Contents | GPU Driver Store `32.0.32015.2008`; NPU MCDM `32.00.20102.3930`, date 2026-05-07 | GPU and NPU versions match after normalizing leading zeros |
| [Ryzen AI Windows installation](https://ryzenai.docs.amd.com/en/latest/inst.html) and [release notes](https://ryzenai.docs.amd.com/en/latest/relnotes.html) | Current documentation is **Ryzen AI Software 1.8.0**; install page offers NPU `32.0.203.376` as production for Strix Halo, and `32.0.203.280` or newer as the stated minimum | NPU MCDM `32.00.20102.3930`; XRT `32.00.20102.3931` |

The separate Ryzen AI driver branch does not establish that `32.0.203.376` supersedes the installed MCDM package. These pages supply no exact current XRT version comparison. No newer applicable engine or GPU/NPU update was verified, and the checked authorities show no change from the prior checkpoint.

## Limits and actions

GitHub API data was fetched directly through read-only HTTPS because the web reader could not open those API URLs. AMD pages were read from their current official URLs; the installation page reports last updated 2026-09-28. This finding concerns the named public channels at the check time, and does not rule out an unlisted OEM, Windows Update, preview, or later publication. No conclusion relies on absent search results or an assumed 26.10.1 URL.

No hardware tests, engine launches, installs, environment changes, driver changes, firmware changes, or commits were performed. Only this checkpoint file was created.
