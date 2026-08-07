---
name: architecture-quality-analysis
description: Evaluate an architecture decision against explicit quality attributes, scenarios, constraints, and tradeoffs. Use when comparing designs or reviewing whether a proposed structure serves product and operational goals.
---

# Architecture Quality Analysis

Analyze architecture as tradeoffs under concrete scenarios, not as a contest of patterns.

## Precedence and authority

- Preserve approved product direction, core policy, adapter boundaries, and decision ownership.
- This analysis does not authorize architecture changes, new dependencies, services, recurring costs, or migrations.
- Keep reviewer roles advisory; one accountable owner must decide and execute.

## Workflow

1. State the decision and the baseline alternative, including “keep the current design.”
2. Identify the few quality attributes that materially affect this decision: correctness, security, privacy, reliability, performance, operability, maintainability, portability, cost, or others evidenced by the request.
3. Express each important attribute as a scenario: stimulus, environment, affected component, desired response, and measurable response.
4. Map each option to benefits, liabilities, assumptions, and failure modes under those scenarios.
5. Check cross-attribute tradeoffs and irreversible consequences.
6. Identify evidence needed: benchmark, prototype, fault injection, migration rehearsal, or operational data.
7. Recommend an option only when the decision owner and evidence support it; otherwise recommend the next discriminating experiment.

## Circuit breaker

If repeated review rounds reject options without improving the product decision, stop. Re-state what can ship relative to the current baseline, which product harm each gate prevents, and who owns the final decision.

## Output

Provide decision context, scenarios, option matrix in prose or a compact table, recommendation with confidence, rejected alternatives, validation plan, and approval needs.
