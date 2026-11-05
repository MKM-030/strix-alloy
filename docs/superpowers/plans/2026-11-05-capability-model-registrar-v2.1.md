# Registrar v2.1 capture completeness repair

Root authorized a pre-integration source-only successor after independent review. Preserve every v2 source/test/guide/handoff byte. Work only on new v2.1 files in the existing isolated branch `codex/model-registration-v2-20261105`, based on v2 commit `01f08ff6ac8637580f0426005cce0b7ad9927bc3`. No SDK, native/runtime operation or canonical edit.

Independent minimal reproduction: `C:/Projects/strix-alloy-clean/server/.local/voice-repair-20261102/registrar-v2-independent-review-20261105/MISSING-ES-COMPANION.v1.REPRO.json`, SHA256 `7726968a9ffe9b5a3349646b1c859b1a82c93df7a627f866bc328d22fd631a5b`. Frozen v2 wrongly accepts a visible current ES companion omitted from the payload, including active LF registration with a ready Add handoff. The inverse missing-current case already refuses.

- [x] Add reviewer-derived RED cases for visible-current/payload-absent, both inactive and active, plus exact retained LF source; preserve a distinct inverse missing-current case.
- [x] Query secure current companion presence on EVERY transformer transport check. Require at most one visible row and bidirectional presence parity before complete nine-field equality.
- [x] Keep both-absent single-record captures valid; document that secure absence is not global absence.
- [x] Create only new v2.1 source/tests/guide/handoff, run targeted and full relevant CPU checks/ES5 parsing, verify every frozen predecessor hash, commit and hand to Root.

Do not relax action, binding, direct-field, size, permissions, source/history/context, exact content or Partial guards. Never create/edit ES companions or retry an uncertain operation.

Verification: the three missing-payload cases were RED against the exact v2 behavior (`Applied` instead of `Partial`). After the narrow parity fix all four targeted cases passed, including the inverse missing-current case. All five relevant suites passed 368/368 CPU cases (v2.1:101); no native execution occurred. The ordinary both-absent and complete both-present positive cases remain green.
