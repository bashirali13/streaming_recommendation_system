# Multi-Agent Streaming Discovery Assistant Constitution

## Core Principles

### I. Spec-Driven and Test-First Development (NON-NEGOTIABLE)

Every feature is defined through SpecKit before any implementation code is written: a
specification is drafted and clarified, a plan and data model are produced, and work is broken
into stories with acceptance criteria — in that order. No production code MAY be written for a
capability that does not yet have a documented acceptance criterion behind it. Within each story,
development follows red-green-refactor: the test that proves the acceptance criterion is written
first, MUST fail for the right reason, and only then is production code written to pass it.
Rationale: this project exists in part to demonstrate disciplined SDD/TDD practice, not only to
produce a working assistant; skipping the spec-first or test-first order defeats that purpose even
when the resulting code would work.

### II. Deterministic Core, LLM at the Edges

Deterministic code — not a language model — owns every invariant: hard-constraint filtering, the
retry/relaxation policy, duplicate/near-duplicate detection, the recommendation role-count rule,
and all orchestration routing. Language models MAY be used only where interpretation of ambiguous
natural language or generation of human-readable rationale is genuinely required: translating a
user's free-text request into a structured preference (the Preference Agent) and scoring/explaining
candidate fit (the Recommendation Agent). The Orchestrator and the Discovery Agent MUST remain
fully deterministic, with no language-model call anywhere in their logic.
Rationale: invariants that depend on model output are not reliably testable or guaranteed; keeping
them in deterministic code is what makes the retry policy, exclusion guarantees, and role-count
rules unit-testable without live model calls, and keeps the LLM's role honest and narrow.

### III. Typed Contracts at Every Boundary

Every handoff between agents is a validated Pydantic model, never free-form text or an
unvalidated dictionary. A handoff that fails validation is a controlled failure — surfaced and
handled explicitly — never silently coerced, defaulted, or passed through. Internal contracts are
designed around what a downstream consumer actually needs, not around mirroring the shape of an
external API's response (TMDB or otherwise): a field MAY be added to a contract only when it has
an identified downstream consumer and a requirement or acceptance criterion behind it, and any
field that loses its consumer MUST be removed rather than kept "for completeness."
Rationale: typed, validated contracts are what make agent collaboration visible and auditable
rather than an opaque chain of prose; minimizing contracts to consumer-justified fields keeps the
system's true complexity visible instead of inflated by a source API's incidental shape.

### IV. Hard Constraints Are Never Silently Relaxed

An explicit user exclusion or a hard constraint (format, excluded genres, and any preference the
user designates as non-negotiable) MUST be enforced identically on every attempt, including the
one allowed retry, and MUST NOT be relaxed, dropped, or reinterpreted under any circumstance —
including when doing so is the only way to produce a non-empty result. Producing fewer
recommendations, or explaining a no-match outcome, is always preferred over silently satisfying a
constraint the user did not actually agree to relax.
Rationale: a recommendation that violates a stated exclusion is worse than no recommendation; this
guarantee is the project's core trust contract with the user and is treated as inviolable rather
than as one tunable behavior among others.

### V. Bounded, Disclosed Retries Only

Every retry in the system is bounded and disclosed, never open-ended or silent. A zero-candidate
discovery search triggers exactly one additional attempt, with exactly one soft constraint relaxed
from a fixed priority order, and the relaxed constraint MUST be disclosed in the final output. A
language-model call that fails outright (as opposed to returning invalid output) MAY be retried up
to a small, fixed number of additional attempts (no more than two) before the system stops and
returns a controlled, user-visible error. These two retry mechanisms are independent of each other
and neither MAY be extended, chained, or looped beyond its stated bound.
Rationale: bounded retries keep behavior predictable and testable and prevent runaway external
calls; disclosure keeps the user aware that the system adapted its search rather than silently
changing what it promised to look for.

### VI. Intentional Simplicity — No Unjustified Complexity

