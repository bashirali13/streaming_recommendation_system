# Feature Specification: Multi-Agent Streaming Discovery Assistant (MVP)

**Feature Branch**: `001-streaming-discovery-assistant`

**Created**: 2026-09-22

**Status**: Draft

**Input**: User description: "Create the initial baseline specification for the Multi-Agent Streaming Discovery Assistant, based on the project outline at multi_agent_streaming_discovery_project_outline.md. A terminal-based streaming discovery assistant that helps a user choose a movie or TV show from vague moods, specific constraints, or a mix of both, using a multi-agent architecture (Orchestrator, Preference Agent, Discovery Agent, Recommendation Agent) communicating via validated Pydantic JSON contracts, with TMDB as the sole external data source. Returns exactly three recommendation roles (Best Match, Safe Pick, Wildcard Pick), supports one bounded zero-result retry with deterministic soft-constraint relaxation, never silently relaxes hard constraints/exclusions, never shows raw TMDB JSON to the user, and holds session state in memory only. Scoped as the MVP slice: guided-but-optional terminal intake; movie/TV/either; provider/mood/exclusion/constraint capture; PreferenceProfile -> CandidatePool -> RecommendationPackage pipeline; one retry policy; fixture-backed deterministic demo mode."

## Problem Statement

People often know they want to watch *something* tonight but cannot translate that feeling into a search query a streaming service or search engine understands. Existing platform search requires either an exact title or rigid filter selection, and it does not handle vague mood-based requests ("something dark and moody"), multi-constraint requests ("Netflix or Hulu, after 2010, powerful female lead, not superhero"), or similarity requests ("something like Arrival and Severance") in a single interaction. Users are left either browsing endlessly or receiving oversized, undifferentiated result lists that create decision fatigue rather than resolving it.

This project addresses that gap with a terminal-based assistant that interprets natural-language taste signals (vague or specific), retrieves real candidate titles from a single trusted metadata source (TMDB), and narrows the result down to three clearly differentiated, explained picks — rather than a list to browse.

## Goals

- Accept vague mood/vibe requests (e.g., "dark, moody, Eastern European vibes") and specific constraint-based requests (e.g., "Netflix or Hulu, movie, after 2010, powerful female lead, not superhero") through the same interface.
- Offer an optional, lightweight terminal intake that guides users who don't know what to ask for, without forcing a rigid questionnaire on users who already know what they want.
- Translate natural language and/or intake answers into a structured, validated preference representation before any discovery happens.
- Retrieve candidate movies/TV shows from TMDB and normalize them into a bounded, structured candidate pool.
- Rank and curate candidates into exactly three differentiated recommendation roles — **Best Match**, **Safe Pick**, and **Wildcard Pick** — with a plain-language rationale for each.
- Make agent collaboration and decision-making visible and auditable through typed, validated JSON contracts between agents rather than free-form text handoffs.
- Guarantee that explicit exclusions and other hard constraints are never silently dropped or relaxed to produce a result.
- Apply exactly one bounded, deterministic retry when initial discovery yields zero candidates, and clearly disclose any relaxed constraint in the final output.
- Drive development spec-first and test-first: every capability in this specification is expected to map to acceptance criteria and tests written before implementation (SDD/TDD), per this project's SpecKit-driven process.

## Scope

**In scope for this MVP specification:**

- A terminal (command-line) conversational flow: optional guided intake, free-text preference input, confirmation of the interpreted preferences, and a final three-pick recommendation output.
- Support for movies, TV series, or either, as the requested format.
- Capture of streaming service/provider preference, mood/genre/tone/setting/theme signals, exclusions, and optional constraints (release year range, runtime ceiling, language, liked titles, disliked titles, free-form notes).
- A four-agent pipeline — Orchestrator, Preference Agent, Discovery Agent, Recommendation Agent — communicating exclusively through validated structured (Pydantic) contracts.
- TMDB as the single external data source for search, discovery, similar-title lookups, title details, genre metadata, and watch-provider metadata.
- Deterministic, orchestrator-owned handling of the case where the initial discovery search returns zero candidates: exactly one retry with one soft constraint relaxed according to a fixed priority order.
- A final recommendation package containing at most three roles (Best Match, Safe Pick, Wildcard Pick), each with a concise rationale, and a disclosure of any relaxed constraint.
- An in-memory session model (no database, no persistent storage) with an optional end-of-session export.
- A fixture-backed, deterministic demo mode that reproduces the full pipeline without live TMDB or LLM credentials, for testing and demonstration.

