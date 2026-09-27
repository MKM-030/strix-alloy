# GUFO Finite Parser Fixture Characterization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Verify the exact raw malformed-input recipes for the finite live test against the existing production parser and route adapter without a model.

**Architecture:** Extend the existing CPU-only route-policy test in the isolated helper checkout. Reuse its fake backend and real JSON/OpenAI adapters; change no production behavior. The finite controller and full request schedule remain separate deliverables.

**Tech Stack:** Existing C++/CMake/CTest, pinned native Windows clang24, HIP OFF, clang-format19.1.5.

## Global Constraints

- Preserve working installations and unrelated changes. Native Windows and WSL2 are acceptable; dual boot is not.
- Preserve49GiB available physical before model launch,24GiB runtime physical,12GiB commit reserve. This task authorizes no model launch.
- No BIOS/carve/VGM/driver/services/security/pagefile settings, reboot, D:, publication or unrelated process termination.
- Work only in `C:/Projects/strix-alloy-research/engine/gufo-lifecycle-fixture`, branch `codex/service-lifecycle-fixture`, original task BASE `b46393cc62fe9855987ee50f40cb397b23fb6cdc`.
- Frozen production `engine/gufo-ar4k-header-cap` remains clean at `e6feed7ca52df4661d10434c72a8ea5b5f054bc2`. No production source, helper implementation, first-six fixture, build/runtime pins, acceptance, recovery markers or evidence changes.
- Only `tests/cli/text_request_policy_routes_test.cpp` changes. No new test framework, dependency, CMake target, socket, metadata/helper/model/GPU invocation or compiler acquisition.
- Use existing CPU build `C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927`, HIP OFF, two build jobs, fresh24GiB available RAM and25GiB free C: checks.
- This is characterization of existing behavior, not a missing-feature implementation: new tests may pass immediately. Do not invent a RED by using wrong expected values or modifying production behavior. Unexpected failures require diagnosis before any broader change.

## Task 1: Freeze malformed parser boundary behavior

**Files:** Modify only `tests/cli/text_request_policy_routes_test.cpp` in the component checkout; report outside the checkout at `C:/Projects/strix-alloy-research/reports/gufo-finite-parser-fixtures-implementation-20260927.md`.

**Interfaces:** Existing anonymous-namespace `PolicyBackend`, `Chat(std::string)` and `Expect(bool,std::string_view)`. Existing `HandleOpenAiChat`, `json::parse`, response.status/body/streaming_body. `PolicyBackend` is not final; a local subclass can return the actual served alias without changing existing tests.

- [ ] Step1 — inspect identity and baseline evidence.

Verify clean branch/BASE. The unchanged route target passed in the previous two-test run at this exact BASE; its raw log is `build/gufo-lifecycle-fixture-cpu-20260927/Testing/Temporary/LastTest.log`. Read that existing baseline evidence instead of rerunning an unchanged test. Confirm the helper executable still hashes `1D21C3112795C7849A0E1F9E19068BFBEE64C578BF0613FA8CBAB352B9FC46DB`. Read AGENTS.md and the negative contract `reports/gufo-lifecycle-negative-fixture-contract-20260927.md`.

- [ ] Step2 — add the following characterization function before the anonymous namespace closes, then add `TestFiniteParserFixtures();` before `return0` in main.

