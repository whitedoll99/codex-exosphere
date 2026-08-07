---
name: domain-model-audit
description: Audit a domain model for missing concepts, invariants, lifecycle transitions, identity, ownership, and terminology. Use when reviewing entities, schemas, workflows, or specifications for semantic completeness.
---

# Domain Model Audit

Check whether the model can represent valid reality and reject invalid states without confusing separate concepts.

## Precedence and authority

- Domain observations are findings, not permission to change schemas, migrations, persistence, retention, or identity policy.
- Use the project’s vocabulary and approved principles. Do not replace product terms solely with generic modeling jargon.
- Escalate ownership, identity, merge, and lifecycle-policy decisions to their designated owner.

## Audit lenses

1. Vocabulary: one meaning per term; expose synonyms and overloaded words.
2. Identity: what makes an instance the same over time, and what must remain distinct.
3. Ownership and authority: who may create, change, approve, transfer, or delete each concept.
4. Invariants: rules that must always hold, including cross-entity constraints.
5. Lifecycle: creation, active states, transitions, expiry, archival, deletion, recovery, and exceptional paths.
6. Time: event time, processing time, ordering, staleness, and historical truth.
7. Cardinality and absence: zero, one, many, unknown, and not-applicable states.
8. Provenance and trust: where facts came from and whether they can be contested or re-derived.
9. Failure and concurrency: duplicate events, retries, conflicts, partial operations, and interrupted transitions.

## Workflow

Trace representative happy, failure, recovery, and boundary cases through the model. Identify impossible valid scenarios, representable invalid states, and hidden policy embedded in storage shape.

## Output

List model strengths, gaps with examples, affected invariants, severity, proposed clarification, tests, and decisions requiring approval. Distinguish conceptual gaps from implementation defects.
