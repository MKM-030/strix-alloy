#!/usr/bin/env bash
# Env wrapper for strix-llama over DXG. Source this, never execute.
export VLLM_SOURCE=/home/revn/ciru-runtime/sources/vllm-glm53-strix
export VLLM_VENV=/home/revn/ciru-runtime/venv
export AITER_SOURCE=/home/revn/ciru-runtime/sources/aiter-gfx1151
source /home/revn/ciru-runtime/runtime-env.sh
export HSA_ENABLE_DXG_DETECTION=1
export GGML_HIP_ENABLE_UNIFIED_MEMORY=1
