# Frozen authored code-location questions

This dataset contains 16 agent-authored questions: 6 clear intent, 4 exact identifier/path, 3 ambiguous, and 3 out-of-scope no-answer questions. It is a curated source-grounded pilot, not a real human benchmark.

Only current tracked Python files under `server/` and `backends/halogen-wsl2-0.17.3/scripts/` are eligible. `eligible-corpus.json` explicitly freezes the 52-file envelope with raw content SHA256 hashes; `.local`, untracked files, private paths/basenames, non-Python files, and reparse paths are excluded. Tracked test source remains eligible, but was never executed.

`selected-files.json` lists the 14 production source files that supply the 17 ground-truth locations. Every selected file is in the eligible envelope. Questions alone are in `questions.json`; answers and source excerpts are separately retained in `ground-truth.json`.

Each answer span has an inclusive, 1-based file line range and enclosing function scope. Ambiguous questions deliberately leave two or three control-family/source-copy alternatives open. They require acknowledging that ambiguity and presenting the listed plausible alternatives. No-answer questions request React UI, native HIP kernel, or PostgreSQL migration implementations outside this Python corpus.

Raw file content hashes bind the source snapshot. Excerpt hashes bind UTF-8 text with LF line separators and no terminal newline, as documented in the truth file. Source hashes must still match when root evaluates; changed files require a stale result rather than silent source substitution.

Question wording and truth were completed without running or inspecting the retrieval prototype or its outputs. No hardware, API, model, download, test, or Git mutation was performed. The pre-evaluation question payload, truth, allowlists, and this note are bound together by `freeze.json`.

Do not modify this frozen payload or truth after evaluating it. Any later dataset must use a new version/location and remain separately reported.
