# CPU-first code lookup prototype

The prototype returns source locations directly for a locate-only task. It uses no main-model request, semantic model, provider runtime, GPU/NPU session, or serving API. Its possible value is task completion time or an avoided model request after quality evaluation; it establishes no direct prefill/decode gain.

The frozen eligible envelope is all52 Git-tracked Python files under server/ and backends/halogen-wsl2-0.17.3/scripts/, including tracked test sources. It excludes .local, hidden/cache/private-data directories, private*.py (including private_hsa.py), credential file names and any symlink/junction/reparse escape. File contents are read only after this filter. Indexing does not scan the home directory, recurse through other trees, read untracked files, or execute source files.

The CPU index has248 bounded chunks and no oversized-line omissions in the current corpus. Each chunk is at most32 complete lines and8192 UTF-8 excerpt bytes. A SHA256 binds the complete source file; chunk identity binds version/path/source hash/exact inclusive span; the generation binds the whole canonical index. Build rechecks the source inventory and all hashes before one atomic adjacent-file replacement. It refuses a source over1,000,000 bytes rather than silently selecting a convenient subset.

Every query checks the entire frozen tracked inventory and all source SHA256 values. A changed, absent, newly selected or unreadable source returns stale_index with no excerpts and rebuild_required=true. It does not return cached old source text. Exact whole-query identifiers and relative paths lead the ranking, then BM25 (k1=1.2,b=0.75) ranks at most12 positive candidates with deterministic ties. At most3 source excerpts are re-read and hash-checked immediately before return. Excerpts preserve source line endings and the exact one-based inclusive line span.

Result statuses are ok, ambiguous, no_match, stale_index and invalid_index. Ambiguous means multiple exact locations or a top lexical-score tie; it does not attempt semantic ambiguity calibration. No_match means an empty/invalid query or no positive lexical match. A lexical match does not prove the question is answerable. lookup_sufficient=null explicitly leaves that judgment unresolved. main_model_called is always false. The result includes the full <=12 metadata shortlist so root can measure candidate recall separately from top3 source-location precision.

The default-off Reranker protocol is a future same-model adapter slot. Only explicit enable_provider=true plus an adapter with model/tokenizer/preprocessing SHA256 identity can call it. No provider can be enabled from this CLI. GPU-busy, missing adapter, failed adapter or invalid scores yields a tagged CPU fallback. No CPU semantic, GPU or NPU reranker was called by this implementation/probe. An enabled callback’s success would not by itself qualify provider placement or hardware attribution; raw reranker scores are rankings, not correctness probabilities. Root owns graph/preprocessing admission, same-model CPU/NPU comparison, and future hardware work.

PowerShell commands (Python standard library only):

```powershell
$lookupWork = 'C:/Projects/strix-alloy-clean/server/.local/optimization9h-20261004/halogen0172-backend-preparation-20261008/npu-code-lookup-cpu-20261009'
python -B "$lookupWork/code_lookup.py" build --repo 'C:/Projects/strix-alloy-clean' --index "$lookupWork/index.json" --output "$lookupWork/build-result.json"
python -B "$lookupWork/code_lookup.py" query --repo 'C:/Projects/strix-alloy-clean' --index "$lookupWork/index.json" --query 'server/gateway.py' --output "$lookupWork/path-smoke-result.json"
python -B "$lookupWork/test_code_lookup.py"
```

Build/query require explicit --repo and --index. Index/output writes are confined to this isolated work directory. Query CLI exit3 means stale/invalid index, exit2 means a caught command error; ok/ambiguous/no_match return exit0 with explicit JSON status. There is no automatic rebuild, network access, model fallback, indexing worker, serving integration, or change to an engine default.

Python API:

```python
index = code_lookup.build_index(repo, index_path)
index = code_lookup.load_index(index_path)
result = code_lookup.lookup(index, query, repo=repo)
# Optional future slot: reranker=adapter, enable_provider=True, gpu_busy=False.
```

Each top3 item returns path, start_line, end_line, excerpt, source_sha256, chunk_id, index_generation, ranking_method, bm25_score and exact identifier line matches. Shortlist entries carry the same path/span/hash/generation identity without excerpt text. Source-file/hash freshness is separate from the index-file generation integrity check. Oversized single-line omissions, when present, are explicit in the index/build receipt.

Four meaningful filesystem correctness cases passed: exact identifier/span/hash with .local exclusion; stale modified source refusal; ambiguous identifier and no-match status; and provider default-off. Tests replace only approved-root/Git-inventory discovery for real filesystem fixtures confined to this work directory, avoiding Git mutation. The missing-feature red run was observed first. Fixture bytes explicitly use LF so Windows newline translation does not alter the independent literal expectation; actual source excerpt line endings remain preserved. test-receipt.json binds the test and implementation source hashes, and test-output.txt retains the scoped result. The full project test suite was not run under the explicitly CPU-only isolated probe scope.

The real corpus build and a gateway relative-path query succeeded with the provider disabled and no model call. These are correctness smoke observations, not timed retrieval benchmarks or held-out quality results. No frozen questions or truth were inspected, no thresholds were tuned, and root owns the independent16-question evaluation. The current CPU lexical ranking may miss intent, prefer a mention over a definition, or lack calibrated abstention; the shortlist and exact citations make those limits measurable.

Files: design.md (design first), code_lookup.py (CLI/API), test_code_lookup.py and test-receipt.json (four cases), index.json (frozen corpus generation), build-result.json and path-smoke-result.json (CPU smoke receipts), source-freeze.json and result.json (source/corpus bindings and scope). No tracked source, hardware, API, lifecycle, package/model installation, Git staging or commits were changed or performed.
