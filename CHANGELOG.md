# Changelog

Notable changes to codex-exosphere. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

Nothing has been released yet, so no version is cut. The initial commit
extracted a working harness from a private repository; the entries below cover
everything since that extraction.

### Added

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

## 33759b3 — initial extraction, 2026-08-08

The repository begins as an extraction from a private workbench, not as a
history rewrite: 88 files in a single commit, with no earlier revisions to
scrub. It carries the delegation packet guard, skill routing evaluation,
content-free observability, and the plan/apply bootstrap.
