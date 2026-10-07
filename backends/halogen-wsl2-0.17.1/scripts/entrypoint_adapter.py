"""Adapt only host_preflight in the exact extracted Halogen 0.17.1 script."""

import argparse
import hashlib
from pathlib import Path


UPSTREAM_SHA256 = "6cfb7e7a5c0aacb4e8f47f1d218f33ad2e8b3ffe9c110dcccc7772b33a62f4b0"
FUNCTION_START = b"host_preflight() {\n"
FUNCTION_END = b"\n}\n\ndownload_room_check() {"
WSL_FUNCTION = b'''host_preflight() {
  # A KFD host retains the release's preflight byte-for-byte.
  if [ -e /dev/kfd ]; then
    native_host_preflight
    return $?
  fi
  if [ "${HALOGEN_WSL_PROFILE:-}" != "halogen0171-dxg" ]; then
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
  if [ ! -x /candidate/halogen0171_hip_probe ]; then
    echo "halogen: WSL candidate HIP probe is missing" >&2
    return 1
  fi
  local arch
  export HSA_ENABLE_DXG_DETECTION=1
  if ! arch=$(timeout 8 /candidate/halogen0171_hip_probe) || [ "$arch" != "gfx1151" ]; then
    echo "halogen: WSL candidate requires a live HIP gfx1151 device" >&2
    return 1
  fi
  echo "halogen: WSL candidate DXG and live HIP gfx1151 preflight passed"
}
'''


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
    return source[:start] + native + b"\n" + WSL_FUNCTION + source[end:]


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
