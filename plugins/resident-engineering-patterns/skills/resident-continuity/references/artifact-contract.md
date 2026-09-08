# Resident continuity artifact contract

All input is UTF-8 JSON. Use a temporary file or stdin (`--input -`); do not put diary text on a command line where shell history can retain it.

## Diary input

```json
{
  "title": "A short title",
  "content": "First-person subjective prose.",
  "category": "technical, reflective",
  "importance": 4,
  "emotion": "satisfied, cautious"
}
```

`category` and `emotion` may be null. Importance is an integer from 1 through 5. Content is bounded to 12,000 UTF-8 bytes. The helper generates `entry_id`, `created_at`, and `profile_id`.

## Knowledge index input

```json
{
  "purpose": "Locate resident knowledge without duplicating it.",
  "locations": [
    {
      "topic": "Environment architecture",
      "source": "codex-environment/docs/meta-self-agent-ecosystem.md",
      "authority": "reference",
      "freshness": "repo_head"
    }
  ],
  "recent_artifacts": [
    {
      "observed_at": "2026-07-20T02:30:00Z",
      "topic": "Standalone harness plan",
      "source": "codex-environment/docs/meta-self-agent-ecosystem.md"
    }
  ],
  "open_loops": ["Revalidate the latest handoff before resuming work."]
}
```

`locations` has 1 through 64 entries. `recent_artifacts` and `open_loops`
have at most 32 entries each. Authority is one of `normative`, `operational`,
`reference`, or `subjective`; freshness is one of `repo_head`,
`verify_on_rehydrate`, `historical`, or `append_only`.

The helper writes `knowledge-index.md` atomically with mode 0600. It is a
mutable pointer catalog, not a handoff snapshot or memory store. Sources and
labels must not contain raw transcripts, prompts, credentials, tool output, or
copied memory content.

## Handoff input

```json
{
  "objective": "The current bounded objective.",
  "completed": ["Verified completed outcome."],
  "pending": ["Unfinished next action."],
  "decisions": ["Decision and its owner."],
  "blockers": [],
  "verification": ["Command or evidence and result."],
  "files": ["relative/path.md"]
}
```

Each list has at most 32 entries; each entry is at most 1,000 UTF-8 bytes. `objective` is at most 2,000 bytes. The helper reads the canonical Git root, branch, HEAD, and dirty state directly. It does not commit or clean the worktree.

Time-varying external state belongs in the most relevant list, but must use a
bounded freshness prefix:

```text
[observed_at=2026-07-20T01:24:13Z; rehydrate=required] The user timer was unavailable from the sandbox.
```

This convention applies to quota, daemon, timer, network, service, and other
claims that can change without a Git commit. On rehydrate, these are historical
observations until a fresh read-only probe confirms them. An unavailable probe
must remain explicitly unverified.

## Handoff snapshot versions

- `resident-codex-handoff/v1` records branch, HEAD, and a dirty boolean.
- `resident-codex-handoff/v2` additionally records a bounded sorted inventory
  of at most 256 dirty repo-relative paths and a worktree fingerprint. The
  fingerprint covers Git status, tracked diffs, and untracked file content but
  stores none of that raw content. Fingerprinting fails closed after 64 MiB of
  tracked diff or total untracked content.
- The latest pointer schema v2 carries the dirty path count, path inventory,
  and fingerprint. Readers retain v1 compatibility and identify which pointer
  schema was used in their result.

## Private state

- State directories: mode 0700.
- Artifacts and pointers: mode 0600.
- Diary buffer: append-only Markdown compatible with `hypmem-codex-diary-buffer/v1`.
- Handoff snapshots: immutable, repository-scoped, SHA-256 verified.
- Latest pointer: atomic JSON replacement containing only the snapshot name, digest, and repository identity hash.

Handoffs are operational evidence. Diary entries are subjective records. Neither is automatically recalled or published.
