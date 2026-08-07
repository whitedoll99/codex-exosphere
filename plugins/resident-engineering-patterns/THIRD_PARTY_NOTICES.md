# Third-party provenance

This plugin is an independent adaptation. It is not an upstream release of
either project below.

## Superpowers

- Source: https://github.com/obra/superpowers
- Version reviewed: v6.1.1
- Upstream license: MIT
- Influence: evidence-first debugging, verification before completion,
  test-first implementation, and structured code review workflows.

The included skills were rewritten to preserve repository governance, resident
main-agent accountability, read-only boundaries, and explicit invocation.

## inspired-mino-design-skills

- Source: https://github.com/my-take-dev/inspired-mino-design-skills
- Version reviewed: v0.8.0; compared again at upstream commit `afd50e2`
- Upstream license status when reviewed: no license file identified
- What this repository took from it: the selection of five design-review
  topics, namely problem framing, design by contract, architecture quality
  attributes, domain-model completeness, and interface/implementation
  separation.

The five included skills were written from the primary literature listed below
rather than from the upstream text. A structured comparison performed on
2026-08-07 covered every upstream Markdown file (five `SKILL.md` files, their
per-skill reference workflows, and the 27 `mino-doc` source summaries; 72
files, 15,488 lines). It found no shared section structure beyond a generic
`## Workflow` heading, no shared distinctive terminology in either direction,
and none of the upstream's distinctive analytical devices. The upstream
material is written in Japanese; these skills are written in English and are
roughly 40 percent of the length.

The topic selection above is the part that originates upstream. It is recorded
here because it is real, not because it carries a licence obligation.

## Primary sources for the five design-review skills

These are the works the current skill text traces to. They were identified
twice and independently, by two reviewers working from the skill text without
seeing each other's list, and the lists were compared afterwards.

### problem-framing

No single primary source identified. The content follows ordinary requirements
practice: separating a stated need from a proposed mechanism, recording
evidence and non-goals, and stating success measures in observable terms.

### contract-design

- Bertrand Meyer, "Applying 'Design by Contract'", IEEE Computer, 1992 —
  preconditions, postconditions, and invariants as an observable contract.
- Barbara Liskov and Jeannette M. Wing, "A Behavioral Notion of Subtyping",
  1994 — behaviour that must hold across implementations.

The error taxonomy, idempotency, retry, timeout, observability, and privacy
items are practitioner synthesis with no single identifiable source.

### architecture-quality-analysis

- Rick Kazman, Mark Klein, and Paul Clements, "ATAM: Method for Architecture
  Evaluation", SEI, 2000 — architecture as tradeoffs across quality
  attributes, evaluated against scenarios.
- Len Bass, Paul Clements, and Rick Kazman, "Software Architecture in
  Practice", 2nd edition, 2003 — the quality-attribute scenario template. The
  local skill uses stimulus, environment, affected component, desired
  response, and measurable response, omitting the source element and treating
  the affected component as the artifact.

### domain-model-audit

- Eric Evans, "Domain-Driven Design", 2003 — ubiquitous language, entity
  identity, invariants, and lifecycle.
- Martin Fowler, "Analysis Patterns", 1996 — modelling domain reality
  separately from implementation.
- The time lens draws on Fowler's temporal patterns (actual time versus record
  time) and on stream-processing practice (event time versus processing time).

The provenance, concurrency, and absence lenses are synthesis with no single
identifiable source.

### interface-boundary-audit

- David L. Parnas, "On the Criteria To Be Used in Decomposing Systems into
  Modules", 1972 — information hiding; implementation decisions that are
  expected to change stay replaceable.
- Alistair Cockburn, "Hexagonal Architecture / Ports and Adapters", 2005 —
  capability-shaped boundaries and technology isolation.
- Barbara Liskov and Jeannette M. Wing, "A Behavioral Notion of Subtyping",
  1994 — substitutability across implementations.
- Robert C. Martin, "The Dependency Inversion Principle", 1996 — intended
  direction of dependencies.

The cautions against false abstraction, including one-use pass-through
interfaces and abstractions created only for mocking, have no single
identifiable source.

## Attributed to no external source

The following are written for this harness and are not derived from any work
named above: the precedence and authority sections, approval and ownership
boundaries, the proportionality and operating-context rules, the review
circuit breaker, and the output formats.
