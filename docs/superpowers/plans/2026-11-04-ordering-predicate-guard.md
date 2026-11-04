# Ordering Predicate Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow clearly negated, prospective/process and hypothetical ordering language without releasing unsupported positive order claims.

**Architecture:** Evaluate each literal `bestellt` occurrence in its local clause, preserving adjacent contrast/exception tails. A small conservative grammar recognizes only direct `nicht/nichts bestellt` predicate negation, explicit leading `falls`/conditional `wenn`, or prospective/process passive forms. Generic `kein` noun phrases and ambiguous/reporting/contrastive negation remain held; there is no general German parser. All positive optional-model completion assertions remain held; verified ServiceNow results already use the separate native backend speech lane. Caller text, processing, own history and free-text public findings grant no new completion authority.

**Tech Stack:** Existing Python regex guards and offline unittest fake model/media fixtures.

**Spec:** Root's explicit design GO, 2026-11-04, after a spent hearing probe proved `completion_ordered`; actual discarded sentence was not retained.

## Global Constraints

- Only the `bestellt` predicate receives this exception; other completion, identifier, number, identity, revision and playback guards remain active.
- Evaluate every occurrence. Negation/condition in one clause must not authorize another positive clause.
- Reject contrastive, restrictive, partial and double negation; retain comma tails such as `außer einem Laptop` or `sondern der Monitor`.
- Preserve per-reply recovery and one new attempt only for a new caller input. No inference, authentication or runtime changes.

## Review Focus

- `Es wurde noch nichts bestellt` passes; `Ich habe den Laptop bestellt` and `nicht nur … bestellt` stay held.
- `nicht von mir/gestern/hier/vollständig bestellt` does not negate completion.
- Concessive/factive `auch wenn/obwohl/nachdem` does not become a hypothetical exception.
- `bestellt worden sein` is inferred completion, not prospective `bestellt werden`.
- A later positive occurrence, or another forbidden guard, must still reject a multi-clause response.

### Task 1: Correct the ordering predicate only

**Files:** native_duplex.py; new test_native_duplex_ordering_language.py.

- [x] Add the allow/hold grammar matrix and provenance/other-guard tests; confirm current source fails the allow cases.
- [x] Add one conservative pure helper for noncompletion grammar and filter only its safe `bestellt` matches out of the existing forbidden-match scan.
- [x] Run targeted NativeDuplex tests and report the unchanged Native bridge hash.
- [ ] Independently review the committed scope for Root's later activation; do not claim the unretained live sentence has been verified.

## Verification

The original word guard rejected all eleven initial noncompletion examples. Independent adversarial review then exposed sixteen unsafe/ambiguous accepts in an uncommitted broader version; its generic `kein` branch was removed and exception tails/double negation/concession checks were tightened. The final targeted run passes all 101 NativeDuplex tests. Native bridge remains SHA256 `7315f2a24a868166388dc27dc9f9460c3ebfc0a41ef14428541298aab443891e`. No live call or runtime change was performed.
