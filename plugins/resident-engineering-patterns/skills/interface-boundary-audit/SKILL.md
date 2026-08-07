---
name: interface-boundary-audit
description: Audit whether interfaces express stable capability boundaries while implementation details remain replaceable and dependencies point in the intended direction. Use for adapters, ports, plugins, providers, and host integrations.
---

# Interface Boundary Audit

Assess boundary quality without automatically introducing abstractions.

## Precedence and authority

- Approved adapter boundaries and public contracts are constraints, not suggestions.
- Do not create interfaces, split packages, or alter dependency direction unless implementation is authorized.
- A concrete implementation is acceptable when no meaningful substitution, testing, policy, or ownership boundary exists.

## Workflow

1. Identify the capability the boundary is meant to expose and who owns it.
2. List consumers and implementations, including foreseeable host-specific variants supported by the product direction.
3. Trace dependency direction and locate leaks of transport, storage, framework, environment, or vendor details.
4. Check whether the interface is consumer-shaped, cohesive, minimal, and behaviorally specified.
5. Check substitutability: errors, ordering, state, performance expectations, side effects, and lifecycle must be compatible.
6. Look for false abstraction: one-use pass-through interfaces, duplicated types, capability-free wrappers, or abstractions created only for mocking.
7. Check composition and ownership: configuration, construction, resource cleanup, and policy should have an explicit home.
8. Identify contract tests that every implementation should pass.

## Output

Report boundary purpose, current coupling, leaks, missing or excessive abstractions, compatibility risks, recommended local improvement, and approval needs. Prefer the smallest boundary that protects a real variation or policy seam.