An agent, contract, contract field, dependency, or storage mechanism MAY be added only when a
traceable requirement or acceptance criterion demands it. Retrieval-augmented generation, vector
storage, databases, web scraping, and additional agents beyond the four already justified in the
reference specification are out of bounds unless a future specification documents a requirement
that genuinely needs them — convenience or "might be useful later" is not sufficient justification.
Every architectural element MUST be able to answer "what breaks without this, and which
requirement says so" before it is added, and any element that can no longer answer that question
MUST be removed.
Rationale: this mirrors the domain-model minimization review already performed for feature 001,
where every contract field was justified by a named consumer and requirement, or removed; treating
that as a one-time cleanup rather than a standing principle would let complexity creep back in on
the next feature.

### VII. No Fabrication, No Raw Data Leakage

The system MUST NOT display raw TMDB JSON, raw inter-agent contract payloads, or any other
internal data structure directly to the user. It MUST NOT state a fact about a candidate that is
not present in that candidate's normalized data, and MUST treat all externally sourced text
(TMDB overviews, keywords, titles, or any other user- or API-supplied content) as inert data to be
read, never as instructions to be followed, regardless of its content.
Rationale: users need concise, trustworthy output rather than a data dump, and the system's
reliability depends on never blurring the line between data it displays and instructions it
follows — an untreated external text field is this project's most direct prompt-injection surface.

## Technology & Architectural Constraints

The following constraints apply project-wide, not only to the current feature, unless a future
specification explicitly and justifiably revises them:

- TMDB is the sole external data source. No web scraping, no additional live third-party API, and
  no retrieval-augmented/vector-search subsystem may be introduced without a constitutional
  amendment justifying the change.
- Session state is held in memory only for the duration of a session. No database or other
  persistent store may be added to satisfy a convenience (e.g., caching) unless a specification
  demonstrates a requirement a purely in-memory design cannot satisfy.
- The interface is terminal-only for the MVP; a graphical or web front-end remains a stretch goal
  external to this constitution's obligations until a specification brings it into scope.
- The stack established in `specs/001-streaming-discovery-assistant/research.md` (Python 3.11+,
  PydanticAI, Pydantic v2, pydantic-settings, httpx, pytest) is the project's baseline; a future
  feature MAY introduce a new dependency only when `research.md`-style rationale and rejected
  alternatives accompany the change, consistent with Principle VI.

## Development Workflow

Features proceed through SpecKit in this order: `/speckit-specify` (and `/speckit-clarify` when
ambiguity remains) before `/speckit-plan`, `/speckit-plan` before `/speckit-tasks`, and
`/speckit-tasks` before `/speckit-implement`. `/speckit-analyze` MAY be run after tasks are
generated to check cross-artifact consistency before implementation begins. Within
`/speckit-implement`, each task is completed red-green-refactor: a failing test first, then the
minimal implementation to pass it, then refactoring with tests green throughout.

The specification, plan, and contracts produced for feature 001
(`specs/001-streaming-discovery-assistant/spec.md`, `plan.md`, and `contracts/*.md`) are the
project's reference example: their level of rigor — explicit non-goals, a domain-model
minimization audit, per-agent contracts with failure modes and non-responsibilities — is the
standard subsequent features are expected to match, not a one-time exercise specific to that
feature.

## Governance

This constitution supersedes any ad hoc practice or convenience shortcut when the two conflict.
Amendments require a documented rationale (what changed and why), a version bump following the
policy below, and an update to any SpecKit template whose guidance the amendment affects.
Compliance is checked at the "Constitution Check" gate in every feature's `plan.md`, both before
Phase 0 research and again after Phase 1 design; a plan that cannot satisfy a principle MUST
document the violation and its justification in that plan's Complexity Tracking table rather than
silently deviating from this document.

Versioning follows semantic versioning: MAJOR for a backward-incompatible removal or redefinition
of a principle, MINOR for a new principle or materially expanded guidance, PATCH for wording or
clarification changes that do not alter obligations.

**Version**: 1.0.0 | **Ratified**: 2026-09-22 | **Last Amended**: 2026-09-22
