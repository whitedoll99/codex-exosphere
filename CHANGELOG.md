# Changelog

Notable changes to codex-exosphere. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Changed

- Updated the resident default and guarded worker route from GPT-5.6 Sol/Luna
  to GPT-6 Sol/Luna. The model identifiers were verified with read-only live
  canaries on Codex CLI 0.156.0 before changing the routing defaults; Astra
  remains the bounded read-only Oracle.

## [0.2.0] - 2026-09-22

First versioned release of the current Sol Orchestrator / Astra Oracle / Luna
Worker harness. The initial commit extracted a working harness from a private
repository; the entries below cover the work included in this release.

### Added

- A read-only GPT-6 Astra Oracle for difficult problem framing, conflicting
  causal explanations, and design choices that couple multiple contracts.
  Sol remains the decision and verification owner; Oracle advice grants no
  implementation or approval authority.
- `docs/luna-packet.example.json`, a complete packet to copy from. The guard
  requires all eleven fields and rejects unknown ones, so a hand-written packet
  rarely validates on the first try (`6cc7817`).
- A pre-flight step in the Luna section: `luna-packet-guard validate` costs no
  model call and renders exactly what the worker will receive (`6cc7817`).
- A `Verified scope and limitations` section in both READMEs, recording what
  the end-to-end run covered, the six areas it did not, and two behaviours that
  look like defects and are not (`dbd2aea`).
- Continuous integration: the test suite, an install plan, and validation of
  the example packet, on the documented minimum Python and one version above
  it. Running the suite locally leaves fifteen ignored bytecode files behind,
  which is how a working tree drifts without `git status` noticing.

### Changed

- Clarified in both READMEs that Astra's `read-only` setting is an agent-side
  sandbox request and an operating-role constraint, not a mechanically
  guaranteed write barrier when a parent runtime override applies. Mutating
  actions remain outside Oracle authority regardless of effective runtime
  permissions.
- The public routing model is now Sol Orchestrator / Astra Oracle / Luna
  Worker. Both READMEs, installed guidance, responsibility boundaries,
  managed paths, and verification describe the same three-role contract.
- The plugin cachebuster was refreshed to
  `0.2.0+codex.20260921060626`; the plugin's semantic base version remains
  `0.2.0` because this change affects harness routing and managed agents, not
  the plugin skill contract.
- The quick start now uses the concrete GitHub clone URL and documents the
  bootstrap contract for an existing global `AGENTS.md`: missing or identical
  is supported, while different content stops the whole no-clobber install.
- Both READMEs now describe the first resident-Codex-to-Luna user journey and
  preserve the explicit limitation that a fresh authenticated model run has
  not yet been verified.
- Installed global guidance no longer points at a repository-relative contract
  document that is not part of the managed installation.
- The English README states that detailed documents under `docs/` are primarily
  maintained in Japanese.
- The quick start now leads with the three commands that actually install.
  It previously opened by copying and editing `config/local.toml` and passed
  `--local-config` to both install steps, which read as though the file were
  required. It is not (`0c08095`).
- `--local-config` and `verify.py --installed` moved to optional subsections.
  The latter now states that it goes through the Codex CLI, which the other
  commands do not need (`0c08095`).
- The quick start says what to reach for after installing, since the sections
  below it otherwise read as parallel features rather than an order
  (`6cc7817`).

### Removed

- The unused Terra reviewer is no longer installed or advertised as an active
  routing role. Uninstall remains backward compatible with an unchanged
  `terra_reviewer.toml` recorded by an older install state; a locally changed
  file still stops removal fail closed.

## 33759b3 — initial extraction, 2026-08-08

The repository begins as an extraction from a private workbench, not as a
history rewrite: 88 files in a single commit, with no earlier revisions to
scrub. It carries the delegation packet guard, skill routing evaluation,
content-free observability, and the plan/apply bootstrap.
