---

description: "Task list template for feature implementation"
---

# Tasks: Multi-Agent Streaming Discovery Assistant (MVP)

**Input**: Design documents from `/specs/001-streaming-discovery-assistant/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md, `.specify/memory/constitution.md`

**Tests**: Included and mandatory, not optional. Constitution Principle I (Spec-Driven and Test-First Development, NON-NEGOTIABLE) requires a failing test before any production code for every capability. Every implementation task below has at least one test task ordered before it — this list was re-audited by `/speckit-analyze` and remediated to close every case where that wasn't yet true (see the `001-streaming-discovery-assistant` process log for the audit).

**Organization**: Tasks are grouped by user story (spec.md priorities P1–P3) to enable independent implementation and testing of each story, per Constitution Principle VI (no capability built ahead of the requirement that justifies it).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6, matching spec.md)
- Every task names its exact file path

## Path Conventions

Single project, per plan.md's Structure Decision: `src/streaming_discovery/`, `tests/` at repository root. `.env` (git-ignored) and `.env.example` (tracked) already exist at the repository root.

---

## Phase 1: Setup

**Purpose**: Project initialization — no story-specific code yet.

- [x] T001 Create the `src/streaming_discovery/` package (with `contracts/`, `agents/`, `tmdb/`, `llm/`, `cli/` subpackages, each with `__init__.py`) and the `tests/` tree (`unit/`, `contract/`, `tmdb_adapter/`, `integration/`, `e2e/`, `adversarial/`, `fixtures/`), matching plan.md's Project Structure exactly
- [x] T002 Initialize the Python project in `pyproject.toml`: Python 3.11+ requirement, dependencies `pydantic-ai`, `pydantic>=2`, `pydantic-settings`, `httpx`, dev dependencies `pytest`, `pytest-asyncio`, per research.md §1–4. `pydantic-settings` reads `.env` via its built-in dotenv support — no separate `python-dotenv` dependency needed. `.env` and `.env.example` already exist at the repository root and are not touched by this task. Managed with `uv` (`uv add` / `uv add --dev`); `.python-version` (3.11) and `uv.lock` are committed for reproducibility.
- [x] T003 [P] Configure `ruff` (lint + format) in `pyproject.toml`
- [x] T004 [P] Configure `pytest` in `pyproject.toml` (asyncio mode, `tests/` rootdir, markers for `contract`, `unit`, `integration`, `e2e`, `adversarial`)
- [x] T005 [P] Add `tests/fixtures/README.md` documenting fixture provenance (recorded TMDB payloads; no live network calls in any automated test, per NFR-004) and the directory layout (`tests/fixtures/tmdb/`, `tests/fixtures/llm/`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The six core contracts (data-model.md), the TMDB and LLM ports with their fixture-backed fakes, configuration, and the Orchestrator's single-attempt skeleton — everything every user story depends on. No user story may begin before this phase is complete.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

### Shared enums and contracts (data-model.md)

- [x] T006 [P] Define `MediaType` (`movie`/`tv`/`either`), `RelaxableConstraint` (`tone`/`runtime`/`year_range`), and `RecommendationRole` (`best_match`/`safe_pick`/`wildcard_pick`) enums in `src/streaming_discovery/contracts/enums.py`, per data-model.md "Shared enums"
- [x] T007 [P] Contract test for the three enums (valid values only; invalid string rejected) in `tests/contract/test_enums.py`
- [x] T008 [P] Define `PreferenceProfile` in `src/streaming_discovery/contracts/preference_profile.py` with every field from data-model.md's PreferenceProfile table (including `season_count_max` and `hard_override_fields`), enforcing: at least one of `media_type, providers, genres, tone_descriptors, setting_descriptors, theme_descriptors, liked_titles` must be non-empty/non-null, and `year_min <= year_max` when both are set
- [x] T009 [P] Contract test: valid `PreferenceProfile` payloads accepted; an entirely-empty profile rejected; `year_min > year_max` rejected, in `tests/contract/test_preference_profile.py`
- [x] T010 [P] Define `DiscoveryQuery` in `src/streaming_discovery/contracts/discovery_query.py` with every field from data-model.md's DiscoveryQuery table (including `season_count_max`), enforcing: `retry_number` is `0` or `1`; `relaxed_constraint` is `None` when `retry_number == 0` and set when `retry_number == 1`
- [x] T011 [P] Contract test: valid `DiscoveryQuery` payloads for both `retry_number` values; a `retry_number=0` payload with a non-`None` `relaxed_constraint` rejected; a `retry_number=1` payload with `relaxed_constraint=None` rejected, in `tests/contract/test_discovery_query.py`
- [x] T012 [P] Define `CandidateMedia` in `src/streaming_discovery/contracts/candidate_media.py` with exactly the fields in data-model.md's CandidateMedia table (including `season_count`, excluding every field in spec.md's "fields considered and explicitly excluded" table), enforcing `vote_average` in the closed range `[0.0, 10.0]`
- [x] T013 [P] Contract test: valid `CandidateMedia` payload accepted; `vote_average` of `-1` or `10.1` rejected; confirm the model has no `genre_ids`, `popularity`, `vote_count`, `poster_path`, or `backdrop_path` field, in `tests/contract/test_candidate_media.py`
- [x] T014 [P] Define `CandidatePool` in `src/streaming_discovery/contracts/candidate_pool.py` with exactly `candidates`, `relaxed_constraint`, `retry_number`, `error` (no `total_results`, no `retry_required`, per spec.md's Domain Model Minimization Rationale). Also define the nested `TmdbErrorInfo` type in the same file: `{ kind: Literal["timeout", "http_error", "malformed_response"], detail: str }`, per data-model.md's `TmdbErrorInfo` definition
- [x] T015 [P] Contract test: an empty `candidates` list with `error=None` is valid (a legitimate zero-result pool); a `CandidatePool` with `error` set requires a valid `TmdbErrorInfo.kind`; confirm the model has no `total_results`/`retry_required` field, in `tests/contract/test_candidate_pool.py`
- [x] T016 [P] Define `Recommendation` (nested: `role`, `candidate`, `rationale`, `confidence_note`) and `RecommendationPackage` (`best_match`, `safe_pick`, `wildcard_pick`, `applied_constraints`, `relaxed_constraint` (singular), `unresolved_notes`) in `src/streaming_discovery/contracts/recommendation_package.py`, enforcing role contiguity (`safe_pick` requires `best_match` set; `wildcard_pick` requires `safe_pick` set) and no two filled roles sharing a `tmdb_id`
- [x] T017 [P] Contract test: a package with only `best_match` set is valid (the partial-fill case — FR-015/SC-008); a package with `safe_pick` set but `best_match=None` is rejected; a package where `best_match` and `safe_pick` share a `tmdb_id` is rejected, in `tests/contract/test_recommendation_package.py`
- [x] T018 [P] Define `UserSessionState` in `src/streaming_discovery/contracts/session_state.py` per data-model.md (`raw_user_input`, `intake_answers`, `preference_profile`, `discovery_attempts` (max 2 entries), `recommendation_package`)
- [x] T019 [P] Contract test: a fresh `UserSessionState` has all optional fields `None`/empty (blank stays unspecified, not defaulted — FR-003); a third `discovery_attempts` entry is rejected, in `tests/contract/test_session_state.py`

### Configuration

- [x] T020 [P] Implement `Settings` (pydantic-settings, `env_file=".env"`) in `src/streaming_discovery/config.py`, matching `.env.example`'s declared variables: `tmdb_api_token: str` (from `TMDB_API_TOKEN`), `openrouter_api_key: str` (from `OPENROUTER_API_KEY`), `model_name: str` (from `MODEL_NAME`), `region: str = "US"` (from `REGION`, FR-020), plus two fields with no `.env.example` entry yet: `llm_retry_max_attempts: int = 2` (FR-028) and `demo_mode: bool = False`
- [x] T021 [P] Contract test: default `Settings()` values match the spec above; `REGION=GB` environment variable overrides the default; every variable declared in `.env.example` maps to a `Settings` field, in `tests/contract/test_config.py`

### TMDB adapter (ports + fakes)

- [x] T022 [P] Define the `TmdbClient` `Protocol` (methods for discover/search, similar-title lookup, and detail fetch, each accepting a `result_limit`) in `src/streaming_discovery/tmdb/client.py`, shared by the real and fake implementations, per contracts/discovery-agent.md
- [x] T023 [P] Unit test: given a fixture response spanning more pages/items than `result_limit`, the `TmdbClient` implementation stops paginating/collecting at the bound and never returns more than `result_limit` items, in `tests/tmdb_adapter/test_pagination_bound.py` (NFR-003) — write this first; it must fail before T024 exists
- [x] T024 [P] Implement the real `httpx`-based `TmdbClient` in `src/streaming_discovery/tmdb/client.py`: request timeout and the bounded pagination/result limit from T023 enforced on every call (NFR-003). Also defines `TmdbAdapterError`, a uniform error type both the real and fake clients raise on failure, carrying the `TmdbErrorInfo` a `CandidatePool.error` field expects.
- [x] T025 [P] Adapter test: `FakeTmdbClient` configured for timeout / HTTP error / malformed response raises `TmdbAdapterError` with a well-formed `TmdbErrorInfo` (never a crash, never a fabricated candidate), and that error wraps cleanly into a valid `CandidatePool(candidates=[], error=...)`, in `tests/tmdb_adapter/test_fake_client_errors.py` (FR-027) — write this first; it must fail before T026 exists. *(Reordered before its implementation task during Foundational implementation — see the process log: this and T026-T028 were originally sequenced implementation-before-test, the same latent slip caught and fixed for User Story 2 during `/speckit-analyze`.)*
- [x] T026 [P] Implement `FakeTmdbClient` in `src/streaming_discovery/tmdb/fake_client.py` (satisfying T025), reading recorded payloads from `tests/fixtures/tmdb/*.json`, honoring the same `result_limit` contract as the real client, and supporting the injectable failure mode and a call-count instrumentation hook (for later finalist-only-fetch verification) for adapter and integration tests (NFR-004)
- [x] T027 [P] Adapter test: `normalize.py` output never contains a value corresponding to `popularity`, `vote_count`, raw genre ids, poster/backdrop paths, or a rent/buy provider offer, even when the input fixture contains them, and correctly scopes provider data to one region + flatrate only, in `tests/tmdb_adapter/test_normalize.py` — write this first; it must fail before T028 exists
- [x] T028 [P] Implement `normalize.py` in `src/streaming_discovery/tmdb/normalize.py` (satisfying T027): raw TMDB payload → `CandidateMedia`, resolving genre ids to names once via TMDB's static genre list (never carrying raw ids downstream), converting `release_date`/`first_air_date` to `release_year`, and scoping provider data to `Settings.region` and flatrate offers only (FR-019, FR-029)

### LLM provider (ports + fakes)

- [x] T029 [P] Define the `ModelProvider` `Protocol` and the `ModelCallError` exception in `src/streaming_discovery/llm/provider.py`, used only by the Preference Agent and Recommendation Agent (NFR-008)
- [x] T030 [P] Contract test: a bounded-retry wrapper around `ModelProvider` calls succeeds when the underlying call fails fewer times than `llm_retry_max_attempts`, raises the controlled error when it fails more times than that, and never retries a non-`ModelCallError` failure (e.g. schema-invalid output), in `tests/contract/test_llm_retry.py` (FR-028) — write this first; it must fail before T031/T032 exist. *(Reordered before its implementation tasks — see the T025 note above; same latent slip.)*
- [x] T031 [P] Implement the bounded-retry wrapper (`generate_with_retry`, satisfying T030) around `ModelProvider` calls in `src/streaming_discovery/llm/provider.py`: on an outright call failure (not a schema-validation failure), retry up to `Settings.llm_retry_max_attempts` additional times, then raise a controlled, typed error (FR-028)
- [x] T032 [P] Implement `FakeModelProvider` (satisfying T030) in `src/streaming_discovery/llm/fake_provider.py`: returns fixture-backed deterministic responses, with an injectable "fail N times then succeed" / "always fail" mode for retry testing

### Orchestrator skeleton

- [x] T033 Implement the `Orchestrator`'s session lifecycle and single-attempt sequencing (create `UserSessionState`, invoke Preference Agent, validate its output against `PreferenceProfile`, invoke Discovery Agent, validate its output against `CandidatePool`) in `src/streaming_discovery/agents/orchestrator.py`, per contracts/orchestrator.md — retry logic itself is added in Phase 6 (US4). Also defines `ContractValidationError`/`validate_handoff`, the shared controlled-failure mechanism used at every agent boundary (FR-022, NFR-002).
- [x] T034 Implement the preference confirmation step as a logic-layer function (`build_confirmation_summary`, `apply_correction`; given a `PreferenceProfile`, produce a renderable summary and accept/re-validate a correction) in `src/streaming_discovery/agents/orchestrator.py` (FR-006), with a preceding unit test in `tests/unit/test_confirmation.py` (added during implementation so this logic wasn't left untested until User Story 1's CLI exists — the same reasoning as the T069/export gap caught during `/speckit-analyze`). This is deliberately terminal-agnostic here — User Story 1 (T045) is what wires it to actual terminal I/O for every request path, not only guided intake; see the Dependencies section note on FR-006 scope.
- [x] T035 [P] Integration test: an agent output that fails its contract's validation is surfaced as a controlled failure by the Orchestrator, never silently coerced or passed downstream, in `tests/integration/test_contract_validation_boundary.py` (FR-022, NFR-002)

**Checkpoint**: Foundation ready — every user story phase below builds on T006–T035. Verified: 64 tests passing, `ruff check`/`ruff format --check` clean.

---

## Phase 3: User Story 1 - Specific Constraint Request (Priority: P1) 🎯 MVP

**Goal**: The full pipeline, single discovery attempt, exactly three distinct roles (or fewer, when fewer genuinely qualify), no raw JSON, and an interactive confirmation step — the outline's own "first implementation slice," now scoped to fully satisfy FR-006 and FR-015/SC-008 on its own rather than deferring either to a later story.

**Independent Test**: Submit "I have Netflix and Hulu. I want a movie after 2010 with a powerful female lead that is not a superhero movie." against a fixture pool with more than three qualifying titles; verify the `PreferenceProfile` hard/soft split, three distinct non-excluded-genre picks, a confirmation step the user can correct, and no raw JSON anywhere in the output.

### Tests for User Story 1 (write first; must fail before implementation)

- [x] T036 [P] [US1] Contract test: the Preference Agent's output for the fixture specific-constraint request marks `media_type` and the excluded genre as hard, and the tone/recency signals as soft, in `tests/contract/test_preference_agent_us1.py` (spec.md US1 Acceptance Scenario 1)
- [x] T037 [P] [US1] E2E test: the full pipeline for the specific-constraint request returns exactly three distinct titles assigned to Best Match/Safe Pick/Wildcard Pick, none in the excluded genre, with no raw TMDB JSON or raw inter-agent JSON in the rendered output, in `tests/e2e/test_specific_constraint_request.py`, using the quickstart.md scenario 1 fixture set (spec.md US1 Acceptance Scenarios 2–3)
- [x] T038 [P] [US1] E2E test: given a fixture pool with exactly 1 qualifying candidate, only `best_match` is populated in the final output; given exactly 2, `best_match` and `safe_pick` are populated and `wildcard_pick` is `None`; in neither case is any constraint broadened or a candidate reused across roles, in `tests/e2e/test_partial_fill.py`, using the quickstart.md scenario 1b fixtures (FR-015, SC-008, resolved Clarification Q1)
- [x] T039 [P] [US1] Integration test: for a free-text request (no guided intake involved), the CLI renders the `PreferenceProfile` confirmation summary and accepts a terminal correction before Discovery is invoked, and that correction is reflected in the profile actually used, in `tests/integration/test_confirmation_free_text.py` (FR-006)
- [x] T040 [P] [US1] Integration test: using `FakeTmdbClient`'s call-count instrumentation (T026), the Discovery Agent's detail-level fetch (runtime for TV, provider list, thematic keywords) is called exactly once per finalist candidate reaching ranking, and zero times for candidates eliminated by hard filtering, for a fixture raw pool larger than the finalist set, in `tests/integration/test_finalist_only_enrichment.py` (FR-029)

### Implementation for User Story 1

- [x] T041 [US1] Implement the `PreferenceAgent` (PydanticAI, using `ModelProvider`) mapping free text to `PreferenceProfile`, including hard/soft classification and `hard_override_fields` detection for user-designated non-negotiable fields, in `src/streaming_discovery/agents/preference_agent.py`, per contracts/preference-agent.md (depends on T008, T029, T031)
- [x] T042 [US1] Implement the `DiscoveryAgent`'s single-attempt path — `PreferenceProfile` → `DiscoveryQuery` → `TmdbClient` → normalized `CandidatePool`, with exact-match `exclude_titles` filtering and finalist-only detail enrichment (satisfying T040) — in `src/streaming_discovery/agents/discovery_agent.py`, per contracts/discovery-agent.md (depends on T010, T022–T028)
- [x] T043 [US1] Implement the `RecommendationAgent`: re-apply hard filters, score soft fit, assign roles in priority order — filling only as many roles as distinct qualifying candidates support, per FR-015 (satisfying T038) — write a rationale per filled role, and exclude near-duplicates via the `vote_average` tie-break (spec.md Assumptions), in `src/streaming_discovery/agents/recommendation_agent.py`, per contracts/recommendation-agent.md (depends on T012, T016, T029, T031). All soft-fit scoring, ranking, dedup, and the weak-evidence decision are deterministic code (constitution Principle II); the LLM writes only the rationale wording, with its own unit tests in `tests/unit/test_recommendation_scoring.py` (added during implementation, beyond this task's original scope).
- [x] T044 [US1] Wire the Orchestrator's single-attempt path end-to-end (Preference Agent → confirmation → Discovery Agent → Recommendation Agent → assembled `RecommendationPackage`) in `src/streaming_discovery/agents/orchestrator.py` (depends on T033, T041–T043). Also adds `build_discovery_queries`/`run_discovery_attempt`, which resolve an unspecified/`either` format into one query per media type and merge the results (data-model.md's "one query per attempt, or a merged strategy").
- [x] T045 [US1] Implement the CLI entry point — read one free-text request, render the T034 confirmation summary and accept a terminal correction (satisfying T039 and FR-006 for every request path, not only guided intake), run the Orchestrator, render the `RecommendationPackage` (never raw JSON, per FR-021) — in `src/streaming_discovery/cli/output.py` and a runnable `__main__`/entry-point script (depends on T034, T044). The production `ModelProvider` (a PydanticAI `Agent` pointed at OpenRouter) is built here too, verified against the installed `pydantic-ai` version's actual API rather than assumed.
- [x] T046 [P] [US1] Unit test: a structured log record is emitted for each agent invocation, each TMDB call, and each contract-validation outcome, in `tests/unit/test_orchestrator_logging.py` (NFR-006) — write this first; it must fail before T047
- [x] T047 [US1] Add structured logging of agent invocations, TMDB calls, and validation outcomes (satisfying T046, NFR-006) in `src/streaming_discovery/agents/orchestrator.py`

**Verified**: 82 tests passing, `ruff check`/`ruff format --check` clean.

**Checkpoint**: User Story 1 is fully functional and independently demoable — the MVP, including the partial-fill guarantee and an interactive confirmation step.

---

## Phase 4: User Story 2 - Vague Mood Request (Priority: P1)

**Goal**: Unspecified fields stay unspecified; weak subjective-trait evidence visibly lowers confidence.

**Independent Test**: Submit "Dark, moody, Eastern European vibes." against the quickstart.md scenario 2 fixtures; verify `media_type`/`providers` stay unset and at least one pick's rationale carries a `confidence_note`.

### Tests for User Story 2 (write first; must fail before implementation)

- [x] T048 [P] [US2] E2E test: the vague-mood request leaves `PreferenceProfile.media_type` and `.providers` unset, still returns picks when the fixture pool supports it, and at least one pick's rationale reflects tone-based matching, in `tests/e2e/test_vague_mood_request.py`, using the quickstart.md scenario 2 fixtures (spec.md US2 Acceptance Scenarios 1–2)
- [x] T049 [P] [US2] Unit test: given free text mentioning only tone/setting descriptors, the `PreferenceAgent` leaves every unmentioned field `None`/empty rather than defaulted, in `tests/unit/test_preference_agent_blank_fields.py` (FR-003)
- [x] T050 [P] [US2] Unit test: a candidate with strong tone-descriptor evidence in its overview/keywords gets no `confidence_note`; a candidate with weak/absent evidence does, in `tests/unit/test_confidence_scoring.py` (spec.md US2 Acceptance Scenario 3) — **already satisfied**: written as `tests/unit/test_recommendation_scoring.py::TestWeakToneEvidence` during User Story 1's implementation, since the confidence-note mechanism was natural to build alongside the rest of `RecommendationAgent`'s scoring logic rather than split across two stories

### Implementation for User Story 2

- [x] T051 [US2] Implement confidence-note logic in the `RecommendationAgent`: attach a `confidence_note` to a `Recommendation` when a stated tone/setting/theme descriptor has weak or absent support in the candidate's `overview`/`thematic_keywords`, satisfying T050, in `src/streaming_discovery/agents/recommendation_agent.py` (FR-018) (depends on T043) — **already implemented** in T043 during User Story 1 (`_has_weak_tone_evidence` wired into `RecommendationAgent.run`); T048/T049 above are the only genuinely new tests this phase needed

**Checkpoint**: User Stories 1 and 2 both independently functional. Verified: 84 tests passing, `ruff check`/`ruff format --check` clean.

---

## Phase 5: User Story 3 - Similarity-Based Request (Priority: P2)

**Goal**: Liked-titles-driven discovery via TMDB similarity lookups, distinct from generic genre search.

**Independent Test**: Submit "I loved Arrival, Ex Machina, and Severance. Give me something thoughtful but not extremely bleak." against the quickstart.md scenario 3 fixtures; verify `liked_titles` is captured distinctly and the candidate pool is sourced via similarity, not generic discovery.

### Tests for User Story 3 (write first; must fail before implementation)

- [x] T052 [P] [US3] E2E test: `liked_titles` is recorded distinctly from genre/tone fields, the bleakness exclusion is soft (not hard), and the candidate pool traces to the similarity-lookup fixture rather than a generic-discover fixture, in `tests/e2e/test_similarity_request.py`, using the quickstart.md scenario 3 fixtures (spec.md US3 Acceptance Scenarios 1–2)
- [x] T053 [P] [US3] Adapter test: `FakeTmdbClient`'s similarity-lookup path (title → id resolution, then similar-title results) returns the expected fixture set, in `tests/tmdb_adapter/test_similarity_lookup.py` — **already satisfied** by `search_title`/`similar` built in Foundational (T026); this test just confirms it

### Implementation for User Story 3

- [x] T054 [US3] Implement similarity-seed resolution and the similar-title discovery path (`liked_titles` → `similarity_seed_titles` → TMDB similar/recommendations lookup, in place of a generic discover query) in `src/streaming_discovery/agents/discovery_agent.py` and `src/streaming_discovery/tmdb/client.py` (depends on T042)
- [x] T055 [US3] Implement `disliked_titles` soft-penalty scoring in the `RecommendationAgent` (deprioritize candidates thematically similar to a disliked title) in `src/streaming_discovery/agents/recommendation_agent.py` (depends on T043). Since the Recommendation Agent cannot call TMDB to learn a disliked title's own genres, "thematic similarity" uses the same overview/keyword text-overlap heuristic already used for tone-descriptor matching (deliberately weaker than the exact-title-match penalty, which is a safety net for a case Discovery already hard-excludes) — a documented design decision, not a deferred one; unit-tested in `tests/unit/test_recommendation_scoring.py`.

**Checkpoint**: User Stories 1–3 independently functional. Verified: 88 tests passing, `ruff check`/`ruff format --check` clean.

---

## Phase 6: User Story 4 - Runtime-Constrained Request (Priority: P2)

**Goal**: The zero-result retry policy, end-to-end, with disclosure — the project's core orchestration demonstration.

**Independent Test**: quickstart.md scenarios 4 (retry succeeds) and 4b (retry also fails).

### Tests for User Story 4 (write first; must fail before implementation)

- [x] T056 [P] [US4] E2E test: a comedy-with-runtime-ceiling request that returns zero candidates initially triggers exactly one retry with the runtime constraint relaxed (not the genre), and the final output discloses the relaxed constraint, in `tests/e2e/test_runtime_retry_success.py`, using the quickstart.md scenario 4 fixtures (spec.md US4 Acceptance Scenarios 1–2)
- [x] T057 [P] [US4] E2E test: when the retried search also returns zero candidates, the session stops without a second retry and explains which constraints blocked a match, in `tests/e2e/test_runtime_retry_failure.py`, using the quickstart.md scenario 4b fixtures (spec.md US4 Acceptance Scenario 3)
- [x] T058 [P] [US4] Unit test: the relaxation-priority helper picks the first eligible constraint in the fixed order (tone → runtime → year_range) present on the profile, and never returns `excluded_genres`, `media_type`, or any `hard_override_fields` entry as relaxable, in `tests/unit/test_relaxation_policy.py` (FR-011, FR-010)

### Implementation for User Story 4

- [x] T059 [US4] Implement the Orchestrator's retry decision (`retry_number=0` result has zero candidates and no error → issue exactly one `retry_number=1` attempt with `relaxed_constraint` set; a second empty result → stop, no further retry) in `src/streaming_discovery/agents/orchestrator.py`, per contracts/orchestrator.md (depends on T033, T044). `FakeTmdbClient` gained a `discover_sequence` option (call-count-sensitive responses) to make the zero-then-nonzero retry scenario testable — a test-infrastructure addition, not a new requirement.
- [x] T060 [US4] Implement the relaxation-priority selection helper (`select_relaxation_constraint`, first eligible soft constraint present on the profile, per FR-011's fixed order) in `src/streaming_discovery/agents/orchestrator.py`
- [x] T061 [US4] Implement `relaxed_constraint` disclosure in the assembled `RecommendationPackage` and in CLI rendering in `src/streaming_discovery/agents/orchestrator.py` and `src/streaming_discovery/cli/output.py` (FR-013) (depends on T059) — **CLI rendering already implemented** in `render_package` during User Story 1; only the Orchestrator-side wiring (setting `relaxed_constraint` on the package via the retried pool) was new here.
- [x] T062 [US4] Implement the `unresolved_notes` no-match explanation when the retry also yields zero candidates in `src/streaming_discovery/agents/orchestrator.py` (FR-012), naming the still-applied constraints via `_describe_blocking_constraints`

**Checkpoint**: User Stories 1–4 independently functional; the retry policy is fully demonstrated. Verified: 97 tests passing, `ruff check`/`ruff format --check` clean.

---

## Phase 7: User Story 5 - Exclusion-Based Request (Priority: P2)

**Goal**: An explicit sub-genre exclusion and a season-count cap both survive the retry unchanged.

**Independent Test**: quickstart.md scenario 5.

### Tests for User Story 5 (write first; must fail before implementation)

- [x] T063 [P] [US5] E2E test: a mystery-series request excluding a sub-genre and capping season count at three keeps both constraints enforced in the initial search and, when an unrelated soft constraint triggers a retry, in the retried search too, in `tests/e2e/test_exclusion_request.py`, using the quickstart.md scenario 5 fixtures (spec.md US5 Acceptance Scenarios 1–2). Uses "Crime" rather than the outline's "police procedural" as the excluded genre — TMDB has no official "police procedural" genre, so excluding it would never match any candidate's real TMDB genre and the exclusion assertion would be vacuous.
- [x] T064 [P] [US5] Unit test: `excluded_genres` and `season_count_max` (once added to `hard_override_fields`) are byte-for-byte identical between the `retry_number=0` and `retry_number=1` `DiscoveryQuery`, in `tests/unit/test_hard_constraints_persist_across_retry.py` (FR-010) — **already satisfied**: `build_discovery_queries` never touched these fields based on `relaxed_constraint`, confirming the design was correct from User Story 4

### Implementation for User Story 5

- [x] T065 [US5] Update the `PreferenceAgent` to detect a stated season-count cap and populate `PreferenceProfile.season_count_max`, always adding it to `hard_override_fields` (data-model.md: a stated season cap is never soft), in `src/streaming_discovery/agents/preference_agent.py` (depends on T041) — **already implemented** in T041's `SYSTEM_PROMPT` during User Story 1; added `tests/unit/test_preference_agent_season_count.py` to confirm it, since it had no dedicated test until now
- [x] T066 [US5] Implement the TV season-count hard filter in the `DiscoveryAgent`: since TMDB has no server-side season-count parameter, fetch season-count detail data over the raw pool (not finalist-only) when `season_count_max` is set, per the hard-filter exception documented in contracts/discovery-agent.md, in `src/streaming_discovery/agents/discovery_agent.py` (depends on T042). No extra fetch was actually needed: every hard-filter survivor already gets a `details()` call for runtime/provider/keyword enrichment, which already includes `number_of_seasons` — this task just added the post-detail comparison against `season_count_max`.

**Checkpoint**: User Stories 1–5 independently functional. Verified: 100 tests passing, `ruff check`/`ruff format --check` clean.

---

## Phase 8: User Story 6 - Open/Guided Discovery Request (Priority: P3)

**Goal**: The guided-intake CLI flow, with blank answers staying unspecified, feeding into the same confirmation/correction step User Story 1 already made interactive.

**Independent Test**: quickstart.md scenario 6.

### Tests for User Story 6 (write first; must fail before implementation)

- [x] T067 [P] [US6] E2E test: a guided-intake session with format/mood answered and providers/exclusions skipped shows only the answered fields at confirmation, and a user correction at that step is reflected in the `PreferenceProfile` used for discovery, in `tests/e2e/test_guided_intake.py` (spec.md US6 Acceptance Scenarios 1–2)

### Implementation for User Story 6

- [x] T068 [US6] Implement the guided-intake CLI prompts (format, services, mood/interests, exclusions, optional constraints — the five-question sequence in spec.md's Assumptions; step 6, confirmation, reuses `default_confirm`) in `src/streaming_discovery/cli/intake.py` (FR-002)
- [x] T069 [US6] Wire guided-intake answers into the `PreferenceAgent` input alongside/instead of free text, reusing the confirmation/correction step T045 already made interactive (no new interactivity to build here — only the guided-intake-specific prompts feeding into it), in `src/streaming_discovery/cli/intake.py` (depends on T045, T068). `run_guided_cli` unifies an optional leading free-text prompt with the five guided questions in one flow (rather than two separate, mutually-exclusive entry points), since a free-text/intake conflict (T070) can't arise if the two paths never coexist in the same session.
- [x] T070 [US6] Implement conflicting-input surfacing at the confirmation step (e.g., free text says "movie," guided intake says "TV") per spec.md Edge Cases, in `src/streaming_discovery/cli/intake.py` (`_detect_format_conflict`, unit-tested directly in `tests/unit/test_intake_conflict_detection.py`) — a narrow, literal check for the specific case the spec names, not a general-purpose contradiction detector, printed before the user reaches confirmation so they can resolve it there.

**Checkpoint**: All six user stories independently functional. Verified: 106 tests passing, `ruff check`/`ruff format --check` clean.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: The two controlled-failure paths, the adversarial suite, export, and the project's required artifacts (outline's Required Artifacts list).

**Pre-Polish additions** (requested by the user during the Phase 8 checkpoint, before Polish began):

- [x] T071 Unit test + fix: relaxing `RelaxableConstraint.TONE` was a no-op (tone/setting/theme descriptors never reach `DiscoveryQuery`, so nothing about the retried query actually changed — a real bug found while reviewing the implementation, not exercised by any US4/US5 test since those all used `RUNTIME`/`YEAR_RANGE` relaxation). Fixed in `build_discovery_queries` (`src/streaming_discovery/agents/orchestrator.py`): relaxing `TONE` now drops `included_genres` for that attempt — the closest `DiscoveryQuery`-visible proxy for "vibe precision" — never touching `excluded_genres` (FR-010). Tests added to `tests/unit/test_relaxation_policy.py`, written before the fix.
- [x] T072 Add a clean, user-friendly terminal UI (`rich`), requested by the user — revisits research.md §7's original "no formatting library for MVP" call now that a presentation-quality requirement actually exists. New `src/streaming_discovery/cli/rich_ui.py` (`print_welcome_banner`, `print_confirmation_summary`, `print_recommendation_package`) styles the *same* content the existing plain-text `build_confirmation_summary`/`render_package` already produce and test, rather than duplicating those decisions; `cli/intake.run_guided_cli` gained an optional `console` parameter that switches to the styled rendering (plus a status spinner during the pipeline run) while leaving the plain-text default — and every test that doesn't pass a console — unchanged. Also unifies the entry point: `main()` moved to `cli/intake.py` (the more complete flow) to avoid a circular import with `cli/output.py`, and `pyproject.toml` gained a `[project.scripts]` entry (`streaming-discovery`) so the app is runnable as `uv run streaming-discovery` instead of `python -m streaming_discovery.cli.output`. Tests: `tests/unit/test_rich_ui.py`, `tests/integration/test_guided_cli_rich_console.py`.

**Originally planned Polish tasks** (renumbered to follow the two additions above):

- [x] T073 [P] E2E test: a `FakeTmdbClient` failure on the first call ends the session with a controlled, user-visible error and no fabricated candidates, in `tests/e2e/test_tmdb_failure.py`, per quickstart.md scenario 7 (FR-027) — passed immediately (parametrized over all three failure modes); confirms FR-027 was already correctly wired via T028/T044, not a new behavior
- [x] T074 [P] E2E test: a `FakeModelProvider` configured to fail 1–2 times succeeds via the bounded retry; configured to fail 3 times, the session ends with a controlled error after the bound is exhausted, in `tests/e2e/test_llm_failure.py`, per quickstart.md scenario 8 (FR-028) — covers both the agent-level retry and the CLI layer's controlled handling once `ModelCallError` propagates up; passed immediately, confirming T030/T045 were already correct
- [x] T075 [P] Adversarial test suite covering conflicting constraints, unsupported vibe language, prompt injection in both user text and a TMDB overview fixture, duplicate/near-duplicate candidates, and malformed LLM output, in `tests/adversarial/test_adversarial_cases.py`, per the outline's Test Strategy table. Since a `FakeModelProvider` never "interprets" anything, these tests prove the *deterministic* code (hard filters, dedup, contract validation) never special-cases hostile input, rather than proving a real model resists injection.
- [x] T076 [P] Unit test: an exported JSON file round-trips (parses back to an equivalent `UserSessionState`) and an exported Markdown file contains the expected sections (preferences applied, each filled role, any relaxed constraint), in `tests/unit/test_export.py` (FR-024) — write this first; it must fail before T077
- [x] T077 [P] Implement optional session export to JSON and to Markdown (satisfying T076) in new `src/streaming_discovery/cli/export.py` (FR-024), offered interactively after the recommendation is shown (`tests/integration/test_cli_export_offer.py`). Wires `UserSessionState` into `Orchestrator` (exposed as `orchestrator.session`, built up during `run_single_attempt` rather than changing that method's return type, so no existing caller/test needed to change) — the contract had existed and been tested since Foundational but was never actually constructed at runtime until now (`tests/unit/test_orchestrator_session_tracking.py`).
- [x] T078 [P] Run the full quickstart.md walkthrough (all 10 scenarios: 1, 1b, 2, 3, 4, 4b, 5, 6, 7, 8) as a documented, watchable demo session and record the transcript/output under `specs/001-streaming-discovery-assistant/` or `docs/`. First opportunity to confirm the unified `streaming-discovery` entry point (T072) actually works end-to-end. Recorded via a new standalone `scripts/record_quickstart_walkthrough.py` (not part of the installed package) that reconstructs each scenario's fixture data fresh and drives the real `Orchestrator`/`run_guided_cli` pipeline, writing captured output to `docs/quickstart-walkthrough.md`. Doing this surfaced a second dead-config gap of the same kind T077 fixed for `UserSessionState`: `Settings.demo_mode` had existed since Foundational but nothing branched on it. Fixed by adding `src/streaming_discovery/demo.py` (one fixture-backed scenario, mirroring US1) and wiring `cli/output.py`'s `build_orchestrator` to switch to fixture-backed fakes when `demo_mode` is set — covered by `tests/unit/test_demo_mode.py`, written and confirmed red (a real, harmless, credential-less call to OpenRouter returning 401) before the wiring made it pass.
- [x] T079 [P] Write `README.md` covering setup, demo-mode usage (no credentials required), and an architecture overview. Validating the README's own demo-mode command live (not just fixture-backed tests) surfaced a real crash: Rich's default spinner glyphs and this project's `●` role markers are non-ASCII, which raises `UnicodeEncodeError` on a legacy Windows console (cp1252) -- Panel/Table borders already get an automatic ASCII fallback from Rich on such consoles, but arbitrary content like these does not. Fixed by using `spinner="line"` (ASCII) in `cli/intake.py` and replacing the `●` markers with `*` in `cli/rich_ui.py`'s `_ROLE_DISPLAY`, with regression tests added in `tests/unit/test_rich_ui.py` and `tests/integration/test_guided_cli_rich_console.py` guarding both.
- [x] T080 [P] Write `CLAUDE.md` with TDD rules, the four agent contract boundaries, and implementation guidance, referencing `.specify/memory/constitution.md`'s principles directly rather than restating them — **completed ahead of schedule, before Phase 1, at the user's request**, so it can guide implementation from the start rather than only document it afterward; see `/CLAUDE.md`
- [x] T081 [P] Add an architecture diagram and a sequence diagram (pipeline + retry path) under `docs/` — both as Mermaid diagrams in `docs/architecture.md` (renders natively on GitHub): a component diagram showing the four agents, their contracts, and the deterministic/model-backed boundary, and a full request sequence diagram covering both bounded retries (the one discovery zero-result retry with soft-constraint relaxation, and the independent 1-2 LLM-call retries wherever a model is invoked). Linked from `README.md`.

---

## Phase 10: Post-Launch Refinements (from the first real live run)

**Purpose**: fixes and UX refinements raised after Polish, during the user's first live (non-demo-mode) run against real TMDB/OpenRouter credentials.

- [x] T082 Fix `MODEL_NAME` in the user's local `.env`: `deepseek/deepseek-chat-v4-0731` is not a valid OpenRouter model ID (the live run failed with a 400 from OpenRouter). The correct slug, confirmed against OpenRouter's own model page plus three independent listings, is `deepseek/deepseek-v4-flash-0731`. Config-only fix, no code/test change — `Settings`/`.env.example` already treat `MODEL_NAME` as a free-form required string per T020/T021.
- [x] T083 Suppress `pydantic-ai`'s startup banner in real (non-demo) runs by setting `PYDANTIC_AI_NO_BANNER=1` before constructing an `Agent` in `_RealModelProvider.generate` (`cli/output.py`) — the banner itself names this variable as the fix; it was cluttering terminal output and had been mistaken for an error. Factored into `_suppress_pydantic_ai_banner()` (uses `setdefault`, so an explicit user choice is never overridden), tested directly in `tests/unit/test_pydantic_ai_banner_suppression.py` without needing a real model call.
- [x] T084 Terminal observability: make the CLI's mid-pipeline status indicator (`cli/intake.run_guided_cli`'s `console.status(...)`) show which phase is currently running (interpreting the request, searching TMDB, curating picks) instead of one static message for the whole pipeline — requested as a stretch goal, and to make the multi-agent routing visible rather than a silent pause. Implemented as an optional `on_step` callback on `Orchestrator.run_single_attempt` (purely a UI notification hook -- makes no decision, calls no model, so it doesn't touch the Orchestrator's determinism boundary), called before each phase (`STEP_INTERPRETING`, `STEP_SEARCHING_TMDB`, a retry message naming the relaxed constraint, `STEP_CURATING_PICKS`); `run_guided_cli` wires it to `Status.update(...)` on the existing spinner. Tests: `tests/unit/test_orchestrator_step_callback.py` (phase order, retry naming, optional/no-op default), `tests/integration/test_guided_cli_rich_console.py`.
- [x] T086 Fix a real bug found on a live run against real TMDB: `RealTmdbClient.discover()` was sending genre and provider **names** straight through as `with_genres`/`without_genres`/`with_watch_providers` query parameters, but TMDB's discover endpoint requires numeric ids for all three -- a documented placeholder (`client.py`'s own NOTE comment, tied to T042) that was left unfinished when T042 was checked off, and never caught because every test exercises `FakeTmdbClient`, which ignores query params entirely (this codebase's TMDB adapter had never actually been called live before this session, per Process Log 003). This violates FR-009/FR-010/FR-029 (discovery-agent.md: hard constraints, including `provider_names`, MUST be applied as real TMDB query parameters, never silently ignored) -- any request naming a provider, or an included/excluded genre, was silently returning zero real candidates. Fix: genre names resolve via a new inverse lookup against `normalize.py`'s existing `MOVIE_GENRES`/`TV_GENRES` tables (case-insensitive, no extra network call); provider names resolve against a live, per-instance-cached fetch of `/watch/providers/{movie,tv}` (exact match, falling back to substring match); if none of a non-empty `provider_names` list resolves at all, an unmatched TMDB provider id is sent rather than omitting the filter, so the hard constraint fails closed (zero results) instead of silently being dropped (FR-010). Also tightens the Preference Agent's system prompt to classify genres using TMDB's own vocabulary, reducing name-mismatch risk at the source rather than only at resolution time.
- [x] T087 Vibe-only requests (no genre, no liked titles -- only tone/setting/theme descriptors) were returning TMDB's default "most popular" pool with nothing relating it to the request at all, since the Discovery Agent has always deliberately excluded subjective fields from `DiscoveryQuery` (discovery-agent.md: "never receives any subjective/free-text field"). The Recommendation Agent honestly flagged the weak matches (per spec.md User Story 2's own acceptance criteria for exactly this case), but the underlying pool was never actually related to the request, which is a poor result in practice even though it's spec-compliant. Fix, chosen with the user over two cheaper alternatives (broadening the pool; leaving it as spec-compliant but weak): add `DiscoveryQuery.vibe_keywords` (from `PreferenceProfile.tone_descriptors + setting_descriptors + theme_descriptors`), resolved to TMDB keyword ids inside `RealTmdbClient.discover()` via `/search/keyword` (full-phrase search, falling back to per-word search on a miss) and applied as `with_keywords` (OR semantics, soft -- an unresolved descriptor is dropped, not failed closed, since tone/setting/theme stay soft signals per data-model.md). Relaxing `RelaxableConstraint.TONE` now clears `vibe_keywords` too, alongside `included_genres` (T071). This is a real, deliberate revision of the Discovery Agent's documented boundary -- update `contracts/discovery-agent.md`, `data-model.md`'s DiscoveryQuery table, and spec.md's DiscoveryQuery Key Entity description to match: the agent still never *interprets* intent (no model call, still NFR-008-compliant) -- it now also applies a TMDB-native keyword search, the same class of deterministic, TMDB-server-side filtering FR-029 already requires for genre/provider/runtime, rather than leaving tone/setting/theme unused by discovery entirely.
- [x] T088 The confirmation-correction prompt ("Press Enter to continue, or type a correction...") reads real terminal input from inside the `with console.status(...)` block (T084), while the status spinner's `Live` background thread is still actively repainting that same terminal line -- so what the user types while correcting is garbled/invisible, reported live. Fix: `run_guided_cli`'s `confirm` closure now pauses the status (`status.stop()`) immediately before the blocking input read and resumes it (`status.start()`) immediately after, via a `_active_status` reference set once the `with` block is entered; both `Status.stop()`/`start()` (delegating to `Live.stop()`/`start()`) are idempotent, so this composes safely with the `with` block's own enter/exit calls.
- [x] T085 Guided intake skips a question already answered by free text, per spec.md line 308 ("the system may skip asking about a field it can already infer as unnecessary"), raised after a live run where a fully-descriptive free-text request was still followed by all five guided questions repeating the same ground. Design (chosen after weighing the cost/precision tradeoff with the user): `run_guided_cli` first interprets free text alone (one extra, bounded LLM call, only when free text was given; falls back to asking every question if that call fails) to get a partial `PreferenceProfile`. The three guided questions that map 1:1 to a single field (`format`->`media_type`, `services`->`providers`, `exclusions`->`excluded_genres`) are skipped outright when already populated. The two compound questions (`mood_and_interests` covers genres/tone/setting/theme; `optional_constraints` covers year range/runtime/season cap/language/liked/disliked titles/notes) are never skipped, since a binary skip would silently drop whichever of their several fields free text didn't cover — instead their prompt shows an "already noted: ..." preview of what free text already captured, so answering feels additive rather than a blind re-ask.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup. Blocks every user story.
- **User Stories (Phases 3–8)**: All depend on Foundational completion.
  - US1 (Phase 3) has no dependency on any other story and is the MVP. It is also the only story that touches the confirmation step's terminal interactivity (T045) — FR-006 is a universal requirement, not guided-intake-specific, so it is satisfied here rather than deferred to US6.
  - US2 (Phase 4) depends only on Foundational + US1's `RecommendationAgent` (T043) and `PreferenceAgent` (T041) existing to extend.
  - US3 (Phase 5) depends only on Foundational + US1's `DiscoveryAgent`/`RecommendationAgent` (T042, T043) to extend.
  - US4 (Phase 6) depends only on Foundational + US1's Orchestrator single-attempt wiring (T044) to extend with retry logic.
  - US5 (Phase 7) depends on US4's retry mechanism (T059) being in place, since its acceptance test exercises hard-constraint persistence *across* a retry.
  - US6 (Phase 8) depends only on Foundational + US1's already-interactive confirmation step (T045) — it adds guided-intake prompts that feed into that same step, not a second interactivity mechanism.
- **Polish (Phase 9)**: T071/T072 (the pre-Polish fix and UI addition) depend only on the Orchestrator/CLI work already merged through US6. Of the originally-planned tasks: T073/T074 need Foundational's fakes only; T075 needs US1–US3 for the scenarios it adversarially targets; T076–T079 need US1 at minimum.

### Within Each User Story

Tests before implementation; contract/data-model fields before the agent logic that uses them; Discovery/Preference/Recommendation agent changes before Orchestrator wiring that calls them.

### Parallel Opportunities

- All `[P]`-marked Setup tasks (T003–T005) run in parallel.
- Within Foundational, the contract-definition/contract-test pairs (T006–T019), the config pair (T020–T021), the TMDB-adapter tasks (T022–T028), and the LLM-provider tasks (T029–T032) are each internally parallelizable — they touch disjoint files — but the Orchestrator skeleton (T033–T035) depends on the contracts existing first.
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
3. **STOP and VALIDATE**: run `tests/e2e/test_specific_constraint_request.py`, `tests/e2e/test_partial_fill.py`, and the quickstart.md scenario 1/1b walkthroughs independently.
4. This is the outline's own "first implementation slice" — demo-ready before any retry, similarity, or guided-intake logic exists, and already satisfies FR-006 and FR-015/SC-008 in full.

### Incremental Delivery

1. Setup + Foundational → foundation ready.
2. US1 → validate independently → MVP demo.
3. US2, US3, US4, US6 → each validated independently → can proceed in any order (or in parallel) once US1 lands, since each extends a different part of US1 without touching the others' code paths.
4. US5 → validated independently → requires US4's retry mechanism first.
5. Phase 9 (Polish) → the two controlled-failure demos, the adversarial suite, export, and the project's required documentation/diagram artifacts.

### Constitutional check on this ordering

Principle I is satisfied because every implementation task in this list has a preceding, currently-failing test task — including export (T076 before T077), the pagination bound (T023 before T024), structured logging (T046 before T047), the confidence-note logic (T050 before T051), and the tone-relaxation fix (T071's own test written before the fix), the last of which was a gap found by reviewing the finished implementation rather than during `/speckit-analyze`, unlike the others. Principle II is satisfied because `orchestrator.py` and `discovery_agent.py` tasks throughout contain no `ModelProvider` dependency — only the Preference Agent and Recommendation Agent tasks do, per NFR-008. Principle VI is satisfied because no task here introduces an agent, contract, or field beyond what spec.md's Domain Model Minimization Rationale already justified, plus the `season_count_max`/`season_count`/`TmdbErrorInfo` additions whose gaps were caught and justified in data-model.md before or during this task list's construction.
