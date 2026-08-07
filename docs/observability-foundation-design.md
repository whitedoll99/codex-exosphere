# Codex observability foundation

## Status and decision owner

Status: approved direction, MVP contract for implementation.
Decision owner: the resident Codex under the user's product direction.

This component observes local CLI-agent work. It does not authorize work,
start agents, read external message or memory stores, or become a control plane.

## Problem framing

The resident Codex environment can delegate bounded implementation to Luna and
review the resulting work, but the operational evidence is scattered across
ephemeral metrics and conversational reports. The user cannot answer, over
time, how often delegation succeeds, where fix rounds originate, what Skills
are actually used, or how cost and scope decisions vary by task type.

The primary actors are:

- the user, who needs a local overview without exposing task content;
- the resident Codex, which owns routing, review, and final decisions;
- delegated workers and adapters, which emit bounded operational facts;
- a future read-only WebUI, which consumes the same stable query contract as
  the CLI.

The smallest useful boundary is a portable local event store with a strict
content-free schema, deterministic summaries, a CLI, and an authenticated
read-only WebUI. The current implementation binds to `0.0.0.0` by default and
also permits loopback binding. Automatic launcher instrumentation, external
notifications, memory views, write controls, and remote hosting remain separate
rounds.

## Success and failure signals

The MVP succeeds when:

- a caller can record a versioned event without a daemon;
- invalid, unknown, oversized, or content-bearing fields fail closed;
- summaries expose delegation outcome, fix rounds, review findings, cost,
  Skills, scope results, and decision returns;
- CLI and WebUI read the same SQLite data and agree on totals;
- a new Linux VM can install it without fixed usernames or repository paths;
- the WebUI cannot mutate data or start work;
- no prompt, message, diff, source text, absolute path, session transcript, or
  credential is accepted by the event contract.

Failure signals include silent schema coercion, unauthenticated API reads,
runtime data written into the source checkout, arbitrary metadata fields,
write-capable HTTP routes, or a required dependency outside Python 3.10+
stdlib and SQLite.

## Quality scenarios

| Attribute | Scenario and required response |
| --- | --- |
| Privacy | An emitter attempts to include an unknown content field; validation rejects the whole event before a database transaction. |
| Security | A LAN process requests an API endpoint without the per-process bearer token; the server returns 401 and no data. |
| Portability | The repository is installed under a different HOME/CODEX_HOME; the launcher resolves its package relative to itself and runtime data defaults to XDG state. |
| Reliability | The same `event_id` is retried; insertion is idempotent only when the normalized event is identical, otherwise it conflicts. |
| Operability | The WebUI is unavailable; event recording and CLI summaries continue without a daemon. |
| Compatibility | A future event schema is encountered; v1 rejects it rather than partially recording unknown semantics. |
| Boundedness | A query requests an excessive limit or date range; the API and CLI clamp or reject it at the boundary. |

## Architecture decision

Adopt a Python-stdlib component installed as one directory plus a thin
executable:

```text
emitters / explicit CLI
          │ validated event v1
          ▼
  codex_observability
    model.py    exact schema and normalization
    store.py    SQLite schema, transactions, queries
    cli.py      emit, import-luna, summary, tasks, serve
    web.py      token-protected read-only HTTP/API
    static/     local HTML/CSS/JS; no external assets
          │
          ▼
$XDG_STATE_HOME/codex-observability/events.sqlite3
```

SQLite is preferred over JSONL because task timelines and aggregates require
indexed queries and atomic idempotency. A daemon is rejected for recording:
it adds lifecycle and delivery failure modes without helping a single-user
local writer. A general telemetry stack is rejected because it adds services,
egress risk, dependencies, and recurring operational cost.

The component has no imports from bootstrap, evals, Luna, external transports,
or memory systems. That boundary keeps it independently reusable.

## Event contract v1

Input is one UTF-8 JSON object, at most 32 KiB, with exactly these fields:
The distributable machine-readable shape is
`codex_observability/schema/event-v1.schema.json`; semantic cross-field and
cross-event invariants remain normative in this document and the validator.

```json
{
  "schema_version": 1,
  "event_id": "018f...",
  "occurred_at": "2026-07-16T12:00:00Z",
  "task_id": "task-20260716-001",
  "run_id": "run-01",
  "event_type": "delegation.completed",
  "actor": "luna",
  "emitter": "luna-launcher",
  "task_kind": "implementation",
  "outcome": "succeeded",
  "model": "gpt-5.6-luna",
  "reasoning_effort": "xhigh",
  "duration_ms": 23000,
  "input_tokens": 24559,
  "cached_input_tokens": 17920,
  "output_tokens": 822,
  "skills": ["bounded-tdd", "verification-before-reporting"],
  "fix_round": 0,
  "finding_count": 0,
  "scope_status": "passed",
  "decision_reason": null
}
```

### Enumerations

- `event_type`: `task.started`, `task.completed`, `delegation.started`,
  `delegation.completed`, `review.completed`, `fix_round.started`,
  `decision.returned`, `scope.checked`
- `actor`: `user`, `sol`, `luna`, `reviewer`, `system`
- `emitter`: a bounded ASCII identifier naming the adapter that produced the
  observation, such as `manual-cli` or `luna-launcher`
