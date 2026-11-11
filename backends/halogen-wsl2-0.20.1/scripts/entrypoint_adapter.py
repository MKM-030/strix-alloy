"""Private candidate: exact WSL preflight plus monotonic watchdog elapsed time.

This adapter reads/writes bytes only. It never executes a shell or the server.
"""

import argparse
import hashlib
from pathlib import Path


UPSTREAM_SHA256 = 'e7bbb4d3c1ea4a4c1841245a79818a23ebfae1c4489d25f119508d092a6c1d51'
ORIGINAL_WSL_SHA256 = '62f1fc54b149cedc6d89987fa497f22b71804108eb609b8d7a32bc126aa202cc'
WATCHDOG_SHA256 = 'df8e32d6aae1e6f42a657f118fa694e1093a0b480a9ddc534d0468a4e1f19810'
UPTIME_HELPER = br'''wd_uptime_s() {
  # Linux boot uptime is independent of realtime clock corrections. Its
  # integer-second resolution preserves the original watchdog granularity.
  local _hgw_uptime _hgw_idle _hgw_seconds
  if ! { read -r _hgw_uptime _hgw_idle < "${_hg_proc:-/proc}/uptime"; } 2>/dev/null; then
    echo "halogen: watchdog uptime clock is unreadable" >&2
    return 1
  fi
  if ! [[ "$_hgw_uptime" =~ ^([0-9]+)([.][0-9]+)?$ ]]; then
    echo "halogen: watchdog uptime clock is invalid" >&2
    return 1
  fi
  _hgw_seconds="${BASH_REMATCH[1]}"
  if [ "${#_hgw_seconds}" -gt 18 ]; then
    echo "halogen: watchdog uptime clock is outside integer range" >&2
    return 1
  fi
  printf '%s\n' "$((10#$_hgw_seconds))"
}

'''
FUNCTION_START = b"host_preflight() {\n"
FUNCTION_END = b"\n}\n\ndownload_room_check() {"
WSL_FUNCTION = b'''host_preflight() {
  # A KFD host retains the release's preflight byte-for-byte.
  if [ -e /dev/kfd ]; then
    native_host_preflight
    return $?
  fi
  if [ "${HALOGEN_WSL_PROFILE:-}" != "halogen0201-dxg" ]; then
    native_host_preflight
    return $?
  fi
  if [ -n "${HALOGEN_DOWNLOAD:-}" ]; then
    echo "halogen: WSL candidate prohibits HALOGEN_DOWNLOAD" >&2
    return 1
  fi
  if [ ! -c /dev/dxg ] || [ ! -r /dev/dxg ] || [ ! -w /dev/dxg ]; then
    echo "halogen: WSL candidate requires an accessible character /dev/dxg" >&2
    return 1
  fi
  if [ ! -r /usr/lib/librocdxg.so ] ||
     [ "$(sha256sum /usr/lib/librocdxg.so | awk '{print $1}')" != "0de8e26350933754d3d9ead9446c39e04792a2bef68d1b6df97950d07312b9d6" ]; then
    echo "halogen: WSL candidate DXG library identity changed" >&2
    return 1
  fi
  if [ ! -x /candidate/halogen0201_hip_probe ]; then
    echo "halogen: WSL candidate HIP probe is missing" >&2
    return 1
  fi
  local arch
  export HSA_ENABLE_DXG_DETECTION=1
  if ! arch=$(timeout 8 /candidate/halogen0201_hip_probe) || [ "$arch" != "gfx1151" ]; then
    echo "halogen: WSL candidate requires a live HIP gfx1151 device" >&2
    return 1
  fi
  echo "halogen: WSL candidate DXG and live HIP gfx1151 preflight passed"
}
'''


def adapt_watchdog(source: bytes) -> bytes:
    if hashlib.sha256(source).hexdigest() != ORIGINAL_WSL_SHA256:
        raise ValueError('Original adapted entrypoint SHA256 mismatch')
    marker = b'engine_watchdog() {\n'
    if source.count(marker) != 1 or b'wd_uptime_s() {' in source:
        raise ValueError('Pinned watchdog function boundary differs')
    start = source.index(marker)
    end = source.index(b'\n}\n', start) + 3
    original = source[start:end]
    if hashlib.sha256(original).hexdigest() != WATCHDOG_SHA256:
        raise ValueError('Pinned watchdog body SHA256 mismatch')
    if original.count(b'$(date +%s)') != 3:
        raise ValueError('Pinned watchdog realtime clock count differs')
    changed = original.replace(b'$(date +%s)', b'$(wd_uptime_s)')
    # Preserve an actual clock failure as failure; never substitute wall time.
    changed = changed.replace(b'last_ok=$(wd_uptime_s)\n', b'last_ok=$(wd_uptime_s) || return 1\n')
    changed = changed.replace(b'now=$(wd_uptime_s)\n', b'now=$(wd_uptime_s) || return 1\n')
    return source[:start] + UPTIME_HELPER + changed + source[end:]


def transform(source: bytes) -> bytes:
    digest = hashlib.sha256(source).hexdigest()
    if digest != UPSTREAM_SHA256:
        raise ValueError(f"upstream entrypoint SHA256 mismatch: {digest}")
    if source.count(FUNCTION_START) != 1 or source.count(FUNCTION_END) != 1:
        raise ValueError("upstream host_preflight shape changed")
    start = source.index(FUNCTION_START)
    end = source.index(FUNCTION_END, start) + len(b"\n}\n")
    original = source[start:end]
    native = original.replace(FUNCTION_START, b"native_host_preflight() {\n", 1)
    return adapt_watchdog(source[:start] + native + b"\n" + WSL_FUNCTION + source[end:])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    candidate = transform(args.upstream.read_bytes())
    with args.output.open("xb") as handle:
        handle.write(candidate)


if __name__ == "__main__":
    main()
