# Quickstart: Validating the Multi-Agent Streaming Discovery Assistant (MVP)

**Feature**: `001-streaming-discovery-assistant` | **Date**: 2026-09-22

This guide documents how each user journey from `spec.md` will be exercised once implemented, using the fixture-backed demo mode (FR-025, NFR-004) — no live TMDB or model credentials required. It is a validation guide, not an implementation guide; concrete file/module names are set in `tasks.md` during implementation, not here.

## Prerequisites

- Python 3.11+ installed.
- Project dependencies installed (`research.md` §1–4: PydanticAI, Pydantic v2, pydantic-settings, httpx, pytest).
- No `.env`/API keys required for the scenarios below — demo mode is selected via a configuration flag that swaps in the fixture-backed TMDB and model implementations described in `research.md` §5.
- Fixture data present under the test fixtures directory (recorded TMDB payloads for the candidate sets each scenario below depends on).

## Running the automated validation suite

```bash
pytest
```

This exercises every contract in `contracts/` (schema validation, both valid and invalid payloads), the Orchestrator's routing/retry logic against `data-model.md`'s state-transition diagram, and one end-to-end test per user story below (per `spec.md` SC-007).

## Scenario walkthroughs (demo mode)

Each walkthrough corresponds to one user story in `spec.md` and should be runnable as a fixture-backed demo session, not only as a pytest case, so the pipeline can be watched end-to-end.

### 1. Specific constraint request (User Story 1, P1)

- **Input**: "I have Netflix and Hulu. I want a movie after 2010 with a powerful female lead that is not a superhero movie."
- **Fixture set**: a candidate pool fixture with more than three qualifying titles after excluding the superhero genre.
- **Expected outcome**: three distinct roles returned (Best Match/Safe Pick/Wildcard Pick), no superhero-genre title present, no raw JSON visible, each pick has a short rationale.

### 1b. Partial-fill request — fewer than three qualifying candidates (User Story 1, P1)

- **Input**: same shape as scenario 1.
- **Fixture set**: a candidate pool fixture with exactly 1, and separately exactly 2, qualifying titles after hard filtering (two fixture variants).
- **Expected outcome**: with 1 qualifying candidate, only `best_match` is populated (`safe_pick`/`wildcard_pick` are `None`); with 2, `best_match` and `safe_pick` are populated and `wildcard_pick` is `None`. No constraint is broadened and no candidate is duplicated or reused across roles to force a third pick (spec.md Clarifications Q1, FR-015, SC-008).

### 2. Vague mood request (User Story 2, P1)

- **Input**: "Dark, moody, Eastern European vibes."
- **Fixture set**: candidates with varying overview/keyword alignment to the tone descriptors, including at least one weak match.
- **Expected outcome**: `PreferenceProfile` leaves `media_type`/`providers` unset; three picks returned when the fixture pool supports it; at least one pick's rationale carries a `confidence_note` reflecting weaker tone evidence.

### 3. Similarity-based request (User Story 3, P2)

- **Input**: "I loved Arrival, Ex Machina, and Severance. Give me something thoughtful but not extremely bleak."
- **Fixture set**: a similarity-lookup fixture keyed to the three named titles.
- **Expected outcome**: `liked_titles` populated distinctly from genre/tone fields; discovery draws from the similarity fixture rather than a generic genre search fixture.

### 4. Runtime-constrained request — retry success path (User Story 4, P2)

- **Input**: "I need something funny under 100 minutes for tonight."
- **Fixture set**: a first-attempt fixture returning zero candidates under the full constraint set, and a second (retry) fixture returning candidates once the runtime ceiling is relaxed.
- **Expected outcome**: exactly one retry occurs; the final output discloses that the runtime constraint was relaxed.

### 4b. Runtime-constrained request — retry failure path (User Story 4, P2)

- **Input**: same as above.
- **Fixture set**: both the initial and retry fixtures return zero candidates.
- **Expected outcome**: no second retry is attempted; the session ends with an explanation naming the blocking constraints.

### 5. Exclusion-based request (User Story 5, P2)

- **Input**: "Recommend a mystery series, but no police procedurals and nothing with more than three seasons."
- **Fixture set**: a pool containing some police-procedural titles (to prove exclusion) and a soft-constraint gap that triggers the one allowed retry.
- **Expected outcome**: the excluded sub-genre and season-count cap are enforced identically in both the initial and retried search.

### 6. Open/guided discovery request (User Story 6, P3)

- **Walkthrough**: opt into guided intake, answer format and mood prompts, leave providers/exclusions blank, review the confirmation summary, make one correction.
- **Expected outcome**: the confirmation summary shows only answered fields as populated; the correction is reflected in the `PreferenceProfile` used for discovery.

### 7. Controlled TMDB failure

- **Fixture set**: a fake TMDB client configured to raise a timeout/HTTP error on the first call.
- **Expected outcome**: session ends with a controlled, user-visible error; no retry is attempted; no fabricated candidates appear.

### 8. Controlled LLM-call failure

- **Fixture set**: a fake model client configured to fail outright (not return malformed output) for 1, then 2, then 3 consecutive calls.
- **Expected outcome**: with 1–2 failures, the bounded retry (FR-028) succeeds and the session proceeds normally; with 3 failures, the session ends with a controlled error after the bounded attempts are exhausted.

## What "done" looks like for this quickstart

Every one of the 10 scenarios above (1, 1b, 2, 3, 4, 4b, 5, 6, 7, 8) has a corresponding automated test (contributing to SC-007) and can also be run as a live, watchable demo session using the same fixture data — satisfying FR-025 as a demonstrable capability, not only a test-suite property.
