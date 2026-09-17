#!/usr/bin/env bash
# Copyright 2026 Ciru. Optional native BF16 image encoder/projector profile.
set -euo pipefail
bundle_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec bash "$bundle_root/serve.sh" --enable-images --image-max-pixels 1048576 "$@"
