#!/usr/bin/env python3
"""verify-width-equivalence.py — the handover's A0 test (one arm per run).

Speculative decoding is defined to be OUTPUT-EQUIVALENT to serial greedy decoding.
  serial decode   : target sees 1 token row at a time  -> indexer ne11 = 4
  n-max 1 (verify): target sees 2 rows                 -> indexer ne11 = 8   (still MMVF)
  n-max 2 (verify): target sees 3 rows                 -> indexer ne11 = 12  (DIFFERENT kernel)
So if the wide-verify path selects different indexer rows (or reduces differently), the
SPECULATIVE output can diverge from serial greedy output on identical input.

This script drives ONE server (one arm) and emits the raw greedy token stream for each
prompt size. The serial arm (no drafter) is the reference; the spec arm (-md head, n-max 2)
must reproduce it token-for-token. Comparison across arms is done by the driver
(width-equivalence.ps1) against these emitted token lists -- NOT within a single arm, which
would be trivially identical and therefore meaningless.

A mismatch is a correctness signal. It is NOT automatically a bug -- near-tie floating-point
differences can also do it -- so we report the FIRST DIVERGENCE POSITION and surrounding
token context, not just a boolean.

usage: verify-width-equivalence.py --port P --sizes 1024,8192 --gen 200 --label serial --out x.json
"""
import argparse
import hashlib
import json
import os
import urllib.request

HERE_DIR = os.path.dirname(os.path.abspath(__file__))

# The corpus is read by whichever python is invoked. Windows python cannot resolve a
# /mnt/c WSL path, so prefer the copy beside this script and fall back to the WSL mount.
CORPUS_CANDIDATES = [
    os.path.join(HERE_DIR, "bench-corpus.txt"),
    "/mnt/c/Projects/REV-N-ornith-eval-20260911/kernel-work/bench-corpus.txt",
    "C:/Projects/REV-N-ornith-eval-20260911/kernel-work/bench-corpus.txt",
]


def resolve_corpus():
    for p in CORPUS_CANDIDATES:
        if os.path.isfile(p):
            return p
    raise FileNotFoundError("bench-corpus.txt not found in: " + ", ".join(CORPUS_CANDIDATES))


def post(url, payload, timeout=7200):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def tokenize(port, text):
    return post(f"http://127.0.0.1:{port}/tokenize", {"content": text}).get("tokens", [])


def gen(port, prompt, n_predict, seed, ignore_eos=True, n_probs=12):
    """Greedy generation; return (token_ids, text, probs).

    cache_prompt=False so the prompt is always fully re-evaluated and no stale KV from a
    prior call can leak into the result. ignore_eos=True forces a full-length trajectory:
    without it a chat corpus prompt can stop after 2 tokens on the end-of-turn marker,
    which makes the comparison vacuous.

    n_probs > 0 asks the server for the top-N logprobs at every generated position. That is
    the discriminator between a benign near-tie (two tokens within float noise of each other,
    so a different reduction order legitimately flips the argmax) and a gross divergence
    (one token is strongly preferred). probs[i] is {token_id: logprob} for position i.
    """
    payload = {
        "prompt": prompt,
        "n_predict": n_predict,
        "temperature": 0.0,
        "top_k": 1,          # pure greedy
        "top_p": 1.0,
        "min_p": 0.0,
        "seed": seed,
        "cache_prompt": False,
        "return_tokens": True,
        "ignore_eos": ignore_eos,
        "stream": False,
        "n_keep": 0,
    }
    if n_probs > 0:
        payload["n_probs"] = n_probs
    r = post(f"http://127.0.0.1:{port}/completion", payload)
    toks = r.get("tokens") or []
    probs = []
    for entry in r.get("completion_probabilities") or []:
        row = {}
        for tp in entry.get("top_logprobs") or []:
            row[tp["id"]] = tp["logprob"]
        probs.append(row)
    return toks, r.get("content", ""), probs


