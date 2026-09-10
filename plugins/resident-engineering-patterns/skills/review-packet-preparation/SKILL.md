---
name: review-packet-preparation
description: Prepare a bounded, evidence-rich packet for an independent code, design, documentation, or release review. Use when another agent or reviewer must assess work without inheriting implementation authority.
---

# Review Packet Preparation

Give the reviewer enough context to find real defects while preserving one accountable implementation owner.

## Precedence and authority

- Preparing a packet does not authorize delegation, file changes, commits, pushes, releases, or scope expansion.
- Keep the reviewer independent: provide facts and constraints without steering toward approval.
- The resident main agent retains decisions, remediation, and the final report.

## Packet contents

1. Objective and user-visible acceptance criteria.
2. Allowed scope, non-goals, and explicit read-only/commit/push boundaries.
3. Relevant repository rules and decision ownership.
4. Base and head references, changed files, or exact artifact locations.
5. Concise implementation summary and important design choices.
6. Verification commands and unedited decisive outcomes.
7. Known risks, assumptions, unresolved questions, and unrelated working-tree changes to ignore.
8. Review focus: correctness, regressions, contracts, security/data handling, edge cases, and test gaps.
9. Requested response format: findings ordered by severity with evidence and file references; no changes unless explicitly authorized.

## Quality checks

- Ensure the reviewer can reproduce claims from the packet.
- Separate implementation rationale from acceptance criteria.
- Do not omit failed or unavailable checks.
- Avoid oversized context that obscures the decision surface.

## Output

Produce a self-contained packet suitable for a review tool, another agent, or a human reviewer. State clearly whether the recipient is advisory, read-only, or authorized for a bounded fix round.

Require the review result to include exactly one status line:
`Evidence audit: performer=<role|none>; inspected=<AC/test/probe scope>; omitted=<scope|none>`.
Use a role rather than a personal name. If no evidence audit was performed, use
`performer=none`; a missing or empty value never means that the audit was
completed.
