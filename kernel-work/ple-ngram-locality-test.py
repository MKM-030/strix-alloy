#!/usr/bin/env python3
"""Is the llama-bench slowdown explained by the model's PLE n-gram table?

Hypothesis (from reading src/models/qwen4exp.cpp:1725,1787): each token gathers
ple_n_heads rows of a 27 GiB table, indexed by a hash of the LOCAL N-GRAM
(token-history dependent, `mixed % ple_head_vocab_sizes[h]`).

  - prose:      the same n-grams recur, so gathers hit rows that are already in
                page cache / recently touched -> fast
  - random ids: every n-gram is essentially unique, so every gather touches a
                cold row of a 27 GiB table -> slower

If that is right, the slowdown should track how REPETITIVE the stream is, at the
same token IDs and the same length -- not the ID range. That is testable here
without touching the engine:

  A) fresh random   : unique n-grams      (llama-bench-like)
  B) repeated block : n-grams recur       (prose-like)

Same IDs, same length, same server. If A is materially slower than B, the
comparability problem with `llama-bench` is n-gram locality, not the UCRT's
RAND_MAX -- which would also explain why the restricted-range arm changed
nothing.

Usage: python ple-ngram-locality-test.py --port 8720 --sizes 8192 --repeats 3
"""
import argparse
import json
import os
import random
import statistics
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "bench-corpus.txt")


def http_json(url, payload=None, timeout=7200):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def wait_ready(port, timeout=1800):
    import time
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(3)
    return False


def n_vocab_of(port):
    try:
        p = http_json(f"http://127.0.0.1:{port}/props")
        v = p.get("n_vocab")
        if isinstance(v, int):
            return v
        d = p.get("default_generation_settings")
        if isinstance(d, dict) and isinstance(d.get("n_vocab"), int):
            return d["n_vocab"]
    except Exception:
        pass
    return 248320


def run_one(port, tokens, gen):
    payload = {"prompt": tokens, "n_predict": gen, "cache_prompt": False,
               "temperature": 0.0, "top_k": 1, "top_p": 1.0, "min_p": 0.0, "stream": False}
    r = http_json(f"http://127.0.0.1:{port}/completion", payload)
    t = r.get("timings", {})
    return {"prompt_n": t.get("prompt_n"), "prefill_tps": t.get("prompt_per_second"),
            "decode_tps": t.get("predicted_per_second")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--sizes", default="8192")
    ap.add_argument("--gen", type=int, default=64)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if not wait_ready(args.port):
        raise SystemExit("server not ready")

    sizes = [int(s) for s in args.sizes.split(",") if s]
    need = max(sizes) + 64
    n_vocab = n_vocab_of(args.port)
    print(f"n_vocab: {n_vocab}")

    rnd = random.Random(4242)

    # A) fresh random, full vocabulary -- every trigram unique
    fresh = [rnd.randrange(0, n_vocab) for _ in range(need)]

    # B) repeated block -- same ID range, same length, but n-grams recur heavily.
    #    512 distinct IDs cycled, so only ~512 distinct trigrams exist in the whole stream.
    block = [rnd.randrange(0, n_vocab) for _ in range(512)]
    repeated = (block * (need // len(block) + 1))[:need]

    # C) real prose, full vocabulary -- natural token statistics (the control)
    if os.path.exists(CORPUS):
        text = open(CORPUS, "r", encoding="utf-8", errors="ignore").read()
        prose = http_json(f"http://127.0.0.1:{args.port}/tokenize", {"content": text})["tokens"]
    else:
        prose = fresh

    for label, s in (("fresh-random", fresh), ("repeated-blk", repeated), ("prose", prose)):
        tri = {(s[i], s[i + 1], s[i + 2]) for i in range(min(len(s), need) - 2)}
        print(f"  {label:<14} len={len(s):<8} distinct trigrams in stream={len(tri)}")

    results = {"n_vocab": n_vocab, "rows": []}
    for label, pool in (("fresh-random", fresh), ("repeated-blk", repeated), ("prose", prose)):
        for n in sizes:
            if len(pool) < n:
                print(f"skip {label} n={n} (pool {len(pool)})")
                continue
            prompt = pool[:n]
            for rep in range(args.repeats):
                try:
                    r = run_one(args.port, prompt, args.gen)
                except Exception as e:
                    r = {"error": str(e)}
                r.update(dist=label, target_n=n, rep=rep)
                results["rows"].append(r)
                pf = r.get("prefill_tps")
                print(f"  {label:<14} n={n:>6} rep={rep} prefill={pf and round(pf,1)} t/s", flush=True)

    json.dump(results, open(args.out, "w"), indent=1)

    print("\n=== warm reps only ===")
    print(f"  {'size':>7} {'fresh-rand':>11} {'repeat-blk':>11} {'prose':>9}")
    for n in sizes:
        vals = {}
        for label in ("fresh-random", "repeated-blk", "prose"):
            v = [r["prefill_tps"] for r in results["rows"]
                 if r.get("dist") == label and r.get("target_n") == n
                 and r.get("rep", 0) >= 1 and r.get("prefill_tps")]
            vals[label] = statistics.median(v) if v else None
        if vals["fresh-random"] and vals["repeated-blk"]:
            d = 100 * (vals["fresh-random"] - vals["repeated-blk"]) / vals["repeated-blk"]
            print(f"  {n:>7} {vals['fresh-random']:>11.1f} {vals['repeated-blk']:>11.1f} "
                  f"{(vals['prose'] or 0):>9.1f}   fresh vs repeated: {d:+.1f}%")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
