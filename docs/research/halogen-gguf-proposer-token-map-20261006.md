# Pinned GGUF proposer token-map inspection — 6 October 2026

**Every requested shared token symbol and BPE merge rank matches; complete tokenizer equivalence is not established.** The immutable Q4_0 GGUF agrees with the target at all **248,070 IDs 0–248069** and all **247,587 ordered merges**, with zero byte or rank differences. Six shared added tokens have a different serialized type: GGUF marks them CONTROL while target `tokenizer.json` marks them nonspecial. GGUF does not embed the full Hugging Face tokenizer JSON, so its metadata cannot prove the target's NFC normalization, matching flags, decoder, or call-option behavior.

The executed [machine-readable proof](halogen-gguf-proposer-token-map-20261006.json) includes every metadata key, tensor descriptor, shared added-token record, mismatch and retained setting. Root verified the completed download before inspection. This task then independently rechecked its exact size and SHA-256. No inference runtime was imported, model executed, build performed, or hardware accessed.

## Immutable inputs and method

| Input | Bytes | SHA-256 |
|---|---:|---|
| `ggml-org/Qwen3.5-0.8B-GGUF` / `Qwen3.5-0.8B-Q4_0.gguf` | 563,036,064 | `57d1997790d1744fba5b40a7317df71ea5e2acee28c47e78f0cce39c0703f8cf` |
| Target `tokenizer.json` | 12,809,320 | `0997f410c57a1f4e53b09e4be8f4a172d90edd9564368fb0847030937229b9f3` |

