# GUFO Larger Lifecycle Fixture Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Extend the existing CPU-only preparation helper just enough to freeze the larger finite-service prompts and one required-tool fixture without touching the built production engine.

**Architecture:** A separate test-only engine checkout starts at the frozen production head. Reuse its real route adapters, renderer, tokenizer and policy unchanged; broaden only the helper's finite input choices and truthful resolved-tool reporting. Runtime packaging and the full72-attempt client remain separate tasks.

**Tech Stack:** C++23, existing CMake/CTest targets, native Windows pinned clang24/vcpkg, HIP OFF.

## Global Constraints

- Preserve working installations and unrelated changes. Native Windows and WSL2 are acceptable; dual boot is not.
- Preserve 49GiB available physical memory before model launch,24GiB during model testing,12GiB commit reserve. This task does not authorize any model launch.
- No BIOS/carve/VGM/driver/services/security/pagefile settings, reboot, D:, publication or unrelated process termination.
- Production engine `C:/Projects/strix-alloy-research/engine/gufo-ar4k-header-cap` stays clean at `e6feed7ca52df4661d10434c72a8ea5b5f054bc2`, tree `7912be2688d6874c0e13f4723aad00a5c3cbe1cf`. Do not change its build, pins or staged/runtime records.
- Only `tests/cli/service_prompt_fixture.cpp` and `tests/cli/service_prompt_fixture_test.cpp` change in the isolated component checkout. All production code and the committed first-six fixture stay byte-identical.
- Retain first-shard-only authenticated OpenMemory loading: metadata<=16MiB, fixture<=1MiB,<=64records/file,body<=16KiB,rendered<=32KiB. No split discovery, model construction, GPU/session/prefill/decode, socket or network access. Inference methods still fail fast.
- CPU-only builds/tests use two jobs and fresh24GiB available RAM/25GiB free C: checks. Existing toolchain/dependencies only, no acquisition. No direct metadata-helper execution during implementation; the parent uses the reviewed final binary later.
- The helper's HTTP200 remains synthetic preparation-only, not an answer or correctness/performance measurement. No stream-body callback is executed by this helper.

## Task 1: Extend bounded preparation choices and resolved-tool evidence

**Files:** Modify `tests/cli/service_prompt_fixture.cpp` and `tests/cli/service_prompt_fixture_test.cpp` only, relative to the new component worktree below. Do not modify CMake or the first-six fixture.

**Isolation:** The parent creates/selects `C:/Projects/strix-alloy-research/engine/gufo-lifecycle-fixture` on `codex/service-lifecycle-fixture` from exact production HEAD. The normal source repository is `C:/Projects/strix-alloy-research/sources/gufo-windows`; the native app worktree tool cannot select that component repository. Verify identity before proceeding, and do not repurpose an existing different directory/branch. No duplicate integration checkout.

**Interfaces:** Keep `ParseFixture`, `PrepareRecord`, `PrepareFixture` and the three-argument helper CLI unchanged. New accepted output choices are exactly16/64/256. Chat may carry exactly one function-tool definition and tool_choice auto/none/required. Required-tool preparation is supported only with stream=true: a non-streaming empty synthetic response would otherwise fail post-generation tool enforcement and be mislabelled as an input-policy rejection. Production HTTP behavior is unchanged.

- [ ] Step1 — add failing CPU tests.

Add this helper in the existing anonymous test namespace:

```cpp
std::string FixtureFor(const gufo::testing::service_prompt::RequestRecord& row) {
  gufo::json::Value item = gufo::json::Value::object();
  item["id"] = row.id;
  item["route"] = row.route;
  item["body"] = row.body;
  gufo::json::Value document = gufo::json::Value::object();
  document["requests"] = gufo::json::Value::array();
  document["requests"].push_back(std::move(item));
  return document.dump();
}
```

After the existing synthetic tokenizer/basic exact-result assertions in RunTests, add:

