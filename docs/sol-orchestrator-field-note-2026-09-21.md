# Sol orchestrator field note — 2026-09-21

Status: one operational observation from an existing personal development
environment. This is feedback for routing and evaluation design, not a
controlled benchmark or an installation acceptance result.

## Context

The resident Codex was served by Sol and owned a bounded cross-layer change:
a SQLite reader plus a pure query composer. The resident fixed the contract,
limited the change to seven paths, delegated implementation to an established
task-scoped collaborator, inspected intermediate and final diffs, and retained
acceptance, commit, integration, and push responsibility.

The collaborator was not the exosphere Luna worker. Astra Oracle was not
invoked. This observation therefore exercises Sol's orchestration and review
behavior only; it does not validate Luna launch, Astra advice, or the complete
three-model route.

## What was observed

Sol found several contract defects by reading the implementation and tests
while the implementation writer remained active:

- a two-statement read violated the specified single-statement snapshot;
- exact-key and runtime container validation was incomplete;
- a sparse array could escape as a raw `TypeError`;
- SQLite text reads did not initially prove complete-byte handling for
  identifiers and roles;
- a database dependency boundary used duck typing instead of the required
  concrete instance check;
- malformed stored enum values could be confused with a supported state;
- a zero-write test compared row counts rather than complete populated-table
  values; and
- corruption probes initially accepted any thrown exception instead of
  requiring the contracted content-free error.

The writer corrected these within the original path boundary. Sol then checked
the actual diff and test bodies, matched a 226-file manifest against the stopped
tree, ran a fresh repository check (41 test files, 427 tests), and finalized the
scope guard before accepting the change.

No evidence in this run required Oracle consultation. That supports the current
policy of keeping Astra for bounded questions whose problem statement or causal
explanation remains contested after primary-source inspection. It does not show
that Sol will identify every such question.

## Useful follow-ups

1. Add or extend a Sol review eval with defects from this run: split snapshot,
   duck-typed dependency, sparse container, incomplete byte read, and an
   `any throw` test that fails to pin error taxonomy. These are stronger review
   signals than a generic style defect.
2. Treat worker availability as multi-source state. Absence of a matching
   process name did not prove that work was inactive; worktree state, delivery
   state, and structured worker status were more reliable together.
3. Preserve read-only intermediate review as an optional latency reduction.
   It helped correct defects before the final handoff, provided the resident
   never became a second writer in the worker's tree.
4. Keep final acceptance independent even after successful intermediate
   feedback. Manifest equality, actual diff review, fresh verification, and
   the scope guard each caught a different class of possible false completion.
5. Track external-action approval separately from model routing. In this run,
   host auto-review did not inherit prior standing push authorization and
   required a new explicit user statement. This was an approval transport
   limitation, not evidence for or against Sol/Astra/Luna routing quality.

## Limits of the observation

- It is one successful task, not a repeated routing measurement.
- The implementation collaborator was not Luna, so worker cost, launcher
  behavior, packet enforcement, and Luna implementation quality remain
  unmeasured here.
- Astra was not called, so Oracle trigger precision and advice quality remain
  unmeasured here.
- The resident supplied several review findings during implementation; the run
  does not isolate how much would have been found only at the final review gate.
- No conclusion is drawn about unrelated tasks, larger migrations, security
  work, or ambiguous product decisions.

