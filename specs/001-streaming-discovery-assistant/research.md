# Phase 0 Research: Multi-Agent Streaming Discovery Assistant (MVP)

**Feature**: `001-streaming-discovery-assistant` | **Date**: 2026-09-22

This document resolves the technical unknowns needed to move from `spec.md` (WHAT/WHY) into `data-model.md` and `contracts/` (HOW). Each decision below responds to a specific requirement or non-functional requirement in the spec, not to a preference stated in isolation.

## 1. Multi-agent framework

**Decision**: PydanticAI.

**Rationale**: The spec's core structural requirement (FR-022, NFR-002) is that every inter-agent handoff validates against a typed contract. PydanticAI agents declare their output type as a Pydantic model and validate against it natively, so contract validation is enforced by the framework at the boundary rather than bolted on afterward. The pipeline itself is a small, fixed, linear sequence with one bounded retry (Orchestrator → Preference → Discovery → Recommendation) — it does not need a general-purpose graph/state-machine orchestration engine.

**Alternatives considered**:
- **LangGraph** — rejected. Its graph/node/state abstraction is built for branching, cyclical, or dynamically-routed agent topologies. This pipeline's routing (including the retry) is fully deterministic and owned by the Orchestrator per NFR-001; adopting a graph framework would add an abstraction layer the design doesn't need and would obscure, rather than clarify, that the routing logic is plain deterministic code.
- **Hand-rolled function-calling loop** (direct provider SDK calls) — rejected. It would require re-implementing schema validation and retry plumbing that PydanticAI already provides, increasing surface area without a corresponding benefit.

## 2. Language-model provider

**Decision**: Keep the model/provider selection strictly as a runtime configuration value behind PydanticAI's model-agnostic interface, defaulting to the project outline's stated target (DeepSeek v4 Flash via OpenRouter) for the Preference Agent and Recommendation Agent — the only two components that call a model at all (NFR-008).

**Rationale**: NFR-004 and FR-025 require the full pipeline to run in a fixture-backed demo mode with **no** live model credentials, which already forces the code to depend on an abstract "preference interpreter" / "rationale generator" interface rather than a concrete provider SDK. Given that abstraction has to exist anyway, the concrete default provider is a configuration detail, not an architectural one — it does not affect any contract, agent boundary, or requirement in the spec.

**Alternatives considered**:
- **Anthropic Claude models via the native API** — not adopted as the default only because the outline explicitly names DeepSeek/OpenRouter as the integration to demonstrate; remains a same-effort swap given the model-agnostic design, and is a reasonable fallback if OpenRouter access is unavailable during implementation.

## 3. TMDB HTTP client

**Decision**: `httpx`.

**Rationale**: PydanticAI tools are commonly invoked from an async agent run loop; `httpx` supports both sync and async clients from one library, so the TMDB adapter (NFR-003) can expose an async interface without forcing a second HTTP dependency later. It also has first-class timeout and connection-pooling controls, which the adapter needs to satisfy NFR-003's timeout/bounded-call requirement directly.

**Alternatives considered**:
- **`requests`** — rejected. Sync-only; would force a sync/async boundary wrapper around an otherwise async-capable agent framework for no benefit.

## 4. Configuration management (region, retry bounds, credentials)

**Decision**: `pydantic-settings`, reading from environment variables (e.g., `REGION`, defaulting to `US` per FR-020) with typed, validated fields.

**Rationale**: The project already depends on Pydantic v2 for every domain contract (NFR-002); `pydantic-settings` reuses that same validation model for configuration instead of introducing a second, unrelated config library. It also gives the "hardcoded fallback default" required by FR-020 a natural expression (a field default).

**Alternatives considered**:
- **Plain `os.environ` reads with manual defaults** — rejected. Works, but reintroduces ad hoc validation the project has already standardized on Pydantic for elsewhere; using a second pattern for config only would be an unjustified inconsistency.

## 5. Fixture-backed demo mode (NFR-004, FR-025)

**Decision**: Define the TMDB adapter and the model-calling interface as small `Protocol`-typed ports, each with a real implementation and a fixture-backed fake implementation. A single configuration flag selects which implementation set is wired in.