```cpp
void TestFiniteParserFixtures() {
  class LifecycleBackend final : public PolicyBackend {
  public:
    std::string model_id() const override { return "gufo-flash-next"; }
  };
  const std::string baseline =
      R"({"model":"gufo-flash-next","messages":[{"role":"user","content":"x"}],"max_tokens":1,"cache_prompt":false,"chat_template_kwargs":{"enable_thinking":false,"preserve_thinking":false},"temperature":0,"stream":false})";
  const std::string nested_prefix =
      R"({"model":"gufo-flash-next","messages":)";
  const std::string nested_suffix =
      R"(,"max_tokens":1,"cache_prompt":false,"chat_template_kwargs":{"enable_thinking":false,"preserve_thinking":false},"temperature":0,"stream":false})";
  const auto nested = [&](std::size_t arrays) {
    return nested_prefix + std::string(arrays, '[') + "0" +
           std::string(arrays, ']') + nested_suffix;
  };
  std::string invalid_utf8 = baseline;
  const auto content_at = invalid_utf8.find("\"content\":\"x\"");
  Expect(content_at != std::string::npos, "raw UTF8 fixture anchor exists");
  invalid_utf8[content_at + std::string_view{"\"content\":\""}.size()] =
      static_cast<char>(0xc0);
  const auto duplicate = baseline.substr(0, baseline.size() - 1) +
                         ",\"max_tokens\":1}";
  struct Case { std::string body; std::string_view error_code; };
  const std::vector<Case> cases{
      {nested(127), "invalid_messages"},
      {nested(128), "parse_error"},
      {invalid_utf8, "parse_error"},
      {duplicate, "parse_error"},
      {"{\"model\":", "parse_error"},
      {R"({"model":"gufo-flash-next","max_tokens":1})", "missing_messages"},
      {R"({"model":"gufo-flash-next","messages":[{"role":"user","content":[{"type":"image_url","image_url":{"url":"data:image/png;base64,AA=="}}]}],"max_tokens":1})", "request_policy_violation"},
  };
  for (const auto& item : cases) {
    LifecycleBackend backend;
    const auto response = HandleOpenAiChat(Chat(item.body), backend);
    Expect(response.status == 400 && !response.streaming_body,
           "finite malformed fixture rejects without streaming success");
    const auto error_body = gufo::json::parse(response.body);
    const auto* error = error_body.find("error");
    Expect(error && error->member_str("code") == item.error_code,
           "finite fixture rejects at the expected parser or schema stage");
    Expect(backend.runner.prepare_calls == 0 && backend.admitted_calls == 0 &&
               backend.raw_calls == 0,
           "malformed fixtures do not prepare or admit a model request");
  }
  const auto accepted_depth = gufo::json::parse(nested(127));
  Expect(accepted_depth.contains("messages"),
         "root plus127 arrays fits the128-container JSON boundary");
  const auto oversized = baseline + std::string(16385 - baseline.size(), ' ');
  Expect(oversized.size() == 16385 &&
             gufo::json::parse(oversized).member_str("model") == "gufo-flash-next",
         "body-limit fixture is exactly16385 otherwise-valid JSON bytes");
}
```

The last assertion proves bytes/JSON only, not HTTP413: body-size rejection belongs to the HTTP reader before route dispatch. Do not call the route adapter for that case and pretend it exercises the reader. The inline image assertion exercises the policy rejection before any URL decoding/loading.

- [ ] Step3 — build and execute the one affected target.

Use the same child-only vcvars/PATH environment as the previous CPU build:

```powershell
$taskVc='C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat'
$taskEnvLines = & cmd.exe /d /s /c "call `"$taskVc`" >nul && set"
foreach ($line in $taskEnvLines) { if ($line -match '^([^=]+)=(.*)$') { [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process') } }
$env:PATH='C:\AI\sdk\therock1151\lib\llvm\bin;'+$env:PATH
& 'C:/Program Files/CMake/bin/cmake.exe' --build 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' --target text_request_policy_routes_test --parallel 2
& 'C:/Program Files/CMake/bin/ctest.exe' --test-dir 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' -N -R '^text_request_policy_routes_test$' --no-tests=error
& 'C:/Program Files/CMake/bin/ctest.exe' --test-dir 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' -R '^text_request_policy_routes_test$' --output-on-failure --no-tests=error
```

Expected discovery1, execution1passed/0failed/0skipped. Preserve build/CTest output in new task-owned logs; never overwrite previous metadata outputs. No unchanged helper test or broader suite repeat.

- [ ] Step4 — format/self-review and commit owned test only.

Use pinned formatter `C:/Program Files (x86)/Microsoft Visual Studio/2022/BuildTools/VC/Tools/Llvm/bin/clang-format.exe`19.1.5 on the owned file; run its dry-run and required `tools/ci/check-format.py` with that formatter on process PATH. Report inherited kernel-only violations without editing them. If formatting changes the compiled test, rebuild/retest the single target. Check source/fixture/helper identities remain fixed; only the intended test differs from task BASE.

```powershell
git add -- tests/cli/text_request_policy_routes_test.cpp
git commit -m 'test(server): characterize finite malformed request fixtures'
```

Report BASE/HEAD/tree, exact command/output/logpaths, actual case coverage, test count/skips, assertion flags, resource checks, inherited warnings and scope limitations. No push. Parent performs independent task review before relying on these recipes in a live manifest.

## Self-review

This closes only the byte/parser-stage uncertainty identified by the source audit. Previously measured token fixtures and existing policy rejection tests remain evidence for their own scope. The complete72-request schedule, finite ledger/transport/store/IPC integration, recovery and real inference/benchmarks are still pending. This test does not grant service acceptance or substitute parser tests for model correctness.
