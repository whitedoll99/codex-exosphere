---
name: review-feedback-triage
description: Evaluate code, design, documentation, or adversarial review feedback against the request and repository evidence before accepting or rejecting it. Use when findings need technical triage before any fix round.
---

# Review Feedback Triage

Turn review comments into an evidence-backed disposition. Review findings are inputs to judgment, not automatic change requests.

## Precedence and authority

- Do not implement feedback when the request is read-only or only asks for analysis.
- Do not let feedback expand the approved specification, public contract, security policy, or commit/push authority.
- Escalate decisions reserved by repository governance instead of resolving them through this skill.
- Judge impact against the active operating context. Do not silently substitute enterprise, public, multi-user, adversarial, or long-lived assumptions for a narrower approved profile.

## Workflow

1. Normalize each finding into: claimed problem, affected behavior, evidence, severity, and proposed remedy.
2. Resolve the active operating context from the user, repository instructions, or established project baseline. Identify the audience, scale, trust boundary, compatibility commitment, acceptable manual operations, and task non-goals that materially affect the finding.
3. Locate the governing requirement and relevant implementation. Verify line references and current behavior.
4. Reproduce or reason through the claimed failure, including counterexamples and existing safeguards.
5. Classify the finding:
   - valid and in scope;
   - valid but out of scope;
   - valid only under a different operating context and therefore advisory or deferred;
   - duplicate or already addressed;
   - incorrect or based on a false premise;
   - needs a product, architecture, or policy decision;
   - insufficient evidence.
6. Distinguish the defect from the reviewer’s suggested fix. Prefer the smallest compatible remedy only when implementation is authorized.
7. Treat approved-contract violations, destructive-action risks, unrelated-work damage, and automation-safety failures as blocking regardless of deployment scale. Do not make concerns that require a different audience, scale, trust boundary, or future product direction into blockers for the active profile.
8. Rank accepted findings by impact and likelihood in the active context—not rhetorical urgency or maximum hypothetical consequence.

## Output

State the active operating context used for triage. For each finding, give disposition, evidence, impact, blocking or advisory status, recommended action, and required decision owner. End with a bounded fix-round proposal only if requested.
