---
name: contract-design
description: Analyze or specify an approved software boundary through inputs, outputs, invariants, errors, compatibility, and observability. Use for APIs, CLIs, adapters, persistence boundaries, events, or component interfaces.
---

# Contract Design

Make observable behavior explicit at a selected boundary. Do not use this skill to choose a new public contract without the required owner’s approval.

## Precedence and authority

- Existing specifications and compatibility commitments outrank local elegance.
- A proposed public API, CLI, schema, migration, configuration default, or failure-semantic change remains a proposal until approved.
- Do not implement or migrate data merely because a contract has been drafted.

## Contract checklist

1. Purpose and boundary owner.
2. Callers, consumers, and trust level.
3. Inputs: shape, units, encoding, required fields, limits, validation, and defaults.
4. Outputs: shape, ordering, determinism, partial results, and side effects.
5. Invariants and preconditions.
6. Error taxonomy, retryability, timeouts, idempotency, cancellation, and atomicity.
7. Compatibility and versioning expectations.
8. Security, privacy, retention, and data-egress implications.
9. Observability needed to diagnose failures without leaking sensitive data.
10. Contract tests and representative edge cases.

## Analysis

Trace at least one successful path and important failure paths end to end. Flag ambiguous ownership, implicit coupling, impossible guarantees, and behavior that differs across implementations.

## Output

Return the current contract, gaps, proposed clarifications, compatibility impact, tests, and decisions requiring approval. Separate documentation-only clarification from behavioral change.