## Non-Goals

The following are explicitly **out of scope** for this specification and for the MVP:

- General film/TV research, review aggregation, trivia, or fact-based question answering. The assistant only exists to help the user pick something to watch.
- Retrieval-augmented generation (RAG), vector databases, embeddings-based semantic search, or any open-ended research/citation behavior.
- Web scraping or any external data source other than TMDB.
- Persistent storage of any kind (no SQLite, no file-backed database, no user accounts, no cross-session history/profile memory).
- Returning more than three primary recommendations, or any "browse a list" style output.
- More than one discovery retry per user request; the system does not loop until it finds a match.
- Silent relaxation of hard constraints or explicit user exclusions under any circumstance.
- Displaying raw TMDB API payloads or raw inter-agent JSON to the end user.
- A graphical or web front-end (explicitly called out in the source outline as a stretch goal only, not part of this MVP spec).
- Guaranteeing that TMDB-reported watch-provider availability reflects a user's actual, current subscription access.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Specific Constraint Request (Priority: P1)

A user who already knows what they want expresses it as a single detailed request: format, providers, and multiple hard/soft constraints together (e.g., "I have Netflix and Hulu. I want a movie after 2010 with a powerful female lead that is not a superhero movie.").

**Why this priority**: This is the core "specific request" path called out as a primary demo scenario in the project outline, and it exercises the full pipeline (preference extraction with mixed hard/soft constraints → discovery → ranking → three-pick output) in the most information-rich form. It is the foundation the vaguer scenarios build on.

**Independent Test**: Can be fully tested by submitting a single specific-constraint request against fixture-backed TMDB data and verifying that the resulting PreferenceProfile correctly separates hard constraints (format, exclusion of superhero genre) from soft preferences (recency, "powerful female lead" tone), and that the final output contains three distinct, constraint-respecting picks.

**Acceptance Scenarios**:

1. **Given** a specific request naming providers, format, a release-year floor, a tone descriptor, and a genre exclusion, **When** the request is processed, **Then** the system returns a PreferenceProfile that marks the genre exclusion and format as hard constraints and the tone/recency as soft preferences.
2. **Given** that same request and a fixture candidate pool with more than three qualifying titles, **When** discovery and ranking complete, **Then** the system returns exactly three distinct titles assigned to Best Match, Safe Pick, and Wildcard Pick, none of which belong to the excluded genre.
3. **Given** the same request, **When** the final recommendation is displayed, **Then** no raw TMDB JSON or raw inter-agent payload is shown to the user, and each pick includes a short, human-readable rationale.

---

### User Story 2 - Vague Mood Request (Priority: P1)

A user expresses only an emotional/aesthetic vibe with no explicit format, provider, or hard constraint (e.g., "Dark, moody, Eastern European vibes.").

**Why this priority**: Handling under-specified, subjective input without inventing facts or forcing the user through a full questionnaire is central to the product's value proposition and is explicitly called out as a primary supported request type.

**Independent Test**: Can be fully tested by submitting a mood-only request and verifying that unspecified fields remain null/unspecified (not guessed), that the request is still treated as valid input to discovery, and that three picks are returned with rationale reflecting the vibe-matching confidence.

**Acceptance Scenarios**:

1. **Given** a request containing only tone/setting descriptors and no format, provider, or explicit constraint, **When** the Preference Agent processes it, **Then** the resulting PreferenceProfile leaves format, providers, and unmentioned fields unspecified rather than populated with invented defaults.
2. **Given** that profile, **When** discovery and ranking run against fixture data, **Then** the system still returns three picks (when enough candidates exist) and each rationale reflects that the match is based on subjective tone signals.
3. **Given** that the vibe language maps weakly to available candidate metadata, **When** the Recommendation Agent scores fit, **Then** the confidence signal communicated to the user for tone-based matching is visibly lower than for a request with explicit hard constraints.

---

### User Story 3 - Similarity-Based Request (Priority: P2)

A user names titles they liked and asks for something in a similar spirit, optionally with a soft exclusion (e.g., "I loved Arrival, Ex Machina, and Severance. Give me something thoughtful but not extremely bleak.").