- `task_kind`: `implementation`, `review`, `research`, `documentation`,
  `operations`, `unknown`
- `outcome`: `started`, `succeeded`, `failed`, `returned`, `rejected`,
  `adopted`, `partial`, `unknown`
- `scope_status`: `passed`, `violated`, `not_checked`
- `decision_reason`: null or one of `architecture`, `compatibility`,
  `authorization`, `scope`, `security`, `requirements`, `work_budget`, `other`

### Validation and privacy invariants

- Unknown and missing fields are rejected; nullable fields remain present.
- IDs and labels are bounded ASCII identifiers, not natural-language content.
- Timestamps are UTC RFC 3339 with second precision and canonical `Z` suffix.
- Token counts, duration, rounds, and findings are non-negative bounded
  integers. Cached input cannot exceed input.
- Skills are a sorted unique list of bounded identifiers.
- `model`, `reasoning_effort`, duration/token counts, `fix_round`,
  `finding_count`, and `decision_reason` are nullable when not applicable. A
  numeric zero means observed zero; null means not observed or not applicable.
- Started events have outcome `started`; `decision.returned` has outcome
  `returned`; `scope.checked` pairs `passed` with `succeeded` and `violated`
  with `failed`. Other completion outcomes remain explicit.
- `event_id` is the idempotency key. Retrying an identical normalized event is
  a no-op; the same ID with different content is a conflict.
- One `task_id` has one stable `task_kind`, and one `run_id` belongs to one
  task. Conflicting reuse is rejected atomically by the database.
- No arbitrary attributes, filenames, paths, prompts, summaries, messages,
  commands, URLs, or free-text errors are accepted.

## Persistence contract

- Database schema version is stored in `PRAGMA user_version` and only version
  1 is accepted by this MVP.
- Parent directories are created mode 0700 and new database files mode 0600.
- Writes use one SQLite transaction; foreign-key and integrity errors do not
  produce partial events.
- The store keeps normalized JSON alongside indexed columns. This preserves
  exact idempotency and future export without accepting arbitrary data.
- Runtime data is never installed into or committed with the source tree.
- Retention and deletion are deliberately absent from MVP; adding them needs a
  separate policy and migration decision.
- Tasks and runs are observational groupings, not mutable entities. Missing or
  out-of-order lifecycle events remain representable because instrumentation
  may begin mid-task. Queries order by event time and then insertion sequence.
- One database represents one local environment. Cross-host merging and a
  portable environment identity are outside MVP and require a separate
  identity decision.

## CLI contract

```text
codex-observe emit --file EVENT.json [--db PATH]
codex-observe import-luna --metrics FILE --task-id ID --run-id ID \
  --event-id ID --occurred-at TIMESTAMP --task-kind KIND [--db PATH]
codex-observe summary [--db PATH] [--json]
codex-observe tasks [--db PATH] [--limit 1..200] [--json]
codex-observe task TASK_ID [--db PATH] [--json]
codex-observe serve [--db PATH] [--host 0.0.0.0|127.0.0.1] [--port 0]
```

`import-luna` only maps the safe subset of launcher metrics. It does not read
the result packet, prompt, diff, stderr, or workspace. Import is explicit in
the MVP; launcher integration is not implied.

## Read-only HTTP contract

The exposure vocabulary separates bind reachability from authentication:

- `trusted-lan`: `0.0.0.0`, no authentication, and all reachable LAN clients
  are trusted. This remains a public-harness option but is not implemented by
  this repository.
- `loopback`: `127.0.0.1`, no authentication, and the host boundary is trusted.
  This remains a public-harness option but is not implemented by this
  repository.
- `authenticated`: `0.0.0.0` by default or `127.0.0.1` when selected, with an
  ephemeral bearer required for every `/api/` request. This repository
  implements this mode.

- `GET /` and static assets are public but contain no data.
- `GET /api/v1/summary`
- `GET /api/v1/tasks?limit=N`
- `GET /api/v1/tasks/{task_id}`
- all `/api/` requests require `Authorization: Bearer <ephemeral-token>`;
- all non-GET methods return 405; unknown paths return 404;
- responses set no-store, frame denial, MIME-sniff denial, and a restrictive
  Content Security Policy;
- default bind is `0.0.0.0` for direct access to the personal development VM;
  `127.0.0.1` remains available, while arbitrary interface addresses are
  rejected;
- the token is generated per process, printed as a URL fragment, never stored
  in the database or HTTP logs.

The fragment is consumed by local JavaScript and sent only as an Authorization
header. The server uses no request logging and exposes no filesystem paths.
Binding to all interfaces intentionally exposes the static UI and authenticated
API to the VM's reachable network; bearer secrecy is therefore the remaining
read boundary. TLS and Internet-facing deployment remain outside this personal
development profile.

## Compatibility and later rounds

- Schema v1 is fail-closed. New event fields or enums require schema v2 or an
  explicitly backward-compatible contract revision.
- The first automatic emitter should be the Luna launcher after the store and
  privacy behavior have real-task evidence.
- External notifications, memory views, and tool-registry observations may emit
  their own events later, but they do not gain control-plane authority.
- A future shared portal may present multiple backends; it must keep their
  data, authentication, and mutation capabilities separate.
