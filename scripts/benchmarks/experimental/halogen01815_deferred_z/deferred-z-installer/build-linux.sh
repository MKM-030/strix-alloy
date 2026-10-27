#!/bin/sh
set -eu
cd "$(dirname "$0")"
: "${CXX:=g++}"
common='-std=c++17 -O2 -Wall -Wextra -Werror -mno-avx -mno-avx2 -mno-avx512f'
"$CXX" $common -shared -fPIC installer_linux.cpp ../deferred-z-stream/launch_redirect_linux.cpp -ldl -pthread -Wl,-z,relro,-z,now,-z,noexecstack,-z,defs -o libhalogen01815-deferred-z.so
"$CXX" $common test_installer_cpu.cpp -o test_installer_cpu
./test_installer_cpu
"$CXX" $common test_ht_policy.cpp -o test_ht_policy
./test_ht_policy
"$CXX" $common test_closure_linux.cpp ../deferred-z-stream/launch_redirect_linux.cpp -ldl -pthread -o test_closure_linux
./test_closure_linux