**Why this priority**: Similarity-based discovery is a distinct input shape (titles instead of descriptors) that exercises TMDB's similar-title lookup path and a different preference-extraction pattern than mood or constraint-based requests.

**Independent Test**: Can be fully tested by submitting a liked-titles request and verifying the liked titles are captured distinctly from genre/tone fields and used to drive discovery via similarity lookups against fixture data.

**Acceptance Scenarios**:

1. **Given** a request naming multiple liked titles and one soft tonal exclusion ("not extremely bleak"), **When** processed, **Then** the PreferenceProfile records the liked titles as a distinct field from genres/tones, and the bleakness exclusion is treated as soft (not hard).
2. **Given** fixture candidate data related to the liked titles, **When** discovery runs, **Then** the candidate pool is built using similarity to the named titles rather than generic genre search alone.

---

### User Story 4 - Runtime-Constrained Request (Priority: P2)

A user needs something that fits a specific time budget (e.g., "I need something funny under 100 minutes for tonight.").

**Why this priority**: Runtime is called out explicitly in the outline as the first soft constraint eligible for relaxation, making this scenario the clearest way to validate both constraint capture and the retry/relaxation policy end-to-end.

**Independent Test**: Can be fully tested with a fixture pool that yields zero results under the full constraint set (genre + runtime ceiling) but non-zero results once the runtime ceiling is relaxed, verifying the one-retry policy fires correctly and the relaxation is disclosed.

**Acceptance Scenarios**:

1. **Given** a comedy request with a runtime ceiling, **When** the initial discovery search under all constraints returns zero candidates, **Then** the Orchestrator relaxes the runtime constraint (not the genre) and retries exactly once.
2. **Given** the retried search returns candidates, **When** the final package is produced, **Then** it explicitly discloses that the runtime constraint was relaxed.
3. **Given** the retried search also returns zero candidates, **When** the Orchestrator evaluates the result, **Then** the system stops, issues no further retry, and explains which constraints prevented a match.

---

### User Story 5 - Exclusion-Based Request (Priority: P2)

A user asks for a category of content but explicitly rules out sub-types (e.g., "Recommend a mystery series, but no police procedurals and nothing with more than three seasons.").

**Why this priority**: This scenario validates that explicit, user-stated exclusions are treated as hard constraints and are protected from the retry/relaxation policy, which is one of the project's non-negotiable guarantees.

**Independent Test**: Can be fully tested by confirming that, even when the retry policy is triggered for an unrelated soft constraint, the explicitly excluded sub-genre and season-count ceiling are still enforced in both the initial and retried search.

**Acceptance Scenarios**:

1. **Given** a mystery-series request excluding "police procedural" and capping season count, **When** the PreferenceProfile is built, **Then** both the sub-genre exclusion and the season-count cap are marked as hard constraints.
2. **Given** zero initial candidates due to an unrelated soft preference, **When** the Orchestrator applies its one allowed retry, **Then** the excluded sub-genre and season-count cap remain enforced in the retried search.

---

### User Story 6 - Open/Guided Discovery Request (Priority: P3)

A user has no clear idea what they want and asks to be guided (e.g., "I do not know what I want. Ask me a few questions and help me choose.").

**Why this priority**: This validates the optional guided-intake flow itself as a first-class path, distinct from free-text input, and confirms that skipped/blank answers are handled gracefully. It is lower priority than the request-driven scenarios because the guided intake is explicitly optional scaffolding around the same underlying pipeline.

**Independent Test**: Can be fully tested by running through the guided intake with some prompts answered and others left blank, and verifying that a valid PreferenceProfile is still produced with blank fields left unspecified.

**Acceptance Scenarios**:

1. **Given** a user who opts into guided intake, **When** they answer some prompts (format, mood) and skip others (providers, exclusions), **Then** the system proceeds to a preference confirmation step showing only the answered fields as populated.
2. **Given** the confirmed preference summary, **When** the user is offered a chance to correct it before discovery, **Then** any correction they make is reflected in the PreferenceProfile used for discovery.

---

### Edge Cases