```cpp
for (const int output : {16, 64, 256}) {
  auto body = gufo::json::parse(records[0].body);
  body["max_output_tokens"] = output;
  const RequestRecord row{"sized", "/v1/responses", body.dump()};
  const auto accepted = ParseFixture(FixtureFor(row));
  const auto result = gufo::json::parse(PrepareRecord(accepted[0], *tokenizer));
  Expect(result.member_size("http_status") == 200 &&
             result.member_size("max_output_tokens") == static_cast<std::size_t>(output) &&
             result.member_size("token_count") == 10 &&
             result.member_str("rendered_sha256") == prepared.member_str("rendered_sha256") &&
             result.member_str("token_ids_le_u32_sha256") == prepared.member_str("token_ids_le_u32_sha256"),
         "finite output choices preserve exact input preparation");
}
for (const int output : {0, 65, 257}) {
  auto body = gufo::json::parse(records[0].body);
  body["max_output_tokens"] = output;
  bool rejected = false;
  try {
    (void)ParseFixture(FixtureFor({"bad-cap", "/v1/responses", body.dump()}));
  } catch (const std::exception&) {
    rejected = true;
  }
  Expect(rejected, "helper rejects output outside its closed finite choices");
}
auto tool_body = gufo::json::parse(R"({"model":"gufo-flash-next","messages":[{"role":"user","content":"hi"}],"max_tokens":64,"temperature":0,"cache_prompt":false,"chat_template_kwargs":{"enable_thinking":false,"preserve_thinking":false},"stream":true,"tools":[{"type":"function","function":{"name":"report_sum","description":"Report the sum.","parameters":{"type":"object","properties":{"sum":{"type":"integer"}},"required":["sum"],"additionalProperties":false}}}]})");
std::string auto_render_hash;
for (const std::string choice : {"auto", "none", "required"}) {
  tool_body["tool_choice"] = choice;
  const auto accepted = ParseFixture(FixtureFor({"tool", "/v1/chat/completions", tool_body.dump()}));
  const auto result = gufo::json::parse(PrepareRecord(accepted[0], *tokenizer));
  Expect(result.member_size("http_status") == 200 &&
             result.member_size("tool_count") == 1 &&
             result.member_str("tool_choice") == choice &&
             result.find("stream")->as_bool(),
         "prepared tool evidence reflects the actual resolved enum");
  if (choice == "auto") auto_render_hash = result.member_str("rendered_sha256");
  if (choice == "none") {
    Expect(result.member_str("rendered_sha256") == prepared.member_str("rendered_sha256") &&
               result.member_size("token_count") == 10 &&
               result.member_str("token_ids_le_u32_sha256") == prepared.member_str("token_ids_le_u32_sha256"),
           "tool none excludes supplied tool from exact rendered input");
  }
  if (choice == "required")
    Expect(result.member_str("rendered_sha256") != auto_render_hash,
           "required tool changes the rendered tool instruction");
}
tool_body["stream"] = false;
bool required_nonstream_rejected = false;
try {
  (void)ParseFixture(FixtureFor({"required-nonstream", "/v1/chat/completions", tool_body.dump()}));
} catch (const std::exception&) {
  required_nonstream_rejected = true;
}
Expect(required_nonstream_rejected,
       "helper does not mislabel synthetic missing-tool generation as input rejection");
```

These tests verify the added input choices and enum/reporting seam; they do not certify model-generated tool calls. Existing byte/count/hash assertions for first-six/basic/rejection behavior remain intact. Format with the pinned formatter; do not remove existing tests.

- [ ] Step2 — baseline/configure and RED.

Use a new CPU build directory `C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927`. Import the existing vcvars64 environment only into the child build process and prepend `C:/AI/sdk/therock1151/lib/llvm/bin`; use existing Ninja path. Reuse the exact previous CPU recipe from `reports/gufo-service-prompt-fixture-implementation-20260927.md`, changing source/build directories and recording version label e6feed7. The full configure arguments are:

```powershell
& 'C:/Program Files/CMake/bin/cmake.exe' -S 'C:/Projects/strix-alloy-research/engine/gufo-lifecycle-fixture' -B 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' -G Ninja -DCMAKE_BUILD_TYPE=RelWithDebInfo -DBUILD_TESTING=ON -DENGINE_ENABLE_HIP=OFF -DGUFO_BUILD_TOOLS=OFF -DCMAKE_C_COMPILER=C:/AI/sdk/therock1151/lib/llvm/bin/clang.exe -DCMAKE_CXX_COMPILER=C:/AI/sdk/therock1151/lib/llvm/bin/clang++.exe -DCMAKE_LINKER_TYPE=LLD -DCMAKE_TOOLCHAIN_FILE=C:/Projects/strix-alloy-research/deps/vcpkg/scripts/buildsystems/vcpkg.cmake -DVCPKG_TARGET_TRIPLET=x64-windows -DVCPKG_MANIFEST_MODE=OFF -DGUFO_VERSION=e6feed7ca52df4661d10434c72a8ea5b5f054bc2
& 'C:/Program Files/CMake/bin/cmake.exe' --build 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' --target service_prompt_fixture_test --parallel 2
& 'C:/Program Files/CMake/bin/ctest.exe' --test-dir 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' -R '^service_prompt_fixture_test$' --output-on-failure --no-tests=error
```

