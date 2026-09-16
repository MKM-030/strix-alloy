#!/usr/bin/env python3
"""Token-exact Flash-Next benchmark client for llama-server (Windows or WSL).

Measures PREFILL and DECODE at exact prompt token counts using /tokenize sizing and
/completion with cache_prompt=false, reading llama.cpp's `timings` block.

Usage:
  python fnbench.py --port 8113 --label vulkan-frspec --sizes 1024,8192,32768,65536,131072 \
      --gen 128 --repeats 3 --out results/vulkan-frspec.json

Notes:
  * Prompt cache is disabled per request so prompt_n is a true fresh prefill.
  * Server must be started with -c >= max(size)+gen+margin.
  * MTP acceptance (draft_n_accepted) is captured when present.
"""
import argparse
import glob
import json
import os
import sys
import time
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "bench-corpus.txt")
TOKENS = os.path.join(HERE, "bench-tokens.json")


def http_json(url, payload=None, timeout=7200):
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def build_corpus(min_tokens_hint=300000):
    """Concatenate repo docs into a natural-language corpus large enough for 128k+ prompts."""
    if os.path.exists(CORPUS) and os.path.getsize(CORPUS) > 2_000_000:
        print(f"corpus exists: {os.path.getsize(CORPUS)/1e6:.1f} MB")
        return
    roots = [
        r"C:\Projects\REV-N-ornith-eval-20260911\docs",
        r"C:\Projects\REV-N\docs",
    ]
    chunks = []
    for root in roots:
        for ext in ("*.md", "*.txt"):
            for p in glob.glob(os.path.join(root, "**", ext), recursive=True):
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        t = f.read()
                    if len(t) > 500:
                        chunks.append(f"\n\n=== {os.path.basename(p)} ===\n\n{t}")
                except Exception:
                    pass
    text = "".join(chunks)
    # augment with varied synthetic prose so decode is not degenerate and length is sufficient
    para = ("The system processes each request in order, recording the measured latency and the "
            "aggregate throughput for every stage of the pipeline. Operators review the resulting "
            "tables, compare them against the published reference figures, and adjust the batch "
            "sizes until the observed numbers converge on a stable plateau. ")
    i = 0
    while len(text) < min_tokens_hint * 4:  # ~4 chars/token
        text += f"\n[section {i}] " + para
        i += 1
    with open(CORPUS, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"corpus built: {len(text)/1e6:.1f} MB -> {CORPUS}")


def tokenize(port, text):
    r = http_json(f"http://127.0.0.1:{port}/tokenize", {"content": text})
    return r["tokens"]