**Rationale**: This is the only design that satisfies FR-025's requirement literally — a full pipeline run, retry path included, with no live TMDB or model credentials — without duplicating agent logic between a "demo" code path and a "real" code path. The agents (Preference, Discovery, Recommendation) depend only on the port interface; which implementation backs it is an assembly-time decision, not something any agent branches on.

**Alternatives considered**:
- **`unittest.mock`/monkeypatching at test time only** — rejected as the sole mechanism. It covers automated tests but not FR-025's separate requirement for a runnable, demonstrable fixture-backed mode outside of pytest (e.g., for a live walkthrough).

## 6. Retry mechanics for LLM-call failures (FR-028)

**Decision**: A small inline bounded-retry helper (fixed 1–2 additional attempts, short fixed delay), not a general-purpose retry library.

**Rationale**: The policy is a fixed, tiny bound with no backoff curve, jitter, or per-exception routing requirement — a few lines of code express it completely and transparently, which also keeps it trivially unit-testable per NFR-001 without mocking a third-party retry decorator's internals.

**Alternatives considered**:
- **`tenacity`** — rejected for MVP. Its configurable backoff/jitter/predicate machinery solves problems this fixed 1–2-attempt policy doesn't have; adopting it would add a dependency and an indirection layer disproportionate to the requirement.

## 7. Terminal I/O

**Decision**: Standard library `input()`/`print()` for the MVP; no CLI or terminal-formatting framework.

**Rationale**: The guiding principle in the outline ("keep the project simple but intentional") and the non-goal excluding a front-end both point toward the smallest interface that satisfies the guided-intake and confirmation flow (FR-002, FR-006). Nothing in the spec requires rich terminal formatting (colors, tables, live spinners); adding one would be a dependency with no requirement behind it, which FR-030's "every element needs a named consumer" principle applies to tooling choices as much as to contract fields.

**Alternatives considered**:
- **`rich`** — not adopted now. It's a reasonable, low-risk future enhancement for presentation quality (e.g., formatting the three-role output as cards), but is not required by any current functional or success criterion, so it stays out of the MVP dependency set. Revisit if a later story adds a presentation-quality requirement.

## 8. Test strategy for contract and adversarial tests

**Decision**: `pytest` with fixtures and `pytest.raises(ValidationError)`-style assertions for contract tests; curated fixture cases (not property-based fuzzing) for the adversarial suite.

**Rationale**: The outline's Test Strategy table already enumerates the adversarial cases as a finite, specific list (conflicting constraints, unsupported vibe language, prompt injection, duplicate candidates, malformed LLM output) rather than an open-ended fuzz target. `pytest` plus Pydantic's own validation errors covers every contract-boundary test (NFR-002) without an additional library.

**Alternatives considered**:
- **`hypothesis`** — not adopted for MVP. Valuable for open-ended property testing, but the adversarial cases here are specific and enumerable rather than a property to fuzz over; it would add setup cost without covering a gap the curated fixtures leave open.

## Resolved unknowns summary

| Technical Context field | Resolution |
|---|---|
| Language/Version | Python 3.11+ |
| Primary Dependencies | PydanticAI, Pydantic v2, pydantic-settings, httpx, pytest (+pytest-asyncio) |
| Storage | N/A — in-memory session state only; optional file export (JSON/Markdown) is a write-out, not a persistence layer |
| Testing | pytest, with Protocol-based fake TMDB/model implementations backing fixture data |
| Target Platform | Cross-platform terminal (CLI), developed on Windows, runnable anywhere Python 3.11+ runs |
| Project Type | Single project — CLI application |
| Performance Goals | No hard latency target (single-user interactive CLI, not a service); demo mode must run without any network call |
| Constraints | Bounded TMDB calls (NFR-003/007), bounded LLM retry (FR-028), no persistent storage (FR-023), terminal-only output (no images/raw JSON) |
| Scale/Scope | Single user, single session, MVP scope (4 agents, 5 core contracts, ~30 functional requirements) |
