# Halogen 0.20.6 WSL2 backend

The exact image, engine, API and entrypoint are pinned, and the backend is installed. The four CPU outputs were freshly built and hash-bound. Historical run `f19220518d3040368449a89b6a116b51` qualified its exact external-r2 source and v2 bridge revision in the managed one-slot 32K text profile. Later bridge development changed the current 0.20.6 package source and binary, so that evolved revision is not runtime-qualified.

Default one-slot `CurrentText32K` retains 30/124 GiB startup admission; explicit capacity opt-in retains 30/131 GiB. The 18/18 GiB runtime reserves, text capacity policy and bearer authentication remain. The new 59-field cached wire is validated; the unchanged CacheOff producer still needs its 51-to-50-field correction. Upstream native-tokenizer, tool masking and model checks are retained. Empty `HALOGEN_CK_OVERLAY` preserves upstream automatic selection of `qwen38-flash-next-drafter-r2.hgn` when present.

The historical qualified run completed the shortened main registration (`65,163,800,576` copied bytes) followed by the external r2 registration (`1,523,564,096` copied bytes), with no preflight rejection. API and engine both reported 0.20.6; authenticated discovery returned `halogen-v2`, and a bounded request returned `HALOGEN_0206_READY`. This is retained functional evidence for the pinned `f192...` revision, not a benchmark or qualification of the current evolved package. Capacity opt-in, two-slot operation and vision remain separately unqualified. See the [dated update record](../../docs/research/halogen0206-update-20261118.md) for exact identities, receipts and limits.

Complete checkpoint and N-gram hashing derives a bounded 600..3600 second deadline from the pinned file size, so the 124 GB source can be verified on Windows-mounted storage without weakening the full-file identity check.

Run CPU checks with `python -m unittest discover -s backends/halogen-wsl2-0.20.6/tests`. Set HALOGEN0206_CAPTURE to a passive extracted image directory for the exact ELF/API/entrypoint cases; absent captures are explicit skips. Linux compilation fixtures are separate and may skip on Windows.
