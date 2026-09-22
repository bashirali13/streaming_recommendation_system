---

description: "Task list template for feature implementation"
---

# Tasks: Multi-Agent Streaming Discovery Assistant (MVP)

**Input**: Design documents from `/specs/001-streaming-discovery-assistant/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md, `.specify/memory/constitution.md`

**Tests**: Included and mandatory, not optional. Constitution Principle I (Spec-Driven and Test-First Development, NON-NEGOTIABLE) requires a failing test before any production code for every capability. Every implementation task below has at least one test task ordered before it.

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P3) to enable independent implementation and testing of each story, per Constitution Principle VI (no capability built ahead of the requirement that justifies it).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6, matching spec.md)
- Every task names its exact file path

## Path Conventions

Single project, per plan.md's Structure Decision: `src/streaming_discovery/`, `tests/` at repository root.

---

## Phase 1: Setup

**Purpose**: Project initialization — no story-specific code yet.

- [ ] T001 Create the `src/streaming_discovery/` package (with `contracts/`, `agents/`, `tmdb/`, `llm/`, `cli/` subpackages, each with `__init__.py`) and the `tests/` tree (`unit/`, `contract/`, `tmdb_adapter/`, `integration/`, `e2e/`, `adversarial/`, `fixtures/`), matching plan.md's Project Structure exactly
- [ ] T002 Initialize the Python project in `pyproject.toml`: Python 3.11+ requirement, dependencies `pydantic-ai`, `pydantic>=2`, `pydantic-settings`, `httpx`, dev dependencies `pytest`, `pytest-asyncio`, per research.md §1–4
- [ ] T003 [P] Configure `ruff` (lint + format) in `pyproject.toml`
- [ ] T004 [P] Configure `pytest` in `pyproject.toml` (asyncio mode, `tests/` rootdir, markers for `contract`, `unit`, `integration`, `e2e`, `adversarial`)
- [ ] T005 [P] Add `tests/fixtures/README.md` documenting fixture provenance (recorded TMDB payloads; no live network calls in any automated test, per NFR-004) and the directory layout (`tests/fixtures/tmdb/`, `tests/fixtures/llm/`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The six core contracts (data-model.md), the TMDB and LLM ports with their fixture-backed fakes, configuration, and the Orchestrator's single-attempt skeleton — everything every user story depends on. No user story may begin before this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Shared enums and contracts (data-model.md)

- [ ] T006 [P] Define `MediaType` (`movie`/`tv`/`either`), `RelaxableConstraint` (`tone`/`runtime`/`year_range`), and `RecommendationRole` (`best_match`/`safe_pick`/`wildcard_pick`) enums in `src/streaming_discovery/contracts/enums.py`, per data-model.md "Shared enums"
- [ ] T007 [P] Contract test for the three enums (valid values only; invalid string rejected) in `tests/contract/test_enums.py`
- [ ] T008 [P] Define `PreferenceProfile` in `src/streaming_discovery/contracts/preference_profile.py` with every field from data-model.md's PreferenceProfile table (including `season_count_max` and `hard_override_fields`), enforcing: at least one of `media_type, providers, genres, tone_descriptors, setting_descriptors, theme_descriptors, liked_titles` must be non-empty/non-null, and `year_min <= year_max` when both are set
- [ ] T009 [P] Contract test: valid `PreferenceProfile` payloads accepted; an entirely-empty profile rejected; `year_min > year_max` rejected, in `tests/contract/test_preference_profile.py`
- [ ] T010 [P] Define `DiscoveryQuery` in `src/streaming_discovery/contracts/discovery_query.py` with every field from data-model.md's DiscoveryQuery table (including `season_count_max`), enforcing: `retry_number` is `0` or `1`; `relaxed_constraint` is `None` when `retry_number == 0` and set when `retry_number == 1`
- [ ] T011 [P] Contract test: valid `DiscoveryQuery` payloads for both `retry_number` values; a `retry_number=0` payload with a non-`None` `relaxed_constraint` rejected; a `retry_number=1` payload with `relaxed_constraint=None` rejected, in `tests/contract/test_discovery_query.py`
- [ ] T012 [P] Define `CandidateMedia` in `src/streaming_discovery/contracts/candidate_media.py` with exactly the fields in data-model.md's CandidateMedia table (including `season_count`, excluding every field in spec.md's "fields considered and explicitly excluded" table), enforcing `vote_average` in the closed range `[0.0, 10.0]`
- [ ] T013 [P] Contract test: valid `CandidateMedia` payload accepted; `vote_average` of `-1` or `10.1` rejected; confirm the model has no `genre_ids`, `popularity`, `vote_count`, `poster_path`, or `backdrop_path` field, in `tests/contract/test_candidate_media.py`
- [ ] T014 [P] Define `CandidatePool` in `src/streaming_discovery/contracts/candidate_pool.py` with exactly `candidates`, `relaxed_constraint`, `retry_number`, `error` (no `total_results`, no `retry_required`, per spec.md's Domain Model Minimization Rationale)
- [ ] T015 [P] Contract test: an empty `candidates` list with `error=None` is valid (a legitimate zero-result pool); confirm the model has no `total_results`/`retry_required` field, in `tests/contract/test_candidate_pool.py`
- [ ] T016 [P] Define `Recommendation` (nested: `role`, `candidate`, `rationale`, `confidence_note`) and `RecommendationPackage` (`best_match`, `safe_pick`, `wildcard_pick`, `applied_constraints`, `relaxed_constraint` (singular), `unresolved_notes`) in `src/streaming_discovery/contracts/recommendation_package.py`, enforcing role contiguity (`safe_pick` requires `best_match` set; `wildcard_pick` requires `safe_pick` set) and no two filled roles sharing a `tmdb_id`
- [ ] T017 [P] Contract test: a package with only `best_match` set is valid; a package with `safe_pick` set but `best_match=None` is rejected; a package where `best_match` and `safe_pick` share a `tmdb_id` is rejected, in `tests/contract/test_recommendation_package.py`
- [ ] T018 [P] Define `UserSessionState` in `src/streaming_discovery/contracts/session_state.py` per data-model.md (`raw_user_input`, `intake_answers`, `preference_profile`, `discovery_attempts` (max 2 entries), `recommendation_package`)
- [ ] T019 [P] Contract test: a fresh `UserSessionState` has all optional fields `None`/empty (blank stays unspecified, not defaulted — FR-003); a third `discovery_attempts` entry is rejected, in `tests/contract/test_session_state.py`

### Configuration

- [ ] T020 [P] Implement `Settings` (pydantic-settings) in `src/streaming_discovery/config.py`: `region: str = "US"` (FR-020), `llm_retry_max_attempts: int = 2` (FR-028), `demo_mode: bool = False`, all overridable by environment variable
- [ ] T021 [P] Contract test: default `Settings()` values match the spec above; `REGION=GB` environment variable overrides the default, in `tests/contract/test_config.py`

### TMDB adapter (ports + fakes)

- [ ] T022 [P] Define the `TmdbClient` `Protocol` (methods for discover/search, similar-title lookup, and detail fetch) in `src/streaming_discovery/tmdb/client.py`, shared by the real and fake implementations, per contracts/discovery-agent.md
- [ ] T023 [P] Implement the real `httpx`-based `TmdbClient` in `src/streaming_discovery/tmdb/client.py`: request timeout and bounded pagination/result limit enforced on every call (NFR-003)
- [ ] T024 [P] Implement `FakeTmdbClient` in `src/streaming_discovery/tmdb/fake_client.py`, reading recorded payloads from `tests/fixtures/tmdb/*.json` and supporting an injectable failure mode (timeout / HTTP error / malformed response) for adapter error tests (NFR-004)
- [ ] T025 [P] Implement `normalize.py` in `src/streaming_discovery/tmdb/normalize.py`: raw TMDB payload → `CandidateMedia`, resolving genre ids to names once (never carrying raw ids downstream), converting `release_date` to `release_year`, and scoping provider data to `Settings.region` and flatrate offers only (FR-019, FR-029)
- [ ] T026 [P] Adapter test: `normalize.py` output never contains a value corresponding to `popularity`, `vote_count`, raw genre ids, poster/backdrop paths, or a rent/buy provider offer, even when the input fixture contains them, in `tests/tmdb_adapter/test_normalize.py`
- [ ] T027 [P] Adapter test: `FakeTmdbClient` configured for timeout / HTTP error / malformed response yields a `CandidatePool` with `error` set and `candidates=[]` — never a crash, never a fabricated candidate, in `tests/tmdb_adapter/test_fake_client_errors.py` (FR-027)

### LLM provider (ports + fakes)

- [ ] T028 [P] Define the `ModelProvider` `Protocol` in `src/streaming_discovery/llm/provider.py`, used only by the Preference Agent and Recommendation Agent (NFR-008)
- [ ] T029 [P] Implement a bounded-retry wrapper around `ModelProvider` calls in `src/streaming_discovery/llm/provider.py`: on an outright call failure (not a schema-validation failure), retry up to `Settings.llm_retry_max_attempts` additional times, then raise a controlled, typed error (FR-028)
- [ ] T030 [P] Implement `FakeModelProvider` in `src/streaming_discovery/llm/fake_provider.py`: returns fixture-backed deterministic responses from `tests/fixtures/llm/`, with an injectable "fail N times then succeed" / "always fail" mode for retry testing
- [ ] T031 [P] Contract test: the bounded-retry wrapper succeeds when the underlying call fails fewer times than `llm_retry_max_attempts`, and raises the controlled error when it fails more times than that, in `tests/contract/test_llm_retry.py` (FR-028)

### Orchestrator skeleton

- [ ] T032 Implement the `Orchestrator`'s session lifecycle and single-attempt sequencing (create `UserSessionState`, invoke Preference Agent, validate its output against `PreferenceProfile`, invoke Discovery Agent, validate its output against `CandidatePool`) in `src/streaming_discovery/agents/orchestrator.py`, per contracts/orchestrator.md — retry logic itself is added in Phase 6 (US4)
- [ ] T033 Implement the preference confirmation step (render a `PreferenceProfile` summary; accept a correction that re-validates against `PreferenceProfile`) in `src/streaming_discovery/agents/orchestrator.py` (FR-006)
- [ ] T034 [P] Integration test: an agent output that fails its contract's validation is surfaced as a controlled failure by the Orchestrator, never silently coerced or passed downstream, in `tests/integration/test_contract_validation_boundary.py` (FR-022, NFR-002)

**Checkpoint**: Foundation ready — every user story phase below builds on T006–T034.

---

## Phase 3: User Story 1 - Specific Constraint Request (Priority: P1) 🎯 MVP

**Goal**: The full pipeline, single discovery attempt, exactly three distinct roles, no raw JSON — the outline's own "first implementation slice."

**Independent Test**: Submit "I have Netflix and Hulu. I want a movie after 2010 with a powerful female lead that is not a superhero movie." against a fixture pool with more than three qualifying titles; verify the `PreferenceProfile` hard/soft split, three distinct non-excluded-genre picks, and no raw JSON anywhere in the output.

### Tests for User Story 1 (write first; must fail before implementation)

- [ ] T035 [P] [US1] Contract test: the Preference Agent's output for the fixture specific-constraint request marks `media_type` and the excluded genre as hard, and the tone/recency signals as soft, in `tests/contract/test_preference_agent_us1.py` (spec.md US1 Acceptance Scenario 1)
- [ ] T036 [P] [US1] E2E test: the full pipeline for the specific-constraint request returns exactly three distinct titles assigned to Best Match/Safe Pick/Wildcard Pick, none in the excluded genre, with no raw TMDB JSON or raw inter-agent JSON in the rendered output, in `tests/e2e/test_specific_constraint_request.py`, using the quickstart.md scenario 1 fixture set (spec.md US1 Acceptance Scenarios 2–3)

### Implementation for User Story 1

- [ ] T037 [US1] Implement the `PreferenceAgent` (PydanticAI, using `ModelProvider`) mapping free text to `PreferenceProfile`, including hard/soft classification and `hard_override_fields` detection for user-designated non-negotiable fields, in `src/streaming_discovery/agents/preference_agent.py`, per contracts/preference-agent.md (depends on T008, T028–T030)
- [ ] T038 [US1] Implement the `DiscoveryAgent`'s single-attempt path — `PreferenceProfile` → `DiscoveryQuery` → `TmdbClient` → normalized `CandidatePool`, with exact-match `exclude_titles` filtering — in `src/streaming_discovery/agents/discovery_agent.py`, per contracts/discovery-agent.md (depends on T010, T022–T025)
- [ ] T039 [US1] Implement the `RecommendationAgent`: re-apply hard filters, score soft fit, assign roles in priority order, write a rationale per filled role, and exclude near-duplicates via the `vote_average` tie-break (spec.md Assumptions), in `src/streaming_discovery/agents/recommendation_agent.py`, per contracts/recommendation-agent.md (depends on T012, T016, T028–T030)
- [ ] T040 [US1] Wire the Orchestrator's single-attempt path end-to-end (Preference Agent → confirmation → Discovery Agent → Recommendation Agent → assembled `RecommendationPackage`) in `src/streaming_discovery/agents/orchestrator.py` (depends on T032, T037–T039)
- [ ] T041 [US1] Implement the minimal CLI entry point — read one free-text request, run the Orchestrator, render the `RecommendationPackage` (never raw JSON, per FR-021) — in `src/streaming_discovery/cli/output.py` and a runnable `__main__`/entry-point script (depends on T040)
- [ ] T042 [US1] Add structured logging of agent invocations, TMDB calls, and validation outcomes (NFR-006) in `src/streaming_discovery/agents/orchestrator.py`

**Checkpoint**: User Story 1 is fully functional and independently demoable — the MVP.

---

## Phase 4: User Story 2 - Vague Mood Request (Priority: P1)

**Goal**: Unspecified fields stay unspecified; weak subjective-trait evidence visibly lowers confidence.

**Independent Test**: Submit "Dark, moody, Eastern European vibes." against the quickstart.md scenario 2 fixtures; verify `media_type`/`providers` stay unset and at least one pick's rationale carries a `confidence_note`.

### Tests for User Story 2 (write first; must fail before implementation)

- [ ] T043 [P] [US2] E2E test: the vague-mood request leaves `PreferenceProfile.media_type` and `.providers` unset, still returns picks when the fixture pool supports it, and at least one pick's rationale reflects tone-based matching, in `tests/e2e/test_vague_mood_request.py`, using the quickstart.md scenario 2 fixtures (spec.md US2 Acceptance Scenarios 1–2)
- [ ] T044 [P] [US2] Unit test: given free text mentioning only tone/setting descriptors, the `PreferenceAgent` leaves every unmentioned field `None`/empty rather than defaulted, in `tests/unit/test_preference_agent_blank_fields.py` (FR-003)

### Implementation for User Story 2

- [ ] T045 [US2] Implement confidence-note logic in the `RecommendationAgent`: attach a `confidence_note` to a `Recommendation` when a stated tone/setting/theme descriptor has weak or absent support in the candidate's `overview`/`thematic_keywords`, in `src/streaming_discovery/agents/recommendation_agent.py` (FR-018) (depends on T039)
- [ ] T046 [P] [US2] Unit test: a candidate with strong tone-descriptor evidence in its overview/keywords gets no `confidence_note`; a candidate with weak/absent evidence does, in `tests/unit/test_confidence_scoring.py` (spec.md US2 Acceptance Scenario 3)

**Checkpoint**: User Stories 1 and 2 both independently functional.

---

## Phase 5: User Story 3 - Similarity-Based Request (Priority: P2)

**Goal**: Liked-titles-driven discovery via TMDB similarity lookups, distinct from generic genre search.

**Independent Test**: Submit "I loved Arrival, Ex Machina, and Severance. Give me something thoughtful but not extremely bleak." against the quickstart.md scenario 3 fixtures; verify `liked_titles` is captured distinctly and the candidate pool is sourced via similarity, not generic discovery.

### Tests for User Story 3 (write first; must fail before implementation)

- [ ] T047 [P] [US3] E2E test: `liked_titles` is recorded distinctly from genre/tone fields, the bleakness exclusion is soft (not hard), and the candidate pool traces to the similarity-lookup fixture rather than a generic-discover fixture, in `tests/e2e/test_similarity_request.py`, using the quickstart.md scenario 3 fixtures (spec.md US3 Acceptance Scenarios 1–2)
- [ ] T048 [P] [US3] Adapter test: `FakeTmdbClient`'s similarity-lookup path (title → id resolution, then similar-title results) returns the expected fixture set, in `tests/tmdb_adapter/test_similarity_lookup.py`

### Implementation for User Story 3

- [ ] T049 [US3] Implement similarity-seed resolution and the similar-title discovery path (`liked_titles` → `similarity_seed_titles` → TMDB similar/recommendations lookup, in place of a generic discover query) in `src/streaming_discovery/agents/discovery_agent.py` and `src/streaming_discovery/tmdb/client.py` (depends on T038)
- [ ] T050 [US3] Implement `disliked_titles` soft-penalty scoring in the `RecommendationAgent` (deprioritize candidates thematically similar to a disliked title) in `src/streaming_discovery/agents/recommendation_agent.py` (depends on T039)

**Checkpoint**: User Stories 1–3 independently functional.

---

## Phase 6: User Story 4 - Runtime-Constrained Request (Priority: P2)

**Goal**: The zero-result retry policy, end-to-end, with disclosure — the project's core orchestration demonstration.

**Independent Test**: quickstart.md scenarios 4 (retry succeeds) and 4b (retry also fails).

### Tests for User Story 4 (write first; must fail before implementation)

- [ ] T051 [P] [US4] E2E test: a comedy-with-runtime-ceiling request that returns zero candidates initially triggers exactly one retry with the runtime constraint relaxed (not the genre), and the final output discloses the relaxed constraint, in `tests/e2e/test_runtime_retry_success.py`, using the quickstart.md scenario 4 fixtures (spec.md US4 Acceptance Scenarios 1–2)
- [ ] T052 [P] [US4] E2E test: when the retried search also returns zero candidates, the session stops without a second retry and explains which constraints blocked a match, in `tests/e2e/test_runtime_retry_failure.py`, using the quickstart.md scenario 4b fixtures (spec.md US4 Acceptance Scenario 3)
- [ ] T053 [P] [US4] Unit test: the relaxation-priority helper picks the first eligible constraint in the fixed order (tone → runtime → year_range) present on the profile, and never returns `excluded_genres`, `media_type`, or any `hard_override_fields` entry as relaxable, in `tests/unit/test_relaxation_policy.py` (FR-011, FR-010)

### Implementation for User Story 4

- [ ] T054 [US4] Implement the Orchestrator's retry decision (`retry_number=0` result has zero candidates and no error → issue exactly one `retry_number=1` attempt with `relaxed_constraint` set; a second empty result → stop, no further retry) in `src/streaming_discovery/agents/orchestrator.py`, per contracts/orchestrator.md (depends on T032, T040)
- [ ] T055 [US4] Implement the relaxation-priority selection helper (first eligible soft constraint present on the profile, per FR-011's fixed order) in `src/streaming_discovery/agents/orchestrator.py`
- [ ] T056 [US4] Implement `relaxed_constraint` disclosure in the assembled `RecommendationPackage` and in CLI rendering in `src/streaming_discovery/agents/orchestrator.py` and `src/streaming_discovery/cli/output.py` (FR-013) (depends on T054)
- [ ] T057 [US4] Implement the `unresolved_notes` no-match explanation when the retry also yields zero candidates in `src/streaming_discovery/agents/orchestrator.py` (FR-012)

**Checkpoint**: User Stories 1–4 independently functional; the retry policy is fully demonstrated.

---

## Phase 7: User Story 5 - Exclusion-Based Request (Priority: P2)

**Goal**: An explicit sub-genre exclusion and a season-count cap both survive the retry unchanged.

**Independent Test**: quickstart.md scenario 5.

### Tests for User Story 5 (write first; must fail before implementation)

- [ ] T058 [P] [US5] E2E test: a mystery-series request excluding "police procedural" and capping season count at three keeps both constraints enforced in the initial search and, when an unrelated soft constraint triggers a retry, in the retried search too, in `tests/e2e/test_exclusion_request.py`, using the quickstart.md scenario 5 fixtures (spec.md US5 Acceptance Scenarios 1–2)
- [ ] T059 [P] [US5] Unit test: `excluded_genres` and `season_count_max` (once added to `hard_override_fields`) are byte-for-byte identical between the `retry_number=0` and `retry_number=1` `DiscoveryQuery`, in `tests/unit/test_hard_constraints_persist_across_retry.py` (FR-010)

### Implementation for User Story 5

- [ ] T060 [US5] Update the `PreferenceAgent` to detect a stated season-count cap and populate `PreferenceProfile.season_count_max`, always adding it to `hard_override_fields` (data-model.md: a stated season cap is never soft), in `src/streaming_discovery/agents/preference_agent.py` (depends on T037)
- [ ] T061 [US5] Implement the TV season-count hard filter in the `DiscoveryAgent`: since TMDB has no server-side season-count parameter, fetch season-count detail data over the raw pool (not finalist-only) when `season_count_max` is set, per the hard-filter exception documented in contracts/discovery-agent.md, in `src/streaming_discovery/agents/discovery_agent.py` (depends on T038)

**Checkpoint**: User Stories 1–5 independently functional.

---

## Phase 8: User Story 6 - Open/Guided Discovery Request (Priority: P3)

**Goal**: The guided-intake CLI flow, with blank answers staying unspecified and a correction step before discovery.

**Independent Test**: quickstart.md scenario 6.

### Tests for User Story 6 (write first; must fail before implementation)

- [ ] T062 [P] [US6] E2E test: a guided-intake session with format/mood answered and providers/exclusions skipped shows only the answered fields at confirmation, and a user correction at that step is reflected in the `PreferenceProfile` used for discovery, in `tests/e2e/test_guided_intake.py` (spec.md US6 Acceptance Scenarios 1–2)

### Implementation for User Story 6

- [ ] T063 [US6] Implement the guided-intake CLI prompts (format, services, mood/interests, exclusions, optional constraints — the six-step sequence in spec.md's Assumptions) in `src/streaming_discovery/cli/intake.py` (FR-002)
- [ ] T064 [US6] Wire guided-intake answers into the `PreferenceAgent` input alongside/instead of free text, and make the confirmation/correction step (T033) interactive over the terminal, in `src/streaming_discovery/cli/intake.py` and `src/streaming_discovery/agents/orchestrator.py` (depends on T033, T063)
- [ ] T065 [US6] Implement conflicting-input surfacing at the confirmation step (e.g., free text says "movie," guided intake says "TV") per spec.md Edge Cases, in `src/streaming_discovery/agents/orchestrator.py`

**Checkpoint**: All six user stories independently functional.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: The two controlled-failure paths, the adversarial suite, export, and the project's required artifacts (outline's Required Artifacts list).

- [ ] T066 [P] E2E test: a `FakeTmdbClient` failure on the first call ends the session with a controlled, user-visible error and no fabricated candidates, in `tests/e2e/test_tmdb_failure.py`, per quickstart.md scenario 7 (FR-027)
- [ ] T067 [P] E2E test: a `FakeModelProvider` configured to fail 1–2 times succeeds via the bounded retry; configured to fail 3 times, the session ends with a controlled error after the bound is exhausted, in `tests/e2e/test_llm_failure.py`, per quickstart.md scenario 8 (FR-028)
- [ ] T068 [P] Adversarial test suite covering conflicting constraints, unsupported vibe language, prompt injection in both user text and a TMDB overview fixture, duplicate/near-duplicate candidates, and malformed LLM output, in `tests/adversarial/test_adversarial_cases.py`, per the outline's Test Strategy table
- [ ] T069 [P] Implement optional session export to JSON and to Markdown in `src/streaming_discovery/cli/output.py` (FR-024)
- [ ] T070 [P] Run the full quickstart.md walkthrough (all 8 scenarios) as a documented, watchable demo session and record the transcript/output under `specs/001-streaming-discovery-assistant/` or `docs/`
- [ ] T071 [P] Write `README.md` covering setup, demo-mode usage (no credentials required), and an architecture overview
- [ ] T072 [P] Write `CLAUDE.md` with TDD rules, the four agent contract boundaries, and implementation guidance, referencing `.specify/memory/constitution.md`'s principles directly rather than restating them
- [ ] T073 [P] Add an architecture diagram and a sequence diagram (pipeline + retry path) under `docs/`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. Blocks every user story.
- **User Stories (Phases 3–8)**: All depend on Foundational completion.
  - US1 (Phase 3) has no dependency on any other story and is the MVP.
  - US2 (Phase 4) depends only on Foundational + US1's `RecommendationAgent` (T039) existing to extend.
  - US3 (Phase 5) depends only on Foundational + US1's `DiscoveryAgent`/`RecommendationAgent` (T038, T039) to extend.
  - US4 (Phase 6) depends only on Foundational + US1's Orchestrator single-attempt wiring (T040) to extend with retry logic.
  - US5 (Phase 7) depends on US4's retry mechanism (T054) being in place, since its acceptance test exercises hard-constraint persistence *across* a retry.
  - US6 (Phase 8) depends only on Foundational + US1's confirmation step (T033) to make interactive.
- **Polish (Phase 9)**: Depends on the user stories it tests (T066/T067 need Foundational's fakes only; T068 needs US1–US3 for the scenarios it adversarially targets; T069–T073 need US1 at minimum).

### Within Each User Story

Tests before implementation; contract/data-model fields before the agent logic that uses them; Discovery/Preference/Recommendation agent changes before Orchestrator wiring that calls them.

### Parallel Opportunities

- All `[P]`-marked Setup tasks (T003–T005) run in parallel.
- Within Foundational, the contract-definition/contract-test pairs (T006–T019), the config pair (T020–T021), the TMDB-adapter tasks (T022–T027), and the LLM-provider tasks (T028–T031) are each internally parallelizable — they touch disjoint files — but the Orchestrator skeleton (T032–T034) depends on the contracts existing first.
- Once Foundational is complete, US1 must go first (everything else extends it), but US2, US3, US4, and US6 can then proceed in parallel with each other (each extends a different piece of US1's output); US5 must wait for US4's retry mechanism.

---

## Parallel Example: Foundational Phase

```bash
# Contract models + their tests can be defined in parallel (disjoint files):
Task: "Define PreferenceProfile in src/streaming_discovery/contracts/preference_profile.py"
Task: "Define DiscoveryQuery in src/streaming_discovery/contracts/discovery_query.py"
Task: "Define CandidateMedia in src/streaming_discovery/contracts/candidate_media.py"
Task: "Define CandidatePool in src/streaming_discovery/contracts/candidate_pool.py"
Task: "Define RecommendationPackage in src/streaming_discovery/contracts/recommendation_package.py"

# TMDB and LLM port work can proceed in parallel with the contract work above:
Task: "Define TmdbClient Protocol in src/streaming_discovery/tmdb/client.py"
Task: "Define ModelProvider Protocol in src/streaming_discovery/llm/provider.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational) — Foundational is the larger investment here, since it carries all six contracts and both adapter ports.
2. Complete Phase 3 (User Story 1).
3. **STOP and VALIDATE**: run `tests/e2e/test_specific_constraint_request.py` and the quickstart.md scenario 1 walkthrough independently.
4. This is the outline's own "first implementation slice" — demo-ready before any retry, similarity, or guided-intake logic exists.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → validate independently → MVP demo.
3. US2, US3, US4, US6 → each validated independently → can proceed in any order (or in parallel) once US1 lands, since each extends a different part of US1 without touching the others' code paths.
4. US5 → validated independently → requires US4's retry mechanism first.
5. Phase 9 (Polish) → the two controlled-failure demos, the adversarial suite, export, and the project's required documentation/diagram artifacts.

### Constitutional check on this ordering

Principle I is satisfied because every implementation task has a preceding, currently-failing test task. Principle II is satisfied because T032–T034 and T054–T057 (Orchestrator) and T038/T049/T061 (Discovery Agent) contain no `ModelProvider` dependency — only T037/T060 (Preference Agent) and T039/T045/T050 (Recommendation Agent) do. Principle VI is satisfied because no task here introduces an agent, contract, or field beyond what spec.md's Domain Model Minimization Rationale already justified, plus the one field (`season_count_max`/`season_count`) whose gap was caught and justified in data-model.md before this task list was written.
