#!/usr/bin/env bash
# checkfacts.sh — verify WSL/DRM state + new-branch gate removal, for the founder's questions.
echo "=== /dev/dri (Vulkan/DRM) in WSL ==="
ls /dev/dri 2>/dev/null || echo "ABSENT -> no Vulkan in WSL (confirms native Windows needed for Vulkan)"
echo
echo "=== /dev/dxg ==="
ls -la /dev/dxg 2>/dev/null
echo
cd /home/revn/strix-llama || exit 1
echo "=== mmb_enabled on the new branch (d67d5883) ==="
grep -n 'bool mmb_enabled' ggml/src/ggml-cuda/mmb.cu 2>/dev/null
echo
echo "=== count of remaining LLAMA_MMB getenv calls on new branch ==="
grep -rc 'getenv("LLAMA_MMB' ggml/src/ggml-cuda/mmb.cu 2>/dev/null
echo
echo "=== QSA decode commit contents (d67d5883 stat) ==="
git show d67d5883 --stat 2>/dev/null | head -14
echo
echo "=== does the new branch still support MTP spec? ==="
grep -c 'DRAFT_MTP' common/common.h
