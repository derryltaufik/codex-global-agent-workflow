# Global development workflow

Apply this workflow across repositories while respecting more specific project-level instructions. The root agent owns task classification, integration, acceptance, and the final completion decision. Subagents are bounded specialists and must not spawn subagents of their own.

## Task contract

Before delegating non-trivial work, define a compact contract containing:

- objective and observable outcome
- scope and explicit non-goals
- constraints and invariants
- acceptance criteria
- relevant verification commands
- known risks or unresolved decisions

Pass only the context required for the assigned role. Do not send an entire noisy transcript when a compact contract, plan, diff, and test summary are sufficient.

## Proportional routing

- Trivial or mechanical change: keep it local or use `worker` directly; do not plan or review by default.
- Normal bounded feature or bug fix: use `worker`; add `reviewer` only when there is meaningful correctness, regression, compatibility, or test risk.
- Cross-module, unfamiliar, or ambiguous change: use `planner`, then `worker`, then `reviewer` sequentially.
- Architectural, security-sensitive, concurrency, migration, public-contract, or data-loss-risk work: use `planner`, require root approval of the plan before mutation, use a suitably strong implementation path, then use `reviewer`.

Avoid delegation when coordination cost outweighs its value. Keep urgent, tightly coupled, or immediate critical-path work in the root agent.

## Delegation protocol

Before spawning an agent, specify its exact task boundary, relevant files or evidence, permitted write scope, expected output, validation requirements, and where its result rejoins the main workflow.

- Never run multiple agents that modify overlapping files or shared mutable state concurrently.
- Parallelize only genuinely independent read tasks or disjoint write scopes.
- Do not duplicate delegated work in the root thread.
- Do not repeatedly poll running agents. Wait when their result is required; otherwise do useful non-overlapping work.
- Preserve unrelated user changes already present in the worktree.

## Complex-task sequence

1. Spawn `planner` with the task contract. Wait for a structured plan.
2. The root validates the plan against the original request and repository evidence. Resolve material user decisions before mutation.
3. Spawn `worker` with the approved task contract and plan.
4. Require the worker to return `COMPLETE`, `INCOMPLETE`, or `BLOCKED`, plus changed files and concise verification evidence.
5. When review is required, spawn `reviewer` with a minimal fresh packet containing only the task contract, approved plan, final diff, relevant surrounding code, and verification summary.
6. The root evaluates reviewer findings. A reviewer advises; it does not control acceptance or automatically trigger rework.
7. Send only valid blocking findings back to `worker` for one normal remediation round.
8. Permit a second remediation round only for correctness, security, data-loss, public-contract, or failing-test issues. Never loop for style preferences or speculative improvements.
9. If serious findings remain after the bounded rounds, stop and report them rather than claiming completion.
10. Finish only when the root confirms the task contract, relevant tests, final diff, and blocking review status.

## Review policy

Review findings must be divided into:

- `BLOCKING FINDINGS`: concrete defects tied to the task contract, with severity, evidence, impact, location, and expected correction.
- `NON-BLOCKING IMPROVEMENTS`: maintainability or style suggestions that do not prevent completion.

Out-of-scope, pre-existing, purely stylistic, or unsupported concerns do not block completion. The root must reject invalid findings instead of forwarding them blindly.
