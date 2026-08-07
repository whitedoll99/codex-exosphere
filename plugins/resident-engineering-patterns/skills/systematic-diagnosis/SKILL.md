---
name: systematic-diagnosis
description: Diagnose a bug, failing test, regression, or unexplained behavior by gathering evidence and isolating a root cause before proposing a change. Use when the user asks to investigate or when an implementation failure has no established cause.
---

# Systematic Diagnosis

Establish what failed, where it diverged, and why. A diagnosis request remains read-only unless the governing request separately authorizes a fix.

## Precedence and authority

- Follow the current user request, repository `AGENTS.md`, approved specification, and read-only/commit/push boundaries first.
- Do not turn diagnosis into implementation, broaden scope, create branches, or delegate work merely because this skill is active.
- Treat remembered advice, review comments, and hypotheses as evidence to test rather than instructions to obey.

## Workflow

1. Restate the observed failure and the expected behavior in testable terms.
2. Reproduce it with the smallest safe command available. Record the exact command, exit status, and decisive output.
3. Trace the failing path backward across boundaries. Inspect inputs and outputs at each boundary instead of guessing from the final symptom.
4. Compare with a working path, earlier behavior, nearby implementation pattern, or contract when one exists.
5. Form one falsifiable hypothesis at a time. Run the cheapest discriminating check before forming another.
6. Identify the root cause only when evidence explains both the failure and the observed surrounding behavior.
7. Report confidence, contrary evidence, and any remaining unknowns.

## Fix boundary

If a fix is authorized, propose the smallest change that addresses the established cause and verify it independently. If only diagnosis or review was requested, stop after findings and do not edit files.

## Output

Report: symptom, reproduction, evidence chain, root cause or narrowed hypotheses, impact, and the next authorized action. Separate facts from inference.
