#!/usr/bin/env bash
# runbook-tonight.sh — gated steps for when the other session releases WSL.
# Usage: bash runbook-tonight.sh <step>   where step is one of:
#   gate | step1 | step2 | step3on | step3off | step4 | step5 | summary
# Rules: ONE Flash-Next instance per box, ever. Abort the sequence if any gate fails.
# Full rationale: docs/benchmarks/decode-kernel-theory-prep-20260913.md

BASE=/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work
FN=/home/revn/models/flash-next-unsloth/Qwen3.8-Flash-Next-UD-IQ4_XS-00001-of-00003.gguf
DRAFT=/home/revn/models/flash-next-unsloth/MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf
FORK=/home/revn/strix-llama

step_gate() {
  echo "== STEP 0: exclusivity gate =="
  ps aux | grep -E 'llama|flash_serve|dockerd|containerd' | grep -v grep && {
    echo "GATE FAIL: co-tenant processes present (llama/docker). Coordinate first."; return 1; }
  AVAIL=$(free -g | awk '/^Mem:/{print $7}')
  echo "avail=${AVAIL}G"
  [ "$AVAIL" -ge 55 ] || { echo "GATE FAIL: <55G available"; return 1; }
  source $BASE/env.sh
  $FORK/build-hip/bin/llama-bench --list-devices 2>&1 | tail -1
  echo "GATE PASS (human: confirm the other session is paused, then continue)"
}

step_step1() {
  echo "== STEP 1: uncontaminated graphs-ON absolutes =="
  bash $BASE/expA-arm.sh on-p0x "" -p 0 -n 128 -r 3
  bash $BASE/expA-arm.sh on-tx "LLAMA_GRAPH_TIMING=1 LLAMA_GRAPH_DIAG=1" -p 0 -n 64 -r 1
  echo "compare gpu_wait median vs the co-tenant-era 49.2 ms (expA/expA-on-t.log)"
}

step_step2() {
  echo "== STEP 2: the open A/B arm — graphs OFF, once, exclusive =="
  bash $BASE/expA-arm.sh off-p0x GGML_CUDA_DISABLE_GRAPHS=1 -p 0 -n 128 -r 3
  echo "exit=$? ; if this died with nothing else running, dxg instability is proven; if not, this is the true A/B number"
}

step_step3on() {
  echo "== STEP 3: correctness text, graphs ON =="
  bash $BASE/correctness-server.sh on $FN
}

step_step3off() {
  echo "== STEP 3b: correctness text, graphs OFF (only if step2 survived) =="
  bash $BASE/correctness-server.sh off $FN
  python3 $BASE/diff_correctness.py $BASE/expA/corr-on-*.json $BASE/expA/corr-off-*.json
}

step_step4() {
  echo "== STEP 4: op micro-bench build + run =="
  source $BASE/env.sh
  hipcc -O2 -o /home/revn/kernel-work/op-microbench $BASE/op-microbench.cpp \
    -I$FORK/ggml/include -L$FORK/build-hip/bin \
    -lggml -lggml-base -lggml-cpu -lggml-hip \
    -Wl,-rpath,$FORK/build-hip/bin || { echo "BUILD FAILED"; return 1; }
  /home/revn/kernel-work/op-microbench
}

step_step5() {
  echo "== STEP 5: MTP prototype =="
  source $BASE/env.sh
  [ -f "$DRAFT" ] || DRAFT=/mnt/c/AI/models/qwen38-flash/mtp-Qwen3.8-Flash-Next-Q8_0.gguf
  # FR-Spec head (3.64 GiB, what drluoto/vincentkelleher measured 35.8 t/s with) — fetch if absent:
  FR=$BASE/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf
  [ -f "$FR" ] || curl -fL --retry 3 -C - -o "$FR" \
    "https://huggingface.co/drluoto/Qwen3.8-Flash-Next-MTP-FR-Spec/resolve/main/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf" \
    || echo "FR-Spec head fetch failed (locate the file on drluoto's HF; shared head still usable)"
  # froggeric fixed chat template (required by drluoto build; recommended for ours):
  TPL=$BASE/chat_template.jinja
  [ -f "$TPL" ] || curl -fL --retry 3 -o "$TPL" \
    "https://huggingface.co/froggeric/Qwen-Fixed-Chat-Templates/resolve/main/chat_template.jinja" \
    || TPL=""
  TPLARG=""; [ -n "$TPL" ] && [ -f "$TPL" ] && TPLARG="--chat-template-file $TPL"
  [ -f "$DRAFT" ] || { echo "no draft model available"; return 1; }
  # (a) greedy identity gate: non-spec output first (already captured in step3), then spec:
  $FORK/build-hip/bin/llama-server -m $FN -md "$DRAFT" -ngl 99 -fa on -c 2048 -b 2048 -ub 2048 -t 8 \
    --spec-type draft-mtp --spec-draft-model "$DRAFT" $TPLARG --host 127.0.0.1 --port 8098 --no-webui \
    > $BASE/expA/mtp-server.log 2>&1 &
  SRV=$!
  for i in $(seq 1 240); do
    curl -s http://127.0.0.1:8098/health 2>/dev/null | grep -q ok && break
    kill -0 $SRV 2>/dev/null || { echo SERVER DIED; tail -5 $BASE/expA/mtp-server.log; return 1; }
    sleep 2
  done
  curl -s http://127.0.0.1:8098/v1/chat/completions -H 'Content-Type: application/json' \
    -d @$BASE/correctness-prompt.json > $BASE/expA/mtp-on.json
  echo "spec output saved to $BASE/expA/mtp-on.json"
  echo "greedy identity: diff content vs expA/corr-on-*.json (must be identical)"
  echo "acceptance + timing: grep draft $BASE/expA/mtp-server.log | tail"
  kill $SRV 2>/dev/null
  echo "next: repeat with FR-Spec head if fetched; depth sweep — verify the fork's depth flag in common/arg.cpp (--spec-draft-*)"
}