def build_prompt(port, corpus, size, start=0, wrap=None):
    """Return text that tokenizes to exactly `size` tokens (best effort, bounded).

    `start` slices the corpus so different content can be selected at the SAME token length
    (this separates 'dense-attention regime' from 'unlucky prompt content' as the cause of a
    divergence). `wrap` is an optional fixed prefix instruction, applied identically in every
    arm so the comparison stays byte-for-byte valid.
    """
    pool = corpus[start:] if start else corpus
    prefix = wrap or ""
    # seed the candidate generously: prefix chars + enough pool for `size` tokens
    cand = prefix + pool[: size * 4]
    toks = tokenize(port, cand)
    if len(toks) > size and toks:
        cand = cand[: max(1, int(len(cand) * size / len(toks)))]
        toks = tokenize(port, cand)
    for _ in range(24):
        if len(toks) == size:
            break
        if len(toks) > size:
            drop = max(8, len(cand) - int(len(cand) * size / len(toks)))
            cand = cand[: len(cand) - drop]
        else:
            add = max(64, (size - len(toks)) * 4 + 64)
            if len(cand) >= len(prefix) + len(pool):
                break
            cand += pool[len(cand) - len(prefix): len(cand) - len(prefix) + add]
        toks = tokenize(port, cand)
    return cand, len(toks)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, required=True)
    ap.add_argument("--sizes", default="1024,8192")
    ap.add_argument("--gen", type=int, default=200)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--repeats", type=int, default=1, help="intra-arm repeated generations (determinism control)")
    ap.add_argument("--n-probs", type=int, default=12, help="top-N logprobs per position (0 = off)")
    ap.add_argument("--label", default="vw")
    ap.add_argument("--out", required=True)
    ap.add_argument("--pool", default=None, help="override path to bench-corpus.txt")
    ap.add_argument("--offset", type=int, default=0, help="corpus byte offset (content variation at fixed size)")
    ap.add_argument("--wrap", default="", help="fixed prefix applied identically in all arms")
    ap.add_argument("--ignore-eos", dest="ignore_eos", action="store_true", default=True,
                    help="force full-length trajectory (default)")
    ap.add_argument("--respect-eos", dest="ignore_eos", action="store_false",
                    help="production-like: allow EOG stop (no ignore_eos EOG bias)")
    args = ap.parse_args()

    pool_path = args.pool or resolve_corpus()
    print(f"[{args.label}] corpus: {pool_path}  offset={args.offset}", flush=True)
    with open(pool_path, "r", encoding="utf-8", errors="ignore") as f:
        corpus = f.read()

    results = []
    for size in [int(s) for s in args.sizes.split(",")]:
        prompt, n = build_prompt(args.port, corpus, size, start=args.offset, wrap=args.wrap)
        print(f"[{args.label}] size={size}: prompt tokenized to {n}", flush=True)

        reps = []
        for r in range(args.repeats):
            toks, txt, probs = gen(args.port, prompt, args.gen, args.seed,
                                   ignore_eos=args.ignore_eos, n_probs=args.n_probs)
            d = hashlib.sha256(",".join(str(t) for t in toks).encode()).hexdigest()[:16]
            reps.append({"n": len(toks), "tokens": toks, "token_sha256": d,
                         "probs": probs, "text_head": txt[:120]})
            print(f"  rep{r}: n={len(toks)}  sha={d}  head={toks[:8]}", flush=True)
        # row-level token list = first repeat; the summary carries every repeat's hash
        row = {
            "requested_prompt_tokens": size,
            "prompt_tokens": n,
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()[:16],
            "gen_requested": args.gen,
            "n": reps[0]["n"],
            "tokens": reps[0]["tokens"],
            "probs": reps[0]["probs"],
            "token_sha256": reps[0]["token_sha256"],
            "text_head": reps[0]["text_head"],
            "repeats": [r["token_sha256"] for r in reps],
            "self_consistent": len({r["token_sha256"] for r in reps}) == 1,
        }
        results.append(row)

    with open(args.out, "w") as f:
        json.dump({"label": args.label, "seed": args.seed, "rows": results}, f, indent=1)
    print(f"wrote {args.out}", flush=True)


if __name__ == "__main__":
    main()