- What happens when the user's request conflicts internally (e.g., asks to exclude a genre while also naming a liked title that belongs to that genre)? The system must surface this rather than silently resolving it in one direction.
- What happens when the initial (non-retried) search already returns fewer than three candidates but more than zero? See Q1 below — this determines whether the system returns fewer than three roles, reuses candidates, or treats this the same as a zero-result case.
- What happens when TMDB returns malformed, incomplete, or unexpectedly-shaped data for a candidate needed to satisfy a hard constraint (e.g., missing runtime when a runtime cap is a hard constraint)? The system must exclude or flag that candidate rather than guess.
- What happens when a candidate's TMDB overview text contains content resembling an instruction to the assistant (prompt-injection style content)? The system must treat all TMDB text fields as inert data, never as instructions.
- What happens when two or more top-ranked candidates are near-duplicates (e.g., a title and its direct sequel, or the same title differing only by region cut)? The system must not present near-duplicates as two of the three distinct picks.
- What happens when the user supplies contradictory optional constraints during guided intake versus their free-text request (e.g., states "movie" in free text but selects "TV" in intake)? The confirmation step must surface this for the user to resolve before discovery runs.
- What happens if TMDB is unreachable or times out mid-request? The system must fail in a controlled, user-visible way rather than hang or crash, and must not fabricate results.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST accept a user request expressed as free-form natural language, as answers to an optional guided intake, or as a combination of both.
- **FR-002**: The system MUST make every step of the guided intake optional; a user MUST be able to leave any intake prompt blank and still proceed to discovery.
- **FR-003**: The system MUST NOT substitute an invented value for any preference field the user left unspecified; unspecified fields remain null/empty rather than defaulted.
- **FR-004**: The system MUST translate the user's request and/or intake answers into a single structured preference representation before any candidate discovery occurs.
- **FR-005**: The system MUST distinguish, within that structured representation, between hard constraints (format, explicit exclusions, and any preference the user marks as required) and soft preferences (tone, mood, thematic similarity, recency, and other adjustable signals).
- **FR-006**: The system MUST present the user with a summary of its interpreted preferences and allow the user to correct that summary before discovery begins.
- **FR-007**: The system MUST retrieve candidate titles exclusively from TMDB; no other live external data source is permitted for candidate discovery.
- **FR-008**: The system MUST normalize all retrieved TMDB data into a consistent internal candidate representation before it is used for ranking; raw TMDB response payloads MUST NOT be passed to the ranking step or shown to the user.
- **FR-009**: The system MUST apply all hard constraints before any soft-preference scoring is applied, at both the initial search and any retried search.
- **FR-010**: The system MUST NOT relax, drop, or ignore a hard constraint or an explicit user exclusion under any circumstance, including when doing so would be the only way to produce a non-empty result.
- **FR-011**: When the initial discovery search yields zero qualifying candidates, the system MUST perform exactly one additional discovery attempt with exactly one pre-approved soft constraint relaxed, chosen in this fixed order of preference: (1) subjective vibe/tone precision, (2) runtime ceiling, (3) release-year range.
- **FR-012**: If the retried search also yields zero qualifying candidates, the system MUST stop without further retries and MUST explain to the user which constraints could not be satisfied.
- **FR-013**: Whenever a soft constraint was relaxed to produce results, the system MUST disclose the relaxed constraint in the final output shown to the user.
- **FR-014**: The system MUST rank qualifying candidates by fit to the user's soft preferences after hard filtering.
- **FR-015**: The system MUST select at most three recommendations from the ranked candidates, assigned to three distinct roles — Best Match, Safe Pick, and Wildcard Pick — and MUST NOT present more than these three as primary recommendations. [NEEDS CLARIFICATION — see Q1]
- **FR-016**: The system MUST NOT assign duplicate or near-identical titles (e.g., the same title, or a direct sequel/prequel/alternate-cut of an already-selected title) to more than one of the three roles.
- **FR-017**: Each recommended title MUST be accompanied by a concise, human-readable rationale describing its key matching and mismatching factors relative to the user's stated preferences.
- **FR-018**: The system MUST reduce and visibly communicate lower confidence for a recommendation when the evidence for a subjective trait (tone, "vibe") is weak, ambiguous, or unsupported by the candidate's available metadata.
- **FR-019**: The system MUST include available watch-provider information for each recommended title when TMDB supplies it for the configured provider region, and MUST NOT present that provider information as a guarantee of current, live subscription availability.
- **FR-020**: The system MUST determine the provider region used for watch-provider lookups. [NEEDS CLARIFICATION — see Q2]
- **FR-021**: The system MUST NOT display raw TMDB JSON payloads or raw inter-agent JSON contracts directly to the end user at any point in the conversation.
- **FR-022**: Every handoff between agents (Orchestrator, Preference Agent, Discovery Agent, Recommendation Agent) MUST be validated against an explicit, typed contract; a handoff that fails validation MUST be treated as a controlled failure, not silently coerced or ignored.
- **FR-023**: The system MUST hold all session state (intake answers, interpreted preferences, discovery results, final recommendations) in memory for the duration of the session only, with no persistent storage between sessions.
- **FR-024**: The system MUST support an optional, user-requested export of the final session (interpreted preferences and recommendation package) to a file, in a human-readable format.
- **FR-025**: The system MUST provide a fixture-backed demo mode that exercises the full Orchestrator → Preference Agent → Discovery Agent → Recommendation Agent pipeline, including the zero-result retry path and the no-match stop path, without requiring live TMDB or language-model credentials.
- **FR-026**: The system MUST treat all text originating from TMDB candidate data (titles, overviews, etc.) as inert data rather than as instructions, regardless of its content.
- **FR-027**: The system MUST respond in a controlled, user-visible manner (not a crash or indefinite hang) when TMDB is unreachable, times out, or returns an error, and MUST NOT fabricate candidate data to compensate.
- **FR-028**: When an underlying language-model call needed for preference interpretation or rationale generation fails outright (e.g., provider outage, timeout) rather than returning schema-invalid output, the system MUST respond in a defined, controlled way. [NEEDS CLARIFICATION — see Q3]