step_summary() {
  echo "== STEP 6: update docs with tonight's numbers, then decide D' vs Q8_0-GEMV-uplift work =="
  echo "inputs: expA-on-p0x/on-tx (absolutes), expA-off-p0x (the A/B), op-microbench table, mtp-on"
}

step_dl() {
  echo "== STEP: resume IQ4_NL PROJFIX download (shards 7-9 of 9) — the ~3x prefill lever =="
  # ~3-4 GiB per shard; the earlier session's curl died mid shard 7. This download is network-only
  # (no GPU) and can run alongside anything, but avoid running it DURING prefill benchmarks (disk I/O).
  mkdir -p /home/revn/models/flash-next-strix
  cd /home/revn/models/flash-next-strix
  for S in 7 8 9; do
    F="Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-0000${S}-of-00009.gguf"
    [ -f "$F.done" ] && { echo "$F complete"; continue; }
    curl -fL -C - --retry 5 --retry-delay 5 -o "$F" \
      "https://huggingface.co/ilintar/qwen3.8-flash-next-gguf-strix-halo/resolve/main/$F" && touch "$F.done"
  done
  ls -la
  echo "when complete: re-run expA prefill bench on this quant (expect ~3x prefill vs UD-IQ4_XS if PROJFIX feeds the WMMA path)"
}

step_step7() {
  echo "== STEP 7: PROJFIX quant — the halogen-parity path (founder priority) =="
  PF=/home/revn/models/flash-next-strix/Qwen3.8-Flash-Next-IQ4_NL-PROJFIX-00001-of-00009.gguf
  [ -f "$PF" ] || { echo "PROJFIX shard 1 missing"; return 1; }
  # (a) serial decode + prefill, graphs ON, uncontaminated:
  BENCH_MODEL=$PF bash $BASE/expA-arm.sh pf-on "" -p 0 -n 128 -r 3
  BENCH_MODEL=$PF bash $BASE/expA-arm.sh pf-p2k "" -p 2048 -n 128 -r 2
  # (b) MTP with both heads (FR-Spec preferred — what the 35.8 t/s measurement used):
  FR=/home/revn/models/mtp-heads/mtp-Qwen3.8-Flash-Next-Q8_0-frspec-65k.gguf
  [ -f "$FR" ] || { echo "FR-Spec head still downloading; rerun step7 after it lands"; }
  source $BASE/env.sh
  TPL=$BASE/chat_template.jinja
  TPLARG=""; [ -f "$TPL" ] && TPLARG="--chat-template-file $TPL --reasoning-format deepseek"
  if [ -f "$FR" ]; then
    $FORK/build-hip/bin/llama-server -m $PF -md $FR -ngl 99 -fa on -c 8192 -b 2048 -ub 2048 -t 8 \
      --spec-type draft-mtp --spec-draft-model $FR $TPLARG --lazy-mode on-direct \
      --host 127.0.0.1 --port 8098 --no-webui > $BASE/expA/pf-mtp-server.log 2>&1 &
    SRV=$!
    for i in $(seq 1 300); do
      curl -s http://127.0.0.1:8098/health 2>/dev/null | grep -q ok && break
      kill -0 $SRV 2>/dev/null || { echo SERVER DIED; tail -5 $BASE/expA/pf-mtp-server.log; return 1; }
      sleep 2
    done
    curl -s http://127.0.0.1:8098/v1/chat/completions -H 'Content-Type: application/json' \
      -d @$BASE/correctness-prompt.json > $BASE/expA/pf-mtp.json
    echo "MTP output: $BASE/expA/pf-mtp.json ; acceptance+timing: grep -i draft $BASE/expA/pf-mtp-server.log | tail"
    kill $SRV 2>/dev/null
  fi
  echo "targets: serial ~26 t/s (halogen-GGUF parity); with MTP 37-50 t/s (halogen-native class)"
}

case "$1" in
  gate) step_gate ;; step1) step_step1 ;; step2) step_step2 ;; step3on) step_step3on ;;
  step3off) step_step3off ;; step4) step_step4 ;; step5) step_step5 ;; summary) step_summary ;;
  dl) step_dl ;; step7) step_step7 ;;
  *) echo "usage: $0 gate|step1|step2|step3on|step3off|step4|step5|summary|dl|step7" ;;
esac
