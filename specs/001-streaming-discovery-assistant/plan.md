# Implementation Plan: Multi-Agent Streaming Discovery Assistant (MVP)

**Branch**: `001-streaming-discovery-assistant` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-streaming-discovery-assistant/spec.md`

**Note**: This template is filled in by the `/speckit-plan` command; its definition describes the execution workflow.

## Summary

A terminal-based assistant that turns a vague or specific natural-language request into three curated picks (Best Match, Safe Pick, Wildcard Pick — or fewer, when fewer genuinely qualify) by routing it through four cooperating agents — Orchestrator, Preference Agent, Discovery Agent, Recommendation Agent — that hand off validated Pydantic contracts rather than free text. TMDB is the sole external data source, accessed through an adapter that normalizes its response into a domain model shaped by consumer need rather than by TMDB's own payload shape (see `data-model.md`). A single deterministic retry relaxes at most one soft constraint when the initial search returns zero candidates; hard constraints and explicit exclusions are never relaxed. Only the Preference Agent and Recommendation Agent invoke a language model; the Orchestrator and Discovery Agent are fully deterministic. The technical approach (PydanticAI for agent/contract enforcement, httpx for the TMDB adapter, pydantic-settings for configuration, a Protocol-based fixture/fake layer for the credential-free demo mode) is detailed in `research.md`.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: PydanticAI (agent orchestration with typed, validated outputs), Pydantic v2 (all contract schemas), pydantic-settings (configuration, incl. `REGION`), httpx (TMDB adapter HTTP client), pytest + pytest-asyncio (testing)

**Storage**: N/A — in-memory session state only (FR-023); optional end-of-session export to a JSON or Markdown file is a one-time write-out, not a persistence layer

**Testing**: pytest, with Protocol-typed fake TMDB and model-call implementations backing recorded fixture data, so the full suite (unit, contract, integration, end-to-end, adversarial) runs without live credentials (NFR-004)

**Target Platform**: Cross-platform terminal/CLI; developed on Windows, runs anywhere Python 3.11+ runs

**Project Type**: Single project — CLI application (no frontend/backend split; a graphical front-end is an explicit non-goal)

**Performance Goals**: No hard latency target — this is a single-user interactive CLI session, not a service under load. The fixture-backed demo mode must run with zero network calls.

**Constraints**: Exactly one discovery retry per request (NFR-007); TMDB access isolated behind a single timeout-bounded adapter (NFR-003); at most 1–2 additional attempts for a failed LLM call before a controlled error (FR-028); no raw TMDB JSON or raw inter-agent JSON ever reaches the terminal (FR-008, FR-021); no persistent storage (FR-023)

**Scale/Scope**: Single user, single session; MVP scope is 4 agents, 6 core contracts (`PreferenceProfile`, `DiscoveryQuery`, `CandidateMedia`, `CandidatePool`, `RecommendationPackage`, `UserSessionState`), and 30 functional + 8 non-functional requirements

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

**Re-evaluated 2026-09-22 against constitution v1.0.0** (ratified after this plan's original draft; this section was stale until this pass — see the `001-streaming-discovery-assistant` process log for that finding). Checked against all 7 principles:

| Principle | Status | Basis |
|---|---|---|
| I. Spec-Driven and Test-First | ✅ Pass | `tasks.md` orders a failing test before every implementation task |
| II. Deterministic Core, LLM at the Edges | ✅ Pass | NFR-008; only Preference/Recommendation agents hold a `ModelProvider` dependency |
| III. Typed Contracts at Every Boundary | ✅ Pass | data-model.md's six contracts, all consumer-justified per FR-030 |
| IV. Hard Constraints Never Silently Relaxed | ✅ Pass | FR-010; `DiscoveryQuery` validation rule holds `excluded_genres`/`media_type`/hard-override fields identical across retry attempts |
| V. Bounded, Disclosed Retries Only | ✅ Pass | FR-011/FR-028; both retry mechanisms capped and independent |
| VI. Intentional Simplicity | ✅ Pass | spec.md's Domain Model Minimization Rationale; no agent/contract beyond the four/six already justified |
| VII. No Fabrication, No Raw Data Leakage | ✅ Pass | FR-008, FR-021, FR-026 |

No violation found; **Complexity Tracking below remains empty.**

## Project Structure

### Documentation (this feature)

```text
specs/001-streaming-discovery-assistant/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/             # Phase 1 output (/speckit-plan command)
│   ├── preference-agent.md
│   ├── discovery-agent.md
│   ├── recommendation-agent.md
│   └── orchestrator.md
└── tasks.md              # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
src/
└── streaming_discovery/
    ├── contracts/          # Pydantic models: PreferenceProfile, DiscoveryQuery, CandidateMedia,
    │                       # CandidatePool, RecommendationPackage, UserSessionState, shared enums
    ├── agents/
    │   ├── preference_agent.py     # LLM-backed (PydanticAI); see contracts/preference-agent.md
    │   ├── discovery_agent.py      # Deterministic; see contracts/discovery-agent.md
    │   ├── recommendation_agent.py # LLM-backed (PydanticAI); see contracts/recommendation-agent.md
    │   └── orchestrator.py         # Deterministic; see contracts/orchestrator.md
    ├── tmdb/
    │   ├── client.py        # httpx-based real TMDB adapter (timeouts, pagination bounds)
    │   ├── fake_client.py   # Fixture-backed fake adapter for demo mode / tests (NFR-004)
    │   └── normalize.py     # Raw TMDB payload -> CandidateMedia (genre-id resolution, region/flatrate scoping)
    ├── llm/
    │   ├── provider.py      # Model-agnostic interface + bounded-retry wrapper (FR-028)
    │   └── fake_provider.py # Deterministic fixture-backed fake for demo mode / tests
    ├── cli/
    │   ├── intake.py        # Guided intake prompts, confirmation/correction step
    │   └── output.py        # Terminal rendering of RecommendationPackage (no raw JSON — FR-021)
    └── config.py             # pydantic-settings: REGION, retry bounds, demo-mode flag

