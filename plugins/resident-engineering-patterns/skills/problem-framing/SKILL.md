---
name: problem-framing
description: Clarify a product, engineering, or research problem before solution design by identifying actors, desired outcomes, constraints, evidence, and success measures. Use when the request is broad, solution-led, or not yet testable.
---

# Problem Framing

Produce a decision-ready problem statement without prematurely selecting an implementation.

## Precedence and authority

- Respect the user’s stated vision and all repository decision ownership.
- Framing is analysis: it does not authorize implementation, dependency adoption, external contact, or scope expansion.
- Preserve explicit assumptions as assumptions; do not turn them into requirements silently.
- Apply the active operating context from the user, repository instructions, or established project baseline. Do not invent a larger audience, scale, trust boundary, or compatibility promise.

## Workflow

1. Resolve the active operating context. Reuse existing facts about audience, user/operator count, trust boundary, expected lifetime, compatibility commitment, acceptable manual operations, and recurring non-goals. Ask only when an unknown would materially change the solution.
2. Identify the affected actor, current situation, observed pain, and consequence.
3. Separate the underlying need from the requested mechanism or favored solution.
4. Gather available evidence: examples, frequency, severity, current workaround, and baseline behavior.
5. Define the desired outcome in observable terms.
6. Record constraints and non-goals, including compatibility, privacy, cost, time, and operational limits.
7. Identify the observed failure or explicit requirement addressed by this task. Do not promote hypothetical future concerns into current requirements.
8. State the smallest sufficient problem boundary, acceptable manual work, and deferred concerns.
9. Identify unknowns whose answers could materially change the solution space.
10. Define success measures and failure signals without inventing unattested numeric targets.

## Output

Provide: active operating context, problem statement, actors, evidence, desired outcome, constraints, non-goals, assumptions, smallest sufficient scope, deferred concerns, open decisions with owners, and success measures. Keep candidate solutions in a separate optional section.
