#!/usr/bin/env python3
"""chunk-depth-bench.py — prefill cost of the SAME appended chunk at increasing occupied depth.

Codex's Step 2b, done properly. Comparing average prefill t/s over whole prompts of different lengths
mixes many operating depths together. Instead: prime the KV to depth D, then append a fixed-size chunk
and measure ONLY that chunk's prefill.

Mechanism: llama.cpp prefix caching. Each request uses `cache_prompt: true`.
  prime  : prompt = pool[:D]          -> KV now holds ~D+1 tokens
  measure: prompt = pool[:D+CHUNK]    -> reuses the D-token prefix, processes CHUNK new tokens
The reported `timings.prompt_n` is the number of tokens actually processed, so we can VERIFY the
measurement only covered the chunk (prompt_n should equal ~CHUNK, not D+CHUNK).

Depths ascend so the prime of each step extends the previous KV; the measured work is always exactly
one CHUNK against a genuinely depth-D history.

usage:
  chunk-depth-bench.py --port P --depths 0,32768,65536,131072,200704 --chunk 8192 --repeats 2 --out x.json
"""
import argparse
import json
import os
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
TOKENS = os.path.join(HERE, "bench-tokens.json")


def post(port, payload, timeout=7200):
    req = urllib.request.Request(f"http://127.0.0.1:{port}/completion",
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def run(port, tokens, n_predict=1):
    r = post(port, {
        "prompt": tokens,
        "n_predict": n_predict,
        "cache_prompt": True,     # <-- prefix reuse is the whole point
        "temperature": 0.0,
        "top_k": 1,
        "top_p": 1.0,
        "min_p": 0.0,
        "stream": False,
    })
    t = r.get("timings", {})
    return {
        "prompt_n": t.get("prompt_n"),
        "prompt_ms": t.get("prompt_ms"),
        "prefill_tps": t.get("prompt_per_second"),
        "predicted_n": t.get("predicted_n"),
        "decode_tps": t.get("predicted_per_second"),
        "cache_n": t.get("cache_n"),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--depths", default="0,32768,65536,131072")
    ap.add_argument("--chunk", type=int, default=8192)
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--label", default="chunk-depth")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    pool = json.load(open(TOKENS))
    print(f"token pool: {len(pool)}", flush=True)
    depths = [int(x) for x in args.depths.split(",")]
    chunk = args.chunk
    need = max(depths) + chunk + 8
    if need > len(pool):
        raise SystemExit(f"pool {len(pool)} < needed {need}")

    rows = []
    step = max(depths) + chunk + 4096   # per-rep corpus offset: keeps prefixes independent
    for rep in range(args.repeats):
        off = rep * step
        for D in depths:
            base = off
            # prime to depth D (full prefill on the first pass, cheap extension afterwards)
            pr = run(args.port, pool[base : base + D]) if D > 0 else None
            # measure ONLY the appended chunk against depth-D history
            m = run(args.port, pool[base : base + D + chunk])
            measured = m["prompt_n"]
            row = {
                "depth": D,
                "chunk": chunk,
                "rep": rep,
                "offset": off,
                "processed_tokens": measured,
                "prompt_ms": m["prompt_ms"],
                "chunk_tps": m["prefill_tps"],
                "cache_reused": m.get("cache_n"),
                "prime_ms": None if pr is None else pr["prompt_ms"],
                "looks_like_full_recompute": (measured is not None and measured > chunk + 16),
            }
            rows.append(row)
            print(f"  rep={rep} depth={D:>7} processed={measured} "
                  f"chunk_prefill={m['prefill_tps'] and round(m['prefill_tps'],1)} t/s "
                  f"(cache_n={m.get('cache_n')})"
                  f"{'  <-- FULL RECOMPUTE?' if row['looks_like_full_recompute'] else ''}", flush=True)

    with open(args.out, "w") as f:
        json.dump({"label": args.label, "chunk": chunk, "rows": rows}, f, indent=1)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
