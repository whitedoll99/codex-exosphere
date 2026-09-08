---
name: bounded-tdd
description: Apply a red-green-refactor loop to a clear, local, already authorized behavior change with concrete verification. Use only when requirements are settled and tests can express the requested behavior.
---

# Bounded TDD

Use tests to drive a small approved change. This skill does not decide product behavior or grant implementation authority.

## Eligibility

Use only when:

- the request explicitly authorizes implementation;
- behavior and acceptance criteria are unambiguous;
- no public API, schema, migration, security, privacy, persistence, or architecture decision remains open;
- a focused automated test can observe the behavior.

Otherwise, return to specification, diagnosis, or the required decision owner.

## Loop

1. Identify one observable behavior from the approved criteria.
2. Add the smallest focused test that fails for the intended reason.
3. Run it and confirm the failure is behavioral, not a setup or syntax error.
4. Before adding custom code, an abstraction, or a dependency, check in order:
   existing repository capability, standard library, native platform
   capability, already-approved dependency, then the smallest local
   implementation. Use an earlier option only when it satisfies the actual
   contract, edge cases, compatibility, and repository architecture.
5. Implement the minimum production change needed to pass.
6. Run the focused test, then relevant neighboring and regression checks.
7. Refactor only within scope while keeping tests green.
8. Repeat for the next approved behavior.

## Guardrails

- Do not alter tests merely to accommodate existing behavior that contradicts the approved requirement.
- Do not over-mock the unit under test or assert private implementation details without necessity.
- Preserve backward compatibility and unrelated user changes.
- Stop and escalate if the failing test reveals an undecided contract or requires scope expansion.
- Commit and push only when explicitly authorized.

## Output

Report each behavior covered, initial failing evidence, passing verification, broader checks, changed scope, and remaining risk.
