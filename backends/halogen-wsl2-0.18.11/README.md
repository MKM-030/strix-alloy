# Inactive Halogen 0.18.11 source preparation

The immutable 0.18.11 image, engine, API, and adapted entrypoint are pinned. A fresh static map verifies the demand seam, its stack/register contract, and seven direct helpers against 0.18.10. CPU products, installation, actual engine provider binding, and serving qualification remain separate root-owned work.

The image internal revision is `44d9515841f5`; the public `v0.18.11` tag points to `002589b11480cf3422f209b336c19dcc208fc69f`. The API and engine obtain their reported version from the pinned image environment `HALOGEN_IMAGE_VERSION=0.18.11`.

Only verified source-manifest members were copied from 0.18.10. Existing complete-file model receipts are reused only after exact file-identity checks; models, credentials, installation state, and runtime files were not copied during this preparation. The retained 18-GiB runtime reserve, 22-GiB request-entry reserve, normal startup floors, vision increment, and model identity policy are unchanged. KV8 is not enabled. Managed context, cache, thinking, vision, and 8192-token prefill controls stay in the matched downstream profile.

WSL/DXG remains a private adapter path; upstream supports native Linux/KFD.
