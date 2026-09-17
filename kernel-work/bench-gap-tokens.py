#!/usr/bin/env python3
"""Resolve the llama-bench vs server "harness gap": is it the harness, or the tokens?

Review item 3 asked for the same stored token array through both entry points. That is not
directly possible -- llama-bench generates its own prompt internally with `std::rand()` and
offers no way to inject tokens. But the *inverse* experiment answers the same question:

  if the server, fed llama-bench's own token distribution, reproduces llama-bench's number,
  then the "gap" is the token workload, not harness overhead.

Design, all in ONE server session so session drift cannot confound it:
  - prose      : real token IDs, the workload our published served numbers use
  - random-a/b/c : uniform pseudorandom IDs, three independent draws -- i.e. llama-bench's
                   distribution class, and also a measure of draw-to-draw variance

If random-token prefill lands near the llama-bench figure (~892 t/s at 16k) while prose sits
~990-1040, the discrepancy is explained by the workload. The spread across the three random
draws also tells us how much of llama-bench's ± value is really draw noise.

Usage: python bench-gap-tokens.py --port 8780 --size 16384 --repeats 3
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
    except Exception:
        pass
    return 248320


def run_one(port, tokens, gen):
    payload = {"prompt": tokens, "n_predict": gen, "cache_prompt": False,
               "temperature": 0.0, "top_k": 1, "top_p": 1.0, "min_p": 0.0, "stream": False}
    r = http_json(f"http://127.0.0.1:{port}/completion", payload)
    t = r.get("timings", {})
    return t.get("prompt_n"), t.get("prompt_per_second")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--size", type=int, default=16384)
    ap.add_argument("--gen", type=int, default=32)
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    if not wait_ready(args.port):
        raise SystemExit("server not ready")

    need = args.size
    nv = n_vocab_of(args.port)
    print(f"n_vocab={nv}  size={args.size}  repeats={args.repeats}")

    prose = None
    if os.path.exists(CORPUS):
        text = open(CORPUS, "r", encoding="utf-8", errors="ignore").read()
        toks = http_json(f"http://127.0.0.1:{args.port}/tokenize", {"content": text})["tokens"]
        if len(toks) >= need:
            prose = toks[:need]

    arms = {}
    if prose:
        arms["prose"] = prose
    for tag in ("a", "b", "c"):
        rnd = random.Random(hash(tag) & 0xFFFF)
        arms[f"random-{tag}"] = [rnd.randrange(0, nv) for _ in range(need)]

    print(f"  distinct ids: prose={len(set(prose)) if prose else '-'} "
          + " ".join(f"{k}={len(set(v))}" for k, v in arms.items() if k != "prose"))

    rows = []
    for label, pool in arms.items():
        vals = []
        for rep in range(args.repeats):
            try:
                pn, pf = run_one(args.port, pool, args.gen)
            except Exception as ex:
                print(f"  {label} rep{rep}: FAILED {ex}")
                continue
            rows.append({"arm": label, "rep": rep, "prompt_n": pn, "prefill_tps": pf})
            if rep >= 1:
                vals.append(pf)
            print(f"  {label:<10} rep{rep} prompt_n={pn} prefill={pf and round(pf,1)} t/s", flush=True)
        if vals:
            print(f"    -> median(warm) = {statistics.median(vals):.1f} t/s")

    json.dump({"size": args.size, "rows": rows}, open(args.out, "w"), indent=1)

    print("\n=== summary (warm reps) ===")
    print(f"  {'arm':<10} {'median':>9} {'min':>9} {'max':>9}")
    med = {}
    for label in arms:
        v = [r["prefill_tps"] for r in rows if r["arm"] == label and r["rep"] >= 1 and r["prefill_tps"]]
        if not v:
            continue
        med[label] = statistics.median(v)
        print(f"  {label:<10} {statistics.median(v):>9.1f} {min(v):>9.1f} {max(v):>9.1f}")

    rnds = [m for k, m in med.items() if k.startswith("random-")]
    if prose and rnds and "prose" in med:
        rmed = statistics.median(rnds)
        print(f"\n  prose {med['prose']:.1f}  vs  random median {rmed:.1f} "
              f"({100*(rmed-med['prose'])/med['prose']:+.1f}%)")
        print(f"  random draw-to-draw spread: {min(rnds):.1f} .. {max(rnds):.1f} "
              f"({100*(max(rnds)-min(rnds))/statistics.median(rnds):.1f}% of median)")
        print(f"\n  llama-bench pp16384 on this box = 892.59 t/s")
        print(f"  server + random tokens (median) = {rmed:.1f} t/s  "
              f"-> {100*(rmed-892.59)/892.59:+.1f}% vs llama-bench")
        print(f"  server + prose tokens           = {med['prose']:.1f} t/s  "
              f"-> {100*(med['prose']-892.59)/892.59:+.1f}% vs llama-bench")
    print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
