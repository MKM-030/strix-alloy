Historical design written before the completed CPU run. Current findings are in README.md and evidence/result.json; the adapter remains default off.

# Inactive scalar backend lookup candidate

The completed full Transformers comparison preserved LOOK/cache parity but made
the four changed cold multi-segment cases slower. The next candidate avoids the
HF Python dispatch, attention-mask extraction and BatchEncoding construction for
each existing segment. It calls the same loaded Rust tokenizer scalarly; it does
not batch segments or change their boundaries, lookup IDs, separators or caches.

The actual Transformers 5.15.0 sources show that Qwen2Tokenizer only customizes
initialization. For the lookup's ordinary string call, the base __call__ selects
no padding/truncation, resolves split_special_tokens, and invokes the backend's
_encode_plus. That sends [segment] to Rust encode_batch with special tokens off
and pretokenized false, then copies encoding.ids and builds unused fields.
Qwen's prefix-space handling and postprocessor are already in the loaded Rust
backend; there is no additional Python prefix/suffix preprocessing on this path.

Alternatives considered: HF batching is measured slower and stays disabled;
changing thread settings adds a different intervention and is excluded. Only
scalar backend encoding is prepared here. Rayon overhead is a hypothesis, not a
measured cause of the prior regression.

The candidate defaults off. A one-time positive binding requires the exact three
exported HF source hashes and exact software versions. Each segment additionally
requires the exact Qwen2/native tokenizer/model types, the original shared backend
alias, no Python instance method overrides or input/target-mode hooks, no backend
padding/truncation, deterministic BPE dropout=None, and the backend's special-token
mode equal to the HF default. Unknown conditions use the original scalar HF call.
No backend state is reset or changed. Native errors/malformed results also fall
back. An overlong result falls back so HF's original length warning is preserved.

Only a private generated API copy may be emitted. The first qualification remains
fake interface tests, followed by Root's real CPU-only HF comparison with the
same eight cases and paired timing protocol. A strict type guard intentionally
rejects a counting facade: real direct-path parity must use the genuine HF object.
There is no GPU/NPU, engine tok/s, acceptance, weight or production change here.
Concurrent live tokenizer mutation has not been qualified; this is an isolated
CPU candidate, not a production rollout.
