# Eager dependency preparation implementation

1. Add focused model-free tests for import-only reusable preparation, retained module-origin validation, selected dependency failure, transport-gated startup ordering and distinct call ownership. Observe failures before production changes.
2. Extract the existing imports into `prepare_conversation_dependencies()` and reuse its classes during per-call setup. Record import and initialization durations without changing ownership or generation rules.
3. Call preparation in Native's application startup for a configured independent transport, before allocating its HTTP session and before yielding readiness. Record startup timing and propagate failures.
4. Run focused dependency tests and existing Native/Pipecat/lifecycle regression groups. Deliver isolated commits and exact validation evidence to Root. No runtime changes or inference tests in this worktree.