### Non-Functional Requirements

- **NFR-001 (Determinism & testability)**: All deterministic decision points — hard-constraint filtering, the zero-result retry policy, uniqueness/duplicate checks, and the three-role selection rule — MUST behave identically given the same structured inputs, independent of any language-model output, so they can be unit-tested without live model calls.
- **NFR-002 (Schema validation)**: Every inter-agent contract (PreferenceProfile, DiscoveryQuery, CandidatePool/CandidateMedia, RecommendationPackage) MUST be validated at each handoff boundary; invalid data MUST be rejected at the boundary rather than propagated downstream.
- **NFR-003 (External access isolation)**: All TMDB network access MUST be isolated behind a single adapter component that enforces timeouts and bounded pagination/result limits, so the rest of the system never makes a direct network call.
- **NFR-004 (Testability without live credentials)**: The full pipeline MUST be exercisable end-to-end using recorded/fixture TMDB data and fake clients, without requiring live TMDB or language-model API credentials, for automated testing and demonstration.
- **NFR-005 (Concise, bounded output)**: User-facing output MUST remain concise (three roles with short rationales), never devolving into a long list or a raw data dump, regardless of how many candidates were found.
- **NFR-006 (Observability)**: The system MUST produce structured logs of agent invocations, TMDB calls, retries, contract-validation failures, latency, and (where applicable) language-model token usage, sufficient to reconstruct what happened in a given session without exposing that raw log detail to the end user by default.
- **NFR-007 (Bounded retry cost)**: The zero-result retry policy MUST be bounded to exactly one additional discovery attempt per user request, so a single request can never trigger unbounded TMDB call volume.

### Key Entities