tests/
├── unit/           # Preference parsing helpers, hard filters, scoring rules, relaxation policy, uniqueness rules
├── contract/        # Valid/invalid payloads for every contract in contracts/
├── tmdb_adapter/     # Success, pagination, empty-result, timeout, HTTP-error, malformed-response, region fixtures
├── integration/      # Orchestrator sequencing, zero-result retry, downstream contract passing, controlled failure
├── e2e/              # One test per quickstart.md scenario (vague, specific, similarity, runtime retry x2, exclusion, guided, TMDB failure, LLM failure)
├── adversarial/      # Conflicting constraints, unsupported vibe language, prompt injection, duplicate candidates, malformed LLM output
└── fixtures/         # Recorded TMDB payloads and fake LLM responses backing all of the above
```

**Structure Decision**: Single project (Option 1) — a plain CLI application with no frontend/backend split. The `src/streaming_discovery/` package is organized by architectural role (contracts, agents, external adapters, CLI) rather than by feature, since this MVP is one feature; `contracts/` at the top level mirrors the four contract-boundary documents under `specs/001-streaming-discovery-assistant/contracts/` one-to-one, and `tmdb/`/`llm/` each split into a real and a fixture-backed fake implementation behind the same interface per `research.md` §5, which is what makes the credential-free demo mode (FR-025) and the adversarial/contract test suites possible without any live network or model access.

## Complexity Tracking

*No entries — the Constitution Check (v1.0.0, re-evaluated above) found no violation, and the spec's own Domain Model Minimization Rationale already removed every contract/field/agent identified as unnecessary during review. No additional complexity beyond the four agents and six contracts already justified in `spec.md` is introduced by this plan.*