The GGUF pin is [commit `9447f74101aeb4e93621884dfa36ee8effb8831b`](https://huggingface.co/ggml-org/Qwen3.5-0.8B-GGUF/tree/9447f74101aeb4e93621884dfa36ee8effb8831b). Its local path is `C:\AI\models\halogen-proposer-qwen35-08b-gguf-9447f741\Qwen3.5-0.8B-Q4_0.gguf`. The target is `C:\AI\models\halogen-flashnext\tokenizer\tokenizer.json`.

The standard-library helper is `server/.local/optimization9h-20261004/gguf-token-map-20261006/compare_gguf_token_map.py`. No installed `gguf` package was available and none was installed. Its in-memory self-test exercised scalar kinds, UTF-8 strings and numeric/string arrays before the real comparison. The parser rejects duplicate metadata/JSON keys, invalid bounds and nonfinite metadata, reads little-endian metadata/tensor descriptors, and never decodes tensor payloads. Whole-file reading occurs only for the immutable-file SHA check. The final evidence timestamp is recorded in the JSON in UTC; the filename uses the local date.

Token comparison uses exact UTF-8 **token-symbol bytes**, without text decoding or Unicode normalization. Digest records are `(uint32-le ID, uint32-le UTF-8 length, UTF-8 symbol bytes)` in ID order. The identical shared digest is **`79eec923789b6428a38b6654c93c7b7baadfbc03a595a18054199a05a8212130`**. Ordered merge strings are compared exhaustively; the identical digest is **`567625e146a9197c27a7d1a6056fdc2ab46f0e4cd015c996de2e8b2bd289cb60`**, using `(uint32-le rank, uint32-le UTF-8 length, merge bytes)` records.

## Exact differences and boundaries

The target has 248,044 base entries and 33 added entries. GGUF contains 248,320 indexed rows: 248,044 NORMAL, 27 CONTROL, six USER_DEFINED and 243 UNUSED. Within the requested shared set there are 248,044 NORMAL, 20 CONTROL and six USER_DEFINED rows. The GGUF specification defines these indexed symbols and types; it also distinguishes an embedded complete Hugging Face tokenizer from the smaller GGML metadata representation. [Official GGUF specification](https://github.com/ggml-org/ggml/blob/master/docs/gguf.md).

All six type differences are listed here. Their token symbols and numeric IDs still match exactly:

| ID | Symbol | Target added-token `special` | GGUF type |
|---:|---|---|---|
| 248060 | `<\|fim_prefix\|>` | false | CONTROL (3) |
| 248061 | `<\|fim_middle\|>` | false | CONTROL (3) |
| 248062 | `<\|fim_suffix\|>` | false | CONTROL (3) |
| 248063 | `<\|fim_pad\|>` | false | CONTROL (3) |
| 248064 | `<\|repo_name\|>` | false | CONTROL (3) |
| 248065 | `<\|file_sep\|>` | false | CONTROL (3) |

The explicit comparison rule expects NORMAL for target base entries, CONTROL for special added entries, and USER_DEFINED for nonspecial added entries. Therefore these are classification differences between the two serialized representations; they do not change the observed ID/symbol pairs. All six target records also have `normalized=false`, `single_word=false`, `lstrip=false`, and `rstrip=false`. GGUF's type enum does not retain these four matching flags.

The seven additional target audio/TTS IDs **248070–248076** were inspected separately. All seven symbols match the GGUF and all seven GGUF types are CONTROL, agreeing with target `special=true`. Thus all **248,077 target-defined symbol pairs** were actually checked and match; their full defined-map digest is **`1ea47dc65bdc42fb4bfacda3f3f2b60ca6e996c8a71331edafc9c5e7d0dd2a2a`**. This broader symbol observation does not expand the requested proposer admission range or establish complete tokenizer behavior. GGUF rows **248077–248319** are UNUSED and have no target definition; head-row bounds alone must not admit them.

There are no missing/truncated token or merge arrays, no merge-order differences, and no token-symbol differences in either inspected defined range. Six serialized type differences and missing complete tokenizer settings are the material limitations.

## Frozen 512-ID workload membership

The [frozen workload manifest](halogen-independent-proposer-workload-20261006.json), SHA-256 **`1f3a2fbfafe1a8fd90f99c23dac49f3f0028644d5f010fcd057edfcce26a4919`**, was inspected alongside the token map. The helper verified the size, SHA-256 and decoded int32 contents of its seed file and all 15 authoritative replay files, reconstructed each prefix as the last 512 IDs of the seed plus already committed outputs, and checked all 15 prefixes individually. The evidence records each prefix's little-endian int32 SHA-256. No future replay labels were supplied to a proposer or model.

All **7,680 prefix ID occurrences**, covering **177 distinct IDs** between **11 and 248069**, lie in the admitted shared range. The prefixes contain four added tokens, each with a matching serialized class:

| ID | Symbol | Target class | GGUF type |
|---:|---|---|---|
| 248045 | `<\|im_start\|>` | special | CONTROL (3) |
| 248046 | `<\|im_end\|>` | special | CONTROL (3) |
| 248068 | `<think>` | nonspecial added | USER_DEFINED (4) |
| 248069 | `</think>` | nonspecial added | USER_DEFINED (4) |

None of the six type-mismatch IDs **248060–248065** occurs in any frozen prefix. None of the excluded audio/TTS or UNUSED rows occurs. All **37 committed update IDs** are within the shared range and contain no added-token or type-mismatch IDs. Accordingly, the six classification differences do **not** block the metadata admission of these already-frozen numeric IDs, when passed directly to tensor input and predictions are kept as raw IDs. This qualification includes the two matching CONTROL tokens actually present; describing the entire prefix as ordinary text tokens would be inaccurate.

This is a raw ID/symbol and classification membership gate. It does not qualify complete text tokenization or decoding, unseen future proposals, numerical model behavior, execution support, acceptance, speed, state transactions, or live target injection. Admission remains **0–248069** even though the seven additional defined symbols also match.

## Retained tokenizer settings

The GGUF retains only these scalar tokenizer settings:

| Metadata key | Value |
|---|---|
| `tokenizer.ggml.model` | `gpt2` |
| `tokenizer.ggml.pre` | `qwen35` |
| `tokenizer.ggml.eos_token_id` | 248046 |
| `tokenizer.ggml.padding_token_id` | 248044 |
| `tokenizer.ggml.add_bos_token` | false |

It retains tokens, token types and merges. It has no `tokenizer.huggingface.json` or chat template. The target explicitly serializes NFC normalization, a regex Split followed by ByteLevel pretokenization, ByteLevel decoding, BPE options, added-token flags, and padding/truncation/post-processing components. The `qwen35` pretokenizer label is an implementation dispatch name, not an embedded proof that each target component is identical. No runtime encoding, decoding, special-token skipping, literal added-token recognition or prompt construction was tested. Candidate EOS/padding metadata must not replace the target's native stopping/prompt policy by inference.

## Architecture and quantization metadata

The file parses as GGUF v3, little endian, with **41 metadata entries and 320 tensors**. Metadata records architecture **`qwen35`**, model **Qwen3.5 0.8B**, 24 blocks, embedding length 1024, FFN length 3584, eight attention heads, two KV heads, key/value length 256, full attention every four layers, and training context length 262144. The latter is model metadata, not a promise of the bridge's configured context or memory use.

`general.file_type=2` denotes MOSTLY_Q4_0 and `general.quantization_version=2`; the actual directory is mixed: **186 Q4_0 tensors, 133 F32 tensors, and one Q8_0 tensor**. The Q8_0 tensor is `token_embd.weight`, dimensions **[1024, 248320]** in GGUF order. `output_norm.weight` is F32 [1024]; no independent `output.weight` descriptor is present. The directory contains 752,393,024 tensor elements. The official format constants provide the type numbers and F32/Q4_0/Q8_0 block byte sizes used for extent checks. [Official gguf-py constants](https://raw.githubusercontent.com/ggml-org/llama.cpp/master/gguf-py/gguf/constants.py).

The metadata ends at byte 10,942,704; tensor descriptors end at 10,961,541; aligned tensor data starts at 10,961,568. Every tensor extent calculated from its dimensions/type lies within the pinned file, with no overlap, gap between payload extents, or trailing bytes. The final extent ends exactly at **563,036,064**. These structural checks detect no truncation. Tensor contents, numerical accuracy, tied-output interpretation and runtime model support were not evaluated.

**Disposition:** exhaustive raw ID/symbol compatibility passes for the requested 0–248069 range, ordered BPE merges pass, and the actual frozen 15-prefix workload passes symbol/range/classification membership. Full serialized tokenizer equality fails the six classification comparisons and cannot be established for settings omitted from GGUF. This removes the metadata obstacle to direct interchange of the inspected frozen IDs; it supplies no acceptance, performance, state-transaction, numerical or live-injection result.