- **UserSessionState**: Represents one in-memory conversation session — raw user input, guided-intake answers, the confirmed preference profile, discovery/retry history, and the final recommendation package, held only for the session's lifetime.
- **PreferenceProfile**: The structured, validated representation of what the user wants — format, providers, genres and excluded genres, tones/settings/themes, languages, release-year and runtime bounds, liked/disliked titles, and an explicit separation of hard constraints from soft preferences.
- **DiscoveryQuery**: The structured request the Orchestrator hands to the Discovery Agent describing how to query TMDB for one discovery attempt — including which constraint (if any) has been relaxed for a retry, and which retry number this is.
- **CandidateMedia**: A single normalized movie or TV title as returned by TMDB and shaped for downstream use — identifier, media type, title, overview, genres, release information, rating/popularity signals, language, runtime (when retrieved), and available provider metadata.
- **CandidatePool**: The bounded set of CandidateMedia produced by one discovery attempt, along with metadata about the query that produced it, whether a retry is required, and any errors encountered.
- **RecommendationPackage**: The final output — Best Match, Safe Pick, and Wildcard Pick (each a CandidateMedia plus rationale), the constraints that were applied, any constraint that was relaxed, and any unresolved notes explaining a partial or no-match outcome.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user submitting either a vague mood-only request or a fully specific constraint-based request receives a complete recommendation response (three roles, or a clear no-match explanation) in a single conversational pass, without needing to restate their request.
- **SC-002**: 100% of final recommendation outputs contain zero raw TMDB payload fragments and zero raw inter-agent JSON.
- **SC-003**: 100% of sessions where the user states an explicit exclusion or hard constraint result in a final output that respects that constraint, including in the retried search.
- **SC-004**: When at least three qualifying, distinct candidates exist after applying hard filters (on the initial search or the one allowed retry), the system returns exactly three distinct recommendation roles in 100% of such cases.
- **SC-005**: When the initial search yields zero qualifying candidates, the system performs exactly one retry and, whether or not that retry succeeds, always communicates a clear outcome (relaxed-constraint disclosure, or a no-match explanation naming the blocking constraints) — never an unexplained empty result.
- **SC-006**: A full demonstration run (guided intake through final recommendation, including one retry scenario) can be completed using only fixture data, with no live TMDB or language-model credentials required.
- **SC-007**: Every documented user journey (vague mood, specific constraints, similarity, runtime-bounded, exclusion-based, guided/open discovery) has at least one passing automated test demonstrating it end-to-end before that journey is considered complete.

## Acceptance Criteria / Definition of Done

Drawn from the project outline's acceptance-criteria themes and definition of done, applied to this MVP scope:

**Acceptance criteria themes**

- Both vague and specific requests produce a valid, schema-conformant PreferenceProfile.
- Blank/unanswered optional intake fields remain null or empty in the PreferenceProfile — never auto-filled.
- Hard exclusions and hard constraints are never silently relaxed, in either the initial or retried search.
- The Discovery Agent's output consists of normalized CandidateMedia objects only — never raw TMDB records.
- A zero-candidate initial search always triggers exactly one broadened retry, never zero and never more than one.
- The retried search always records which single soft constraint was relaxed.
- A retried search that still yields zero candidates ends the workflow with an explanation — it never loops further.
- Ranking always applies hard filters before soft-preference scoring.
- The Recommendation Agent returns Best Match, Safe Pick, and Wildcard Pick as distinct titles whenever enough qualifying candidates exist.
- TMDB errors and malformed upstream (LLM) output both produce controlled, user-visible failures rather than crashes or silent guesses.
- Every inter-agent handoff is validated against its typed contract before use.

**Definition of done (for this specification's scope)**

- Every user story above has documented acceptance scenarios before any implementation begins.
- The retry path (User Story 4, success and failure sub-cases) and the fully-specified request path (User Story 1) are both demonstrable end-to-end using fixture data.
- A fixture-backed demo can run the full pipeline with no API or model credentials.
- Each agent's responsibilities and explicit non-responsibilities (per the project outline's architecture section) are reflected in this spec's functional requirements and are not contradicted by them.
- Output shown to the user is concise, contains no raw JSON, and always identifies any relaxed constraint.
- All three [NEEDS CLARIFICATION] questions below are resolved (or explicitly deferred with a documented owner/decision date) before `/speckit-plan` is run.

## Assumptions

- **Intake question set and order**: The six-step guided intake table in the project outline (format, services, mood/interests, exclusions, optional constraints, confirmation) is treated as the default guided-intake structure; the system may skip asking about a field it can already infer as unnecessary, but does not reorder the fixed sequence for this MVP.
- **Duplicate/near-duplicate tie-breaking**: When two candidates are judged near-identical (same title, or a direct sequel/prequel/alternate cut), the higher-ranked one by the ranking step's own score is kept and the other is excluded from consideration for any of the three roles, rather than surfaced separately.
- **Confidence signaling**: "Reduced confidence" for weak subjective-trait evidence (FR-018) is surfaced qualitatively within a pick's written rationale (e.g., naming the uncertainty) for this MVP, not as a separate numeric confidence score with defined thresholds; a numeric confidence model may be introduced in a later iteration if warranted.
- **Session export trigger and format**: Export is user-initiated at the end of a session (not automatic), and both JSON and Markdown are acceptable output formats per the source outline; the user chooses the format at export time.
- **Language/runtime scope**: The system only needs to support English-language interaction and TMDB's English-locale metadata for the MVP; other locales are not excluded by design but are not required to be tested for this spec.
- **Single-user, single-session scope**: The system serves one user in one terminal session at a time; concurrent multi-user session handling is out of scope for this specification.

