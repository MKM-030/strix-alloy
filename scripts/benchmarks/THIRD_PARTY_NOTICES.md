# Benchmark input attribution

`gufo_prompts.py` extracts the deterministic word generator and task instructions
from `gufo-org/gufo`, `tools/gufo/model_bench/llm.py`, revision
`8eedee6fd904b8e6812f740f777fe84940f341c5`. The rest of the measurement driver
and clock probe are Strix Alloy code.

MIT License

Copyright (c) 2026 gufo contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Article-comparison corpus

The optional article input preparer retrieves public LlamaStash TUI source at
revision `a88808c148aa9c539691238ce06a89d25f6dbb6c` as data, never as executable code.
Those source files are also distributed under the MIT License text above, with:

Copyright (c) 2026 Deepu K Sasidharan

The pinned repository's LICENSE is the authoritative notice. The benchmark's
added fixture records and measurement logic are separate Strix Alloy work.
