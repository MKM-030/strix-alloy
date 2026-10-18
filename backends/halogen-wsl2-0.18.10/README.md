# Inactive Halogen 0.18.10 source preparation

The immutable 0.18.10 image, engine, API, and adapted entrypoint are pinned. A fresh static map verifies the demand seam, its stack/register contract, and seven direct helpers against 0.18.8. CPU products, installation, actual engine provider binding, and serving qualification remain separate root-owned work.

The image internal revision is `7506873e1b0b`; the public `v0.18.10` tag points to `9d11f18aa40d93ba6bc7cb65ee488b1acc834d7d`. The API and engine obtain their reported version from the pinned image environment `HALOGEN_IMAGE_VERSION=0.18.10`.

Only verified source-manifest members were copied from 0.18.8. Existing complete-file model receipts are reused only after exact file-identity checks; models, credentials, installation state, and runtime files were not copied during this preparation. The retained 18-GiB runtime reserve, 22-GiB request-entry reserve, normal startup floors, vision increment, and model identity policy are unchanged. KV8 is not enabled. Managed context, cache, thinking, vision, and 8192-token prefill controls stay in the matched downstream profile.

WSL/DXG remains a private adapter path; upstream supports native Linux/KFD.