def get_token_pool(port, need):
    """Tokenize the corpus once; cache token ids. Return list of >= need tokens."""
    if os.path.exists(TOKENS):
        try:
            pool = json.load(open(TOKENS))
            if len(pool) >= need:
                print(f"token pool cached: {len(pool)} tokens")
                return pool
        except Exception:
            pass
    build_corpus()
    with open(CORPUS, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    print(f"tokenizing corpus ({len(text)/1e6:.1f} MB)...", flush=True)
    pool = tokenize(port, text)
    print(f"tokenized -> {len(pool)} tokens")
    json.dump(pool, open(TOKENS, "w"))
    return pool


def wait_ready(port, timeout=1800):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(3)
    return False


def run_one(port, tokens, gen, timeout=7200):
    payload = {
        "prompt": tokens,
        "n_predict": gen,
        "cache_prompt": False,
        "temperature": 0.0,
        "top_k": 1,
        "top_p": 1.0,
        "min_p": 0.0,
        "stream": False,
    }
    r = http_json(f"http://127.0.0.1:{port}/completion", payload, timeout=timeout)
    t = r.get("timings", {})
    return {
        "prompt_n": t.get("prompt_n"),
        "prompt_ms": t.get("prompt_ms"),
        "prefill_tps": t.get("prompt_per_second"),
        "predicted_n": t.get("predicted_n"),
        "predicted_ms": t.get("predicted_ms"),
        "decode_tps": t.get("predicted_per_second"),
        "draft_n": t.get("draft_n"),
        "draft_n_accepted": t.get("draft_n_accepted"),
    }


# A realistic assistant-style prompt used for the "chat" mode: the acceptance rate on natural
# prose/code is what the official benchmarks report, so we measure both corpus-continuation and this.
CHAT_SYSTEM = (
    "You are a senior systems engineer. Answer precisely and at length, with concrete numbers, "
    "worked examples, and code where useful. Never pad with filler."
)
CHAT_USER = (
    "Explain how a modern MoE transformer with gated linear attention processes a single decode "
    "step end to end. Cover: token embedding lookup, the layer norm and projection GEMVs, the "
    "routing of the token to its top-k experts, the expert FFN compute, the shared expert, the "
    "attention recurrence for the linear-attention layers, the KV read for the full-attention "
    "layers, the final norm and the output projection over the vocabulary, and sampling. For each "
    "stage give the dominant memory traffic and whether it is bandwidth- or latency-bound. Then "
    "compare the cost profile of prefill (long batch) against decode (batch one), and list the "
    "five optimizations with the largest expected effect on decode throughput, with a rough "
    "percentage for each. Finally write a short worked example computing bytes-per-token for a "
    "6B-active MoE at 4.25 bits per weight."
)


def run_chat(port, max_tokens, timeout=7200, system=None, user=None):
    payload = {
        "messages": [
            {"role": "system", "content": system or CHAT_SYSTEM},
            {"role": "user", "content": user or CHAT_USER},
        ],
        "n_predict": max_tokens,
        "cache_prompt": False,
        "temperature": 0.0,
        "top_k": 1,
        "top_p": 1.0,
        "min_p": 0.0,
        "stream": False,
    }
    r = http_json(f"http://127.0.0.1:{port}/v1/chat/completions", payload, timeout=timeout)
    # /v1/chat/completions returns usage + timings (llama.cpp extensions)
    t = r.get("timings", {})
    return {
        "prompt_n": t.get("prompt_n"),
        "prompt_ms": t.get("prompt_ms"),
        "prefill_tps": t.get("prompt_per_second"),
        "predicted_n": t.get("predicted_n"),
        "predicted_ms": t.get("predicted_ms"),
        "decode_tps": t.get("predicted_per_second"),
        "draft_n": t.get("draft_n"),
        "draft_n_accepted": t.get("draft_n_accepted"),
        "text_chars": len(r.get("choices", [{}])[0].get("message", {}).get("content", "")),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--label", required=True)
    ap.add_argument("--sizes", default="1024,8192,32768,65536,131072")
    ap.add_argument("--mode", default="corpus", choices=["corpus", "chat", "both"],
                    help="corpus = continuation of the doc pool; chat = realistic assistant prompt; both")
    ap.add_argument("--gen", type=int, default=128)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--repeats-big", type=int, default=0,
                    help="repeats for sizes >= --big-threshold (0 = same as --repeats)")
    ap.add_argument("--big-threshold", type=int, default=32768)
    ap.add_argument("--out", required=True)
    ap.add_argument("--context-limit", type=int, default=0,
                    help="skip sizes where size+gen+headroom exceeds this (server -c)")
    args = ap.parse_args()

    sizes = [int(s) for s in args.sizes.split(",") if s]
    if args.context_limit:
        # llama.cpp needs the full prompt + n_predict to fit in -c; keep a safety margin
        sizes = [s for s in sizes if s + args.gen + 64 <= args.context_limit]
    print(f"label={args.label} port={args.port} sizes={sizes} gen={args.gen} repeats={args.repeats}")

    if not wait_ready(args.port):
        print("SERVER NOT READY", file=sys.stderr)
        sys.exit(2)
    print("server ready", flush=True)

    pool = get_token_pool(args.port, max(sizes) + 16)
    print(f"token pool: {len(pool)}")

    results = {"label": args.label, "port": args.port, "gen": args.gen, "rows": []}

    if args.mode in ("chat", "both"):
        # realistic prompt: measures the acceptance rate class the official numbers use
        for rep in range(args.repeats):
            try:
                r = run_chat(args.port, args.gen)
            except Exception as e:
                r = {"error": str(e)}
            r["kind"] = "chat"
            r["rep"] = rep
            results["rows"].append(r)
            pf, dc = r.get("prefill_tps"), r.get("decode_tps")
            print(f"  CHAT rep={rep} prompt_n={r.get('prompt_n')} prefill={pf and round(pf,1)} t/s "
                  f"decode={dc and round(dc,2)} t/s acc={r.get('draft_n_accepted')}/{r.get('draft_n')}",
                  flush=True)

    if args.mode == "chat":
        os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
        json.dump(results, open(args.out, "w"), indent=1)
        print(f"wrote {args.out}")
        return

    for n in sizes:
        if n > len(pool):
            print(f"skip {n}: pool too small ({len(pool)})")
            continue
        prompt = pool[:n]
        reps = args.repeats
        if args.repeats_big and n >= args.big_threshold:
            reps = args.repeats_big
        for rep in range(reps):
            try:
                r = run_one(args.port, prompt, args.gen)
            except Exception as e:
                r = {"error": str(e)}
            r["target_n"] = n
            r["rep"] = rep
            # Tag corpus rows too. Chat rows already carry kind="chat"; without this, any consumer that
            # groups on `kind` (the adaptive A/B summary did) silently drops every corpus row, because
            # they had no kind field at all rather than a corpus one.
            r.setdefault("kind", "corpus")
            results["rows"].append(r)
            pf = r.get("prefill_tps")
            dc = r.get("decode_tps")
            acc = r.get("draft_n_accepted")
            dn = r.get("draft_n")
            extra = f" acc={acc}/{dn}" if dn else ""
            print(f"  n={n:>6} rep={rep} prompt_n={r.get('prompt_n')} "
                  f"prefill={pf and round(pf,1)} t/s  decode={dc and round(dc,2)} t/s{extra}",
                  flush=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(results, open(args.out, "w"), indent=1)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
