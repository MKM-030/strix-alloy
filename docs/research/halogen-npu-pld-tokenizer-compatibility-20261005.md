# Exact compact-proposer tokenizer comparison — 5 October 2026

**The shared token map is exact; complete raw tokenizer equality is false.** Every one of the 248,044 base token IDs and every shared added-token ID has identical token-string UTF-8 bytes. All 247,587 ordered BPE merges and encoding/decoding settings match. The target defines seven additional audio/TTS special IDs that the prepared candidate's `tokenizer.json` omits. Its `tokenizer_config.json` declares those same seven IDs and metadata, so full equality is conditional on the loader registering them faithfully. Installed FLM registration behavior was not executed or qualified.

This is the requested executed finite comparison for the [compact proposer plan](halogen-npu-compact-pld-proposer-plan-20261005.md), with [machine-readable proof](halogen-npu-pld-tokenizer-compatibility-20261005.json). The task retained its 20261005 filename across local midnight; the evidence records its actual UTC creation time.

## Artifact pins and acquisition

The target source is `C:\AI\models\halogen-flashnext\tokenizer`. The selected package is **FastFlowLM/Qwen3.5-0.8B-NPU2**, branch **`flm_q4k_high_precision`**, resolved by the official Hugging Face revision API to immutable commit **`1d16e5eaa2508889fb88eb1bfab1921a30a1a466`**. Downloads used [that commit](https://huggingface.co/FastFlowLM/Qwen3.5-0.8B-NPU2/tree/1d16e5eaa2508889fb88eb1bfab1921a30a1a466), not public `main`.

| Source | Bytes | SHA-256 |
|---|---:|---|
| Target `tokenizer.json` | 12,809,320 | `0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3` |
| Prepared `tokenizer.json` | 12,807,982 | `5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42` |
| Target `tokenizer_config.json` | 17,928 | `b11349aafa7cdc6a320767cf7ceb29ed82f7eda5d65e8e0819e76f0ce947bf27` |
| Prepared `tokenizer_config.json` | 16,788 | `485aad30cae5f2280d6050a01f9160c435ee5aeabaf4fda7dd59b76ccc8b1f4c` |

A filename/blob search of local model/runtime and Hugging Face caches found no pinned candidate. Eight discovered tokenizer files were checked for the pinned length, with hashing of same-sized candidates. Only revision metadata, tokenizer, tokenizer configuration, model configuration and chat-template text were retrieved into the new owned directory `server/.local/optimization9h-20261004/token-map-94d0d53b1f8742c68e5520b6bebc962a`. Payload limits were 16 MiB for tokenizer, 128 KiB per small text file and 2 MiB for revision metadata, with a 180-second acquisition deadline. All selected text files matched the installed cached SHA/length or Git-blob/length pins. No language/vision weights were retrieved. The standard-library comparison script and raw text remain in that directory; no HF CLI workflow was used.

## Exhaustive semantic result

| Comparison | Result |
|---|---|
| Base vocabulary | 248,044 entries each; zero missing, extra, duplicate-ID or ID/string-byte differences |
| Shared entire defined map | 248,070 shared IDs checked; zero ID/string-byte differences |
| Added-token metadata | 26 common records identical in content, ID, `single_word`, `lstrip`, `rstrip`, `normalized` and `special`; seven target-only records |
| Ordered merges | 247,587 each; zero pair/order differences; raw JSON representation also identical |
| Tokenizer components | Version, truncation, padding, normalizer, pre-tokenizer, post-processor and decoder identical |
| BPE settings | Type, dropout, unknown-token handling, subword prefixes/suffixes, `fuse_unk`, `byte_fallback` and `ignore_merges` identical |
| Other top-level tokenizer fields | Zero differences |
| Tokenizer configuration | Only two differing fields: `chat_template` and candidate-only `eos_token_id` list `[248044,248046,248048]` |

The case-sensitive JSON parser rejects duplicate keys in both tokenizer and tokenizer-configuration files. Token strings were encoded strictly as UTF-8 and compared at every shared ID; the proof also hashes sorted `(uint32 ID, uint32 UTF-8 length, UTF-8 token-symbol bytes)` records. The base-map digest is **`3637b1a115b34b1791c6f639496208b558476d6cd0a8f4592040a8e4a6c6e925`** for both. The identical ordered-merge digest is **`f73216a68eea59796c4f48025952a9a19c277c3b7a2d8af202591301ec229c15`**. These are token-symbol bytes; decoded text equivalence also depends on the identical serialized decoder and matching call options.

The seven target-only raw added IDs are:

| ID | Token |
|---:|---|
| 248070 | `<\|audio_start\|>` |
| 248071 | `<\|audio_end\|>` |
| 248072 | `<tts_pad>` |
| 248073 | `<tts_text_bos>` |
| 248074 | `<tts_text_eod>` |
| 248075 | `<tts_text_bos_single>` |
| 248076 | `<\|audio_pad\|>` |

All seven have `special=true`, `normalized=false`, and false word/strip flags. The target raw defined set is exactly **0–248076** (248,077 IDs); the candidate raw defined set is exactly **0–248069** (248,070 IDs). For a 248,320-row head, raw target IDs **248077–248319** (243 IDs) and raw candidate IDs **248070–248319** (250 IDs) are undefined by their respective tokenizer JSON. Neither file defines an out-of-head ID. A `<248320` check alone is insufficient.

## Conditional full compatibility and encoding/decoding scope

Both tokenizer configurations contain **33 identical `added_tokens_decoder` records**. The target's records all agree with its raw tokenizer; seven candidate records are absent from its raw tokenizer. The executed comparison derived the candidate map after registering every configuration record at its declared ID: all **248,077** target IDs/string bytes and all 33 added metadata records then match exactly. Its full-map digest equals the target's **`1ea47dc65bdc42fb4bfacda3f3f2b60ca6e996c8a71331edafc9c5e7d0dd2a2a`**. This is a configuration-completion proof, not an observation of a loader doing that registration.

Without qualified registration, direct IDs **0–248069** have exact shared serialized meanings. Text encoding can agree under the same tokenizer implementation and call options when none of the seven omitted literal special-token strings participates in added-token matching. Arbitrary text containing those strings and decoding IDs 248070–248076 require the full registration condition. Special-token allowance, insertion/skipping, cleanup, truncation and padding options must also match. No tokenizer runtime encode/decode calls or model runtime imports were made.

Chat-template content changes prompt construction; it is not a base-map or merge change. The packaged external template also differs from the inline templates. The extra candidate EOS list is stopping metadata and must not replace Halogen's native stop/EOS rules. A raw-ID proposer should consume committed target IDs directly and bypass candidate chat templates and text re-encoding. Its first bounded scope can decline any prefix or proposal containing IDs outside the qualified shared set until registration is established.

The pinned model `config.json` has duplicate conflicting `model_type` entries (`qwen3_5`, `qwen3_5_text`). The first strict parse rejected this small metadata file; the repaired offline comparison records both values and uses only its independently unique `vocab_size=248320`. Downloaded files were reused with pins rechecked. This does not resolve the package loader's interpretation or establish installed DLL compatibility.

**Readiness:** the ordinary shared token-ID mapping obstacle is removed by an exhaustive comparison, with a precise seven-special-token condition. Complete installed-runtime tokenization remains conditional; language weights, accepted-prefix state transactions and live injection remain unqualified. The native seam remains hit-only/static, and no speed or acceptance result follows. Only new evidence/document files and the owned comparison directory changed; the original server, continuation and previous documents were untouched.
