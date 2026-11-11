#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# Root-owned CPU-only linking. No engine/model/accelerator execution.
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -fno-builtin -fno-stack-protector -fno-tree-loop-distribute-patterns -mgeneral-regs-only -c observer.c -o observer.o
cc -fPIC -c entry.S -o entry.o
cc -shared -Wl,-z,defs,-z,relro,-z,now,--version-script=observer.map observer.o entry.o -ldl -o libhgn0203_raw_side.so
cc -std=c11 -O2 -Wall -Wextra -Werror -Wno-unused-function producer_test.c -ldl -o producer_test
./producer_test
python3 -B test_validator.py
sha256sum libhgn0203_raw_side.so
