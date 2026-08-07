---
name: verification-before-reporting
description: Verify implementation, documentation, configuration, or operational work with fresh evidence before claiming completion or success. Use at the reporting gate for tasks with observable acceptance criteria.
---

# Verification Before Reporting

Make completion claims proportional to current evidence. This is a reporting gate, not permission to alter the work.

## Precedence and authority

- Preserve all governing scope and mutation boundaries.
- Do not add tests, fix defects, commit, push, or change external state unless separately authorized.
- The resident main agent owns the final judgment and report.

## Workflow

1. Translate each acceptance criterion into an observable check.
2. Inspect the actual diff or artifact, not only a worker or tool summary.
3. Run the narrowest decisive checks, then proportionate broader checks when risk warrants them.
4. Read full command outcomes: command, exit code, failures, skips, warnings, and relevant environment assumptions.
5. Check scope and non-goals separately from functional correctness.
6. Check repository status so unrelated changes and uncommitted work are not misattributed.
7. Classify the result as verified, partially verified, failed, or not verifiable in the current environment.

## Claim discipline

- Say “tests pass” only for tests just run successfully.
- Say “complete” only when all required work and checks are satisfied.
- Never convert a skipped, unavailable, flaky, or stale check into success.
- State residual risk and verification gaps plainly.

## Output

List implementation scope, checks performed with outcomes, acceptance-criterion coverage, unresolved concerns, and authorized next steps. Do not hide a failure behind a general success statement.
