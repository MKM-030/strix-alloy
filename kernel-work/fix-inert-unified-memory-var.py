#!/usr/bin/env python3
"""Remove the inert GGML_HIP_ENABLE_UNIFIED_MEMORY from launch scripts.

The build only reads GGML_CUDA_ENABLE_UNIFIED_MEMORY (ggml-cuda.cu:156), so this
setting never did anything: every measured number was taken with plain cudaMalloc.
Deleting it is therefore behaviour-preserving. It is deliberately NOT renamed --
renaming would switch the weights to a managed allocation and invalidate the
published baseline (see docs/benchmarks/reference-forks-assessment-20260916.md).

Handles three forms:
  $env:GGML_HIP_ENABLE_UNIFIED_MEMORY = '1'     -> line deleted
  export GGML_HIP_ENABLE_UNIFIED_MEMORY=1       -> line deleted
  export A=1 GGML_HIP_ENABLE_UNIFIED_MEMORY=1 B -> token removed, line kept
"""
import os
import re
import sys

ROOT = r"C:\Projects\strix-alloy\kernel-work"
VAR = "GGML_HIP_ENABLE_UNIFIED_MEMORY"

# standalone assignment on its own line (powershell or shell)
RE_STANDALONE = re.compile(r"^\s*(?:\$env:)?" + VAR + r"\s*=\s*['\"]?1['\"]?\s*;?\s*$")
RE_EXPORT_ONLY = re.compile(r"^\s*export\s+" + VAR + r"=1\s*$")
# token inside a longer export/assignment line
RE_TOKEN = re.compile(r"(?<![A-Za-z0-9_])" + VAR + r"=1\s*")


def main():
    changed = []
    for dirpath, _dirnames, filenames in os.walk(ROOT):
        for fn in filenames:
            if not fn.endswith((".ps1", ".sh")):
                continue
            path = os.path.join(dirpath, fn)
            with open(path, "r", encoding="utf-8", errors="surrogateescape") as f:
                lines = f.readlines()
            if not any(VAR in ln for ln in lines):
                continue

            out = []
            for ln in lines:
                if RE_STANDALONE.match(ln) or RE_EXPORT_ONLY.match(ln):
                    continue  # whole line was the dead setting
                if VAR in ln:
                    # keep the line, drop just the dead token
                    new = RE_TOKEN.sub("", ln)
                    new = new.replace(" && set \"\"", "")   # tidy an emptied cmd fragment
                    if new.strip() in ("export", "set", "", "&&", "' +"):
                        continue
                    out.append(new)
                else:
                    out.append(ln)

            newtext = "".join(out)
            if newtext != "".join(lines):
                with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as f:
                    f.write(newtext)
                changed.append(os.path.relpath(path, ROOT))

    print(f"files changed: {len(changed)}")
    for c in sorted(changed):
        print("  " + c)


if __name__ == "__main__":
    sys.exit(main())
