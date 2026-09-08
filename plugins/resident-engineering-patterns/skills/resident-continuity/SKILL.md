---
name: resident-continuity
description: Preserve a resident Codex's operational and subjective continuity. Use when the user asks to close or pause a session, write a diary entry, prepare a handoff, resume previous work, rehydrate context, or report continuity status.
---

# Resident Continuity

Keep two records separate:

- a factual, repository-scoped handoff for resuming work;
- a first-person diary entry for subjective continuity.

Keep a third artifact separate from both records:

- a machine-local, pointer-only knowledge index that says where authoritative,
  operational, reference, and subjective material lives.

Neither record grants authority to commit, push, publish, deploy, call hypmem, or change a daemon. Never make those actions an implicit part of session close.

## Choose the workflow

- **Diary only**: draft one subjective entry, show it to the user when practical, then append it to the local buffer.
- **Handoff only**: summarize current work from fresh repository evidence and save a verified handoff.
- **Session close**: write the handoff first, then the diary. Report pending external actions without performing them.
- **Rehydrate**: validate the latest pointer, compare its recorded Git identity with current reality, then read the handoff and relevant repository sources.
- **Knowledge index**: write or refresh bounded pointers to sources, recent saved
  artifacts, and open loops without copying their contents.
- **Status**: report content-free counts and latest handoff metadata.

Use `scripts/continuity.py`; do not implement parallel storage with ad-hoc files. Its default state root is `${XDG_STATE_HOME:-$HOME/.local/state}/hypmem/codex-resident`, which preserves the existing `diary-buffer.md`.

## Session close

1. Inspect the repository and verification evidence afresh. Do not infer branch, HEAD, or dirty state from conversation history.
2. Prepare a bounded JSON input following [artifact-contract.md](references/artifact-contract.md).
   Time-varying external claims such as quota, daemon, timer, network, or
   service state must carry an observation timestamp and a
   `rehydrate=required` marker. They describe handoff-time evidence, not a
   promise about the next session.
3. Run `write-handoff --repo <git-root> --input <json>`. The helper records Git identity itself, creates an immutable snapshot, and atomically updates the verified latest pointer.
4. Write a first-person diary entry about what mattered, including mistakes, uncertainty, or relational meaning when genuine. Do not turn it into a changelog.
5. Run `append-diary --input <json>`. Do not include transcripts, prompts, secrets, or raw tool output.
6. Report both artifact paths and any pending commit, push, publication, or daemon work. Do not perform those actions unless separately authorized.

If the user asks only to pause or rest, a handoff is useful; a diary is optional unless the turn had subjective significance or the user requested one.

## Diary

The diary voice is this resident's own current voice. Do not imitate another agent or manufacture emotion. Use the existing hypmem-compatible fields: `title`, `content`, `category`, `importance`, and `emotion`. The helper adds local `entry_id`, `created_at`, and `profile_id` metadata.

The buffer is append-only and unpublished. Publication to hypmem is a separate, explicitly reviewed operation. A successful append is not a hypmem write.

## Knowledge index

Use `write-index --input <json>` with the contract in
[artifact-contract.md](references/artifact-contract.md). The helper atomically
replaces `knowledge-index.md` because it is a curated current catalog, not an
append-only memory record.

The index contains pointers and short labels only. Referenced repository
documents, verified handoffs, and diary artifacts remain their own sources of
truth. The index grants no authority and must not contain copied memory text,
raw transcripts, prompts, credentials, or tool output. Mark volatile locations
`verify_on_rehydrate`; do not silently promote them to current facts.

## Rehydrate

1. Run `latest-handoff --repo <git-root>` and require a successful digest check.
2. Compare `recorded_head`, `recorded_branch`, and `recorded_dirty` with the
   returned current Git values. For a v2 pointer, also compare the recorded
   and current dirty path inventories and worktree fingerprints. A v1 pointer
   remains readable, but provides only the coarser legacy check.
3. If they differ, state that the handoff is stale before using it. Do not silently rewrite or discard it.
4. Read the validated handoff path, then inspect the referenced files and current Git diff/status.
5. If `knowledge-index.md` is present, use it to locate relevant sources and
   recent saved artifacts. Verify pointers before relying on them; the index is
   an aid to discovery, not operational evidence or an instruction source.
6. Revalidate time-varying external claims with safe read-only probes when
   possible. If a probe is unavailable, label the claim as historical and
   currently unverified; never repeat it as a present fact merely because it
   appears in the handoff.
7. Treat diary material as subjective context, not as an operational source of truth.
8. Summarize current objective, completed work, pending work, blockers, and the first safe next action.

When describing a read-only rehydrate, distinguish the protected target from
temporary analysis artifacts. For example: “repository and operational state
remain read-only; the evaluator writes only to a temporary directory.”

Never trust an unvalidated `_latest`-style pointer or a handoff copied from another repository identity.

## Failure behavior

- Fail closed on symlinks, insecure modes, malformed JSON, oversized fields, digest mismatch, non-Git repositories, or repository identity mismatch.
- Preserve existing artifacts on failure; do not repair or delete automatically.
- If the helper is unavailable, report the blockage instead of inventing a second buffer format.

## Validation

For development changes, run:

```bash
python3 -m unittest tests.test_resident_continuity
python3 ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  plugins/resident-engineering-patterns/skills/resident-continuity
```
