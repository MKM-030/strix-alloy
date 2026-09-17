#!/usr/bin/env bash
# Copyright 2026 Ciru. Ornith1.5 Ciru Halo Agent production profile.
set -euo pipefail
bundle_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$bundle_root/paths.env"
export ORNITH_C1_POLICY=auto
export ORNITH_PERSISTENT_IU4_LIBRARY="$bundle_root/native/libornith_persistent_iu4.so"
export ORNITH_PERSISTENT_IU4_MIN_SEQ=32768
export CC="${CC:-$(command -v gcc)}" CXX="${CXX:-$(command -v g++)}"
exec bash "$bundle_root/packaging/serve.sh" \
 --runtime-root "$ORNITH_RUNTIME_ROOT" --plugin-site "$bundle_root/plugin-site" \
 --model "$ORNITH_MODEL" --draft "$ORNITH_DRAFT" \
 --native-library-directory "$bundle_root/native" --cache-directory "$bundle_root/cache" \
 --context 262144 --cache-gib 44 --max-seqs 8 --block-size 1120 \
 --enable-tools --compact-prefill --folded-decode --token-major-kv --routed-prefill-a4 \
 --draft-tokens 7 --prefix-cache --fine-prefix-cache \
 --iu4-prefill-library "$bundle_root/native/libornith_attention_iu4.so" \
 --served-name ciru-halo-agent "$@"