Run the unchanged focused baseline before adding tests, then the RED after tests. Expected RED: the existing helper rejects output16 (and later tool fields) because it only permits64. Do not manufacture wrong expected token counts as a regression RED.

- [ ] Step3 — minimal helper-only implementation.

In chat's AllowedBodyField return expression, add:

```cpp
|| field == "tools" || field == "tool_choice"
```

Within ValidateBody's field loop add:

```cpp
if (key == "tools" && (!value.is_array() || value.size() != 1))
  throw std::invalid_argument("fixture requires exactly one declared tool");
if (key == "tool_choice" &&
    (!value.is_string() || (value.str() != "auto" && value.str() != "none" &&
                            value.str() != "required")))
  throw std::invalid_argument("fixture requires auto, none, or required tool choice");
```

Keep the actual function-definition parsing in the existing real route adapter; it performs no external tool execution. Replace only the final exact64 check with:

```cpp
const auto output = body.member_size(route == "/v1/responses" ? "max_output_tokens" : "max_tokens");
if (body.member_str("model") != "gufo-flash-next" ||
    body.member_double("temperature", -1.0) != 0.0 ||
    (output != 16 && output != 64 && output != 256))
  throw std::invalid_argument("fixture requires alias, greedy sampling and output 16, 64, or 256");
if (body.member_str("tool_choice") == "required") {
  const auto* stream = body.find("stream");
  const auto* tools = body.find("tools");
  if (stream == nullptr || !stream->is_bool() || !stream->as_bool() ||
      tools == nullptr || !tools->is_array() || tools->size() != 1)
    throw std::invalid_argument("required-tool fixture needs one tool and stream=true");
}
```

Retain all remaining reasoning/cache/text/body/file/route restrictions unchanged. In ResultFor, replace the literal auto reporting with the actual enum:

```cpp
switch (backend.runner.captured.tool_choice) {
  case server::ChatRequest::ToolChoice::kAuto: result["tool_choice"] = "auto"; break;
  case server::ChatRequest::ToolChoice::kNone: result["tool_choice"] = "none"; break;
  case server::ChatRequest::ToolChoice::kRequired: result["tool_choice"] = "required"; break;
}
```

Do not synthesize a tool call or execute the streaming callback to make preparation pass. Do not broaden this helper into a malformed-wire HTTP tester. The previously documented ReadBounded growth race remains a separate visible robustness item; no unplanned shared-input or stream-test framework is required here.

- [ ] Step4 — GREEN and final source/binary evidence.

```powershell
& 'C:/Program Files/CMake/bin/cmake.exe' --build 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' --target service_prompt_fixture_test service_prompt_fixture text_request_policy_routes_test --parallel 2
& 'C:/Program Files/CMake/bin/ctest.exe' --test-dir 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' -N -R '^(service_prompt_fixture_test|text_request_policy_routes_test)$' --no-tests=error
& 'C:/Program Files/CMake/bin/ctest.exe' --test-dir 'C:/Projects/strix-alloy-research/build/gufo-lifecycle-fixture-cpu-20260927' -R '^(service_prompt_fixture_test|text_request_policy_routes_test)$' --output-on-failure --no-tests=error
```

Expected discovery2, execution2passed/0failed/0skipped. Inspect actual assertion flags. Run required shared formatting check with the installed pinned clang-format19.1.5; record existing unrelated failures rather than editing kernels. Hash final helper and preserve logs. Confirm `git diff --name-only e6feed7..HEAD` lists only the two test files; record clean production checkout and unchanged first-six hash. Do not rerun metadata preparation before review.

- [ ] Step5 — commit owned test files and report.

```powershell
git add -- tests/cli/service_prompt_fixture.cpp tests/cli/service_prompt_fixture_test.cpp
git commit -m 'test(server): support bounded lifecycle prompt preparation'
```

Report to `C:/Projects/strix-alloy-research/reports/gufo-lifecycle-fixture-helper-implementation-20260927.md`: exact BASE/HEAD/tree, TDD command/output,2test counts/skips, resource checks, final helper hash and limitations. No push. The parent independently reviews the complete BASE..HEAD delta before bounded final-binary metadata verification and later finite72-request fixture construction.

## Plan self-review

This task covers only the preparation-helper gap identified in `reports/gufo-larger-fixture-seam-20260927.md`; the full performance goal remains unchanged. Exact native larger fixture counts and real generated tool correctness are subsequent evidence, not a claim of this implementation. Interfaces and existing targets are preserved. Non-streaming required-tool synthetic failure is explicitly excluded, not misclassified as model or policy failure. Production source/build identity remains untouched.
