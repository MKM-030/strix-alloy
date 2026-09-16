#!/usr/bin/env bash
# commit-stub.sh — commit the Windows prefetch no-op stub on the win-native branch.
cd /home/revn/strix-llama || exit 1
git add src/llama-lazy-reader.h
git -c user.name=revn -c user.email=revn@local commit -F - <<'MSG'
win: restore the _WIN32 lazy-reader prefetch() no-op stub

On Windows the lazy direct reader is stubbed out and the mmap fallback is used,
where prefetch() is a page-cache hint. qwen4exp calls prefetch() unconditionally,
so the absent no-op aborted model load on _WIN32. Behaviour-correct on the
fallback; reported as pwilkin/llama.cpp issue #24.
MSG
git log --oneline -2
