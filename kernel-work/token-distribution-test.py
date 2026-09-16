#!/usr/bin/env python3
"""Does the token-ID distribution change prefill throughput?

llama-bench feeds `std::rand() % n_vocab`. On the Windows UCRT RAND_MAX is 32767, so
against this model's 248320-token vocabulary only the first 13.2% of IDs are reachable
(verified with rand-check.c). ilintar's Linux build uses glibc, where RAND_MAX is
2^31-1 and the whole vocabulary is reachable.

Before blaming any of the cross-platform gap on that, test whether the distribution
matters AT ALL. Hold everything constant -- same server, same harness, same prompt
length, same engine -- and vary only which token IDs are in the prompt:

  A) natural  : real token ids from the repo doc corpus (full vocabulary)
  B) low-only : ids drawn from [0, 32768)          (mimics the Windows llama-bench stream)

If A and B prefill at the same rate, the defect is cosmetic for throughput and the
comparability concern is about workload identity only. If they differ, it is a real
confound in the published cross-platform comparison.

Usage: python token-distribution-test.py --port 8700 --sizes 8192,16384 --repeats 3
"""
import argparse
import json
import os
import random
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


def tokenize(port, text):
    return http_json(f"http://127.0.0.1:{port}/tokenize", {"content": text})["tokens"]


def n_vocab_of(port):
    """Ask the server for the vocabulary size rather than hardcoding it."""
    try:
        props = http_json(f"http://127.0.0.1:{port}/props")
        for key in ("n_vocab", "default_generation_settings"):
            v = props.get(key)
            if isinstance(v, int):
                return v
            if isinstance(v, dict) and isinstance(v.get("n_vocab"), int):
                return v["n_vocab"]
    except Exception:
        pass
    return 248320  # known for Qwen3.8-Flash-Next


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
    ap.add_argument("--sizes", default="8192,16384")
    ap.add_argument("--gen", type=int, default=128)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--low-cut", type=int, default=32768,
                    help="upper bound of the restricted stream (UCRT RAND_MAX+1)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if not wait_ready(args.port):
        raise SystemExit("server not ready")

    sizes = [int(s) for s in args.sizes.split(",") if s]
    need = max(sizes) + 16
    n_vocab = n_vocab_of(args.port)
    print(f"n_vocab reported by server: {n_vocab}")

    # --- natural distribution: real tokens from the doc corpus
    if os.path.exists(CORPUS):
        text = open(CORPUS, "r", encoding="utf-8", errors="ignore").read()
    else:
        text = "".join(f"The system measures stage {i} and records throughput. " for i in range(200000))
    natural = tokenize(args.port, text)
    print(f"natural token stream: {len(natural)} ids, "
          f"{len(set(natural))} distinct, max id {max(natural)}")

    # --- restricted distribution: only ids < low_cut, reusing real ids so the *values* are real
    low_pool = [t for t in natural if 0 <= t < args.low_cut]
    if len(low_pool) < need:
        # top up deterministically from the reachable range
        rnd = random.Random(1234)
        low_pool = low_pool + [rnd.randrange(0, args.low_cut) for _ in range(need - len(low_pool))]
    print(f"restricted stream   : {len(low_pool)} ids available from [0,{args.low_cut}), "
          f"{len(set(low_pool))} distinct, max id {max(low_pool)}")

    # --- the EXACT llama-bench shape: uniform pseudorandom ids, not filtered prose. Filtered natural
    # text keeps natural bigram statistics, so it is not a faithful mimic of what llama-bench feeds.
    # Two arms isolate the variable: uniform over the full vocab (what Linux/glibc reaches) vs uniform
    # over [0, low_cut) (what the Windows UCRT can reach).
    rnd = random.Random(20260916)
    uniform_full = [rnd.randrange(0, n_vocab) for _ in range(need + 64)]
    rnd = random.Random(20260916)
    uniform_low = [rnd.randrange(0, args.low_cut) for _ in range(need + 64)]
    print(f"uniform full        : max id {max(uniform_full)} (mimics glibc llama-bench)")
    print(f"uniform low         : max id {max(uniform_low)} (mimics UCRT llama-bench)")

    results = {"port": args.port, "low_cut": args.low_cut, "rows": []}
    arms = (("natural", natural), ("low-only", low_pool),
            ("unif-full", uniform_full), ("unif-low", uniform_low))
    for label, pool in arms:
        if len(pool) < need:
            print(f"skip {label}: pool too small ({len(pool)} < {need})")
            continue
        for n in sizes:
            prompt = pool[:n]
            for rep in range(args.repeats):
                try:
                    r = run_one(args.port, prompt, args.gen)
                except Exception as e:
                    r = {"error": str(e)}
                r.update(dist=label, target_n=n, rep=rep)
                results["rows"].append(r)
                pf = r.get("prefill_tps")
                print(f"  {label:<9} n={n:>6} rep={rep} prompt_n={r.get('prompt_n')} "
                      f"prefill={pf and round(pf,1)} t/s  decode={r.get('decode_tps') and round(r['decode_tps'],2)}",
                      flush=True)

    json.dump(results, open(args.out, "w"), indent=1)

    print("\n=== summary (warm reps only, rep>=1) ===")
    print(f"  {'size':>7} {'natural':>10} {'low-only':>10} {'unif-full':>10} {'unif-low':>10}  low/full")
    for n in sizes:
        row = {}
        for label in ("natural", "low-only", "unif-full", "unif-low"):
            v = sorted(r["prefill_tps"] for r in results["rows"]
                       if r.get("dist") == label and r.get("target_n") == n
                       and r.get("rep", 0) >= 1 and r.get("prefill_tps"))
            row[label] = v[len(v) // 2] if v else None
        if row["unif-full"] and row["unif-low"] and row["natural"] and row["low-only"]:
            d = 100 * (row["unif-low"] - row["unif-full"]) / row["unif-full"]
            print(f"  {n:>7} {row['natural']:>10.1f} {row['low-only']:>10.1f} "
                  f"{row['unif-full']:>10.1f} {row['unif-low']:>10.1f}  {d:+.1f}%")
    print("\n  low/full compares the two UNIFORM arms -- that is the llama-bench comparability question,")
    print("  since llama-bench feeds uniform pseudorandom ids, not prose.")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