## Open Questions Requiring Clarification

The following three questions are the highest-impact ambiguities identified in the source outline and are blocking for planning. They are also embedded inline above as `[NEEDS CLARIFICATION]` markers.

### Q1: Minimum qualifying-candidate threshold for the three-role guarantee

**Context**: FR-015 states the system selects at most three roles "when enough candidates exist," and the outline says three roles are guaranteed "when enough candidates exist" but does not define what happens when the initial search (or the one allowed retry) yields 1 or 2 qualifying, non-duplicate candidates — a non-zero but insufficient count.

**What we need to know**: Should a 1–2 candidate result (after hard filtering and de-duplication) be treated as (a) a partial success returning fewer than three roles, (b) treated the same as a zero-result case and trigger the one allowed retry, or (c) treated as a no-match/insufficient-result outcome with an explanation, even though it is technically non-zero?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A | Return fewer than three roles (e.g., just Best Match, or Best Match + Safe Pick) when only 1–2 qualify | Simple, but weakens the "always three distinct picks" value proposition and needs its own acceptance criteria for degraded output |
| B | Treat 1–2 candidates the same as zero for retry purposes — the retry policy fires to try to reach three | Keeps the "three roles" promise stronger, but blurs the "zero-result retry" trigger definition (retry becomes "insufficient-result retry") |
| C | Treat 1–2 candidates as a no-match outcome with an explanation, same messaging shape as the zero-candidate stop case | Simplifies logic (only two outcomes: 3-role success or explained non-success) but discards usable near-misses |
| Custom | Provide your own rule | — |

**Your choice**: _[Wait for user response]_

---

### Q2: Provider/region configuration mechanism

**Context**: FR-019/FR-020 and the outline's TMDB Integration section both reference "a configured region" for watch-provider lookups, but the outline never states whether that region is a fixed system default, an intake-time user selection, or a pre-session configuration value (e.g., an environment/config setting).

**What we need to know**: How is the watch-provider region determined for a given session?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A | Fixed default (e.g., "US") baked into configuration for the MVP, not user-facing | Simplest; no new intake step; matches "one configured region" language in the outline most literally |
| B | User selects region during guided intake (new intake field) | More correct for non-US users, but adds an intake step and a new PreferenceProfile field not currently listed in the outline's field set |
| C | Read from an environment/config value at startup, with a hardcoded fallback default, but never asked of the user | Balances flexibility (deployer can change it) with a simple user experience |
| Custom | Provide your own rule | — |

**Your choice**: _[Wait for user response]_

---

### Q3: Behavior when an underlying language-model call fails outright

**Context**: The outline states "LLM outputs are schema-validated" and that malformed LLM output produces a controlled failure, but it does not address the distinct case where the model call itself fails to return anything (timeout, provider outage, rate limit) — a failure mode separate from "the model responded but the output didn't validate."

**What we need to know**: When a language-model call needed for preference interpretation or rationale generation fails to complete at all, should the system (a) abort the whole request with a clear error message, (b) retry the model call itself a bounded number of times before aborting, or (c) fall back to a deterministic/non-LLM degraded path (e.g., treat the entire input as an unparsed soft preference) rather than aborting?

**Suggested Answers**:

| Option | Answer | Implications |
|--------|--------|--------------|
| A | Abort immediately with a controlled, user-visible error; no automatic retry of the model call | Simplest and most predictable; consistent with "one bounded retry" philosophy already used for discovery, but a transient provider blip fails the whole session |
| B | Retry the model call itself up to a small bounded number of times (e.g., 1–2) before aborting | Improves resilience to transient provider issues, but introduces a second, separate retry concept alongside the discovery retry that needs its own acceptance criteria |
| C | Fall back to a deterministic degraded interpretation (e.g., minimal keyword extraction) rather than aborting | Keeps the session alive, but risks a lower-quality PreferenceProfile that the user did not explicitly approve, and adds meaningful implementation complexity for the MVP |
| Custom | Provide your own rule | — |

**Your choice**: _[Wait for user response]_
