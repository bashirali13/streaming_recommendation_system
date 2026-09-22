# Phase 1 Data Model: Multi-Agent Streaming Discovery Assistant (MVP)

**Feature**: `001-streaming-discovery-assistant` | **Date**: 2026-09-22

Source: `spec.md` Key Entities and Domain Model Minimization Rationale. Every field below traces to a named consumer and requirement; see `spec.md` for the audit. Types are expressed in Python/Pydantic terms since Pydantic v2 is the resolved schema library (`research.md` §4).

## Shared enums

- **MediaType**: `movie` | `tv` | `either` — `either` is valid only on `PreferenceProfile` (an unresolved user preference); every `CandidateMedia` and `DiscoveryQuery` resolves to `movie` or `tv`.
- **RelaxableConstraint**: `tone` | `runtime` | `year_range` — the closed set FR-011 permits the Orchestrator to relax, in that fixed priority order. No other field is ever a legal value here, which is what makes "hard constraints are never relaxed" (FR-010) mechanically enforceable rather than a convention.
- **RecommendationRole**: `best_match` | `safe_pick` | `wildcard_pick`.

## PreferenceProfile

Produced by the Preference Agent (FR-004); consumed by the Orchestrator (to build `DiscoveryQuery` and to drive retry relaxation) and the Recommendation Agent (soft scoring, rationale).

| Field | Type | Notes |
|---|---|---|
| `media_type` | `MediaType \| None` | Hard constraint when set; `None` means unspecified, not "either" — FR-003 |
| `providers` | `list[str]` | Streaming service names as the user named them; hard constraint. Empty list = unspecified |
| `genres` | `list[str]` | Soft signal |
| `excluded_genres` | `list[str]` | Hard constraint — never relaxed (FR-010) |
| `tone_descriptors` | `list[str]` | Free-text mood/vibe terms (e.g., "dark", "moody"); soft; consumed only by the Recommendation Agent, never by the Discovery Agent (spec Key Entities: DiscoveryQuery) |
| `setting_descriptors` | `list[str]` | Same treatment as `tone_descriptors`, kept as a distinct field for rationale specificity (spec Assumptions) |
| `theme_descriptors` | `list[str]` | Same treatment as `tone_descriptors` |
| `languages` | `list[str]` | Soft unless the user marks it required |
| `year_min` / `year_max` | `int \| None` | Soft by default; relaxable via `RelaxableConstraint.year_range` |
| `runtime_max_minutes` | `int \| None` | Soft by default; relaxable via `RelaxableConstraint.runtime` |
| `liked_titles` | `list[str]` | Drives similarity-based discovery (User Story 3) |
| `disliked_titles` | `list[str]` | Soft negative signal for the Recommendation Agent; exact matches also excluded by the Discovery Agent at pool assembly |
| `additional_notes` | `str \| None` | Free-form, unparsed remainder; soft, consumed only by the Recommendation Agent's rationale step |
| `hard_override_fields` | `list[str]` | Names of otherwise-soft fields (`runtime_max_minutes`, `year_min`/`year_max`, `providers`) the user explicitly marked non-negotiable ("it MUST be...", per the outline's "user-designated hard constraints"). Fields not listed here keep their default hard/soft classification; `media_type` and `excluded_genres` are always hard and never appear here |

**Validation rules**: at least one of `media_type`, `providers`, `genres`, `tone_descriptors`, `setting_descriptors`, `theme_descriptors`, `liked_titles` must be non-empty/non-null (an entirely empty profile cannot proceed to discovery — this is the "blocking clarification" case the Preference Agent's non-responsibility list still requires the Orchestrator to detect). `year_min <= year_max` when both are set.

## DiscoveryQuery

Derived by the Orchestrator from a `PreferenceProfile` plus retry state; consumed by the Discovery Agent (FR-007, FR-029). Deliberately excludes every subjective/free-text field above — that is the boundary that keeps the Discovery Agent out of intent interpretation (spec Key Entities).

| Field | Type | Notes |
|---|---|---|
| `media_type` | `MediaType` (resolved, not `either`) | Required — the Orchestrator resolves `either` into one query per attempt, or a merged strategy; see `contracts/discovery-agent.md` |
| `provider_names` | `list[str]` | Passed through from `PreferenceProfile.providers` |
| `region` | `str` | From configuration (FR-020), not from the user |
| `included_genres` / `excluded_genres` | `list[str]` | `excluded_genres` is never emptied by relaxation |
| `year_min` / `year_max` | `int \| None` | May be widened only when `relaxed_constraint == year_range` |
| `runtime_max_minutes` | `int \| None` | Applied server-side for movies; enforced as a post-filter for TV (see `contracts/discovery-agent.md`). May be widened only when `relaxed_constraint == runtime` |
| `similarity_seed_titles` | `list[str]` | Resolved from `PreferenceProfile.liked_titles` (title → TMDB id resolution happens inside the Discovery Agent, not in this contract) |
| `exclude_titles` | `list[str]` | From `PreferenceProfile.disliked_titles`, for exact-match exclusion at pool assembly |
| `relaxed_constraint` | `RelaxableConstraint \| None` | `None` on the initial attempt; set to exactly one value on the retry attempt |
| `retry_number` | `int` | `0` for the initial attempt, `1` for the (only allowed) retry — FR-011/NFR-007 |
| `result_limit` | `int` | Bounded page/result cap — NFR-003 |

**Validation rules**: `retry_number` ∈ {0, 1}. `relaxed_constraint` MUST be `None` when `retry_number == 0`, and MUST be set when `retry_number == 1`. `excluded_genres` and `media_type` MUST be identical between the initial and retried query for the same session (hard constraints never change across attempts — FR-010).

## CandidateMedia

Produced by the Discovery Agent from normalized TMDB data (FR-008); consumed by the Recommendation Agent and, for the three selected roles, by the final output.

| Field | Type | Notes |
|---|---|---|
| `tmdb_id` | `int` | Dedup (FR-016), export (FR-024) |
| `media_type` | `MediaType` (resolved) | Hard-filter enforcement |
| `title` | `str` | Display |
| `overview` | `str` | Rationale evidence; always treated as inert text (FR-026) |
| `genres` | `list[str]` | Resolved names only — never raw TMDB genre ids |
| `release_year` | `int \| None` | Year only, not a full date |
| `vote_average` | `float` | Ranking signal, near-duplicate tie-break |
| `runtime_minutes` | `int \| None` | **Enrichment field** — populated only for candidates reaching ranking (FR-029), not the raw pool |
| `provider_names` | `list[str]` | **Enrichment field** — flatrate-only, configured region only (FR-019); populated only for candidates reaching ranking |
| `thematic_keywords` | `list[str]` | **Enrichment field** — populated only for candidates reaching ranking |

**Validation rules**: `vote_average` in `[0.0, 10.0]`. A candidate missing a value needed to satisfy a *hard* constraint (e.g., no runtime data when runtime is user-designated hard) is excluded from the pool rather than assumed to pass (spec Edge Cases).

## CandidatePool

Produced by one Discovery Agent invocation; consumed by the Orchestrator (retry decision) and the Recommendation Agent (ranking input).

| Field | Type | Notes |
|---|---|---|
| `candidates` | `list[CandidateMedia]` | May be empty |
| `relaxed_constraint` | `RelaxableConstraint \| None` | Echoed from the `DiscoveryQuery` that produced this pool |
| `retry_number` | `int` | Echoed from the `DiscoveryQuery` |
| `error` | `TmdbErrorInfo \| None` | Set only on a genuine TMDB failure (timeout/HTTP error/malformed response), never on a legitimate empty result — this is what lets the Orchestrator distinguish "TMDB is down" from "no matches" (FR-027) |

No `total_results` field (TMDB's raw unfiltered count has no consumer) and no `retry_required` field (the Orchestrator computes the retry decision itself from `len(candidates)` — see `contracts/orchestrator.md`).

## RecommendationPackage

Produced by the Recommendation Agent (FR-014–FR-018); consumed by the Orchestrator for final assembly and by the terminal output/export.

| Field | Type | Notes |
|---|---|---|
| `best_match` | `Recommendation \| None` | `None` only when zero qualifying candidates exist after the retry (full no-match case) |
| `safe_pick` | `Recommendation \| None` | `None` when fewer than 2 distinct qualifying candidates exist — FR-015/SC-008 |
| `wildcard_pick` | `Recommendation \| None` | `None` when fewer than 3 distinct qualifying candidates exist |
| `applied_constraints` | `PreferenceProfile` (or a summary view of it) | For user-facing transparency and export completeness (FR-024) |
| `relaxed_constraint` | `RelaxableConstraint \| None` | Singular, matching the one-relaxation cap (FR-011) — not a list |
| `unresolved_notes` | `str \| None` | Populated only in a partial or no-match outcome (FR-012) |

**`Recommendation`** (nested, one per filled role): `{ role: RecommendationRole, candidate: CandidateMedia, rationale: str, confidence_note: str | None }`. `confidence_note` is populated only when subjective-trait evidence is weak (FR-018); it is prose, not a numeric score, per the spec's Assumptions.

**Validation rules**: roles are filled contiguously in priority order — `safe_pick` cannot be set if `best_match` is `None`; `wildcard_pick` cannot be set if `safe_pick` is `None`. No two filled roles may reference the same or a near-duplicate `tmdb_id` (FR-016).

## UserSessionState

In-memory only (FR-023); not serialized to any contract boundary between agents, but is what the export feature (FR-024) writes out.

| Field | Type | Notes |
|---|---|---|
| `raw_user_input` | `str \| None` | The initial free-text request, if any |
| `intake_answers` | `dict[str, str \| None]` | Guided-intake answers keyed by prompt (format, services, mood, exclusions, optional constraints); blank entries stay `None`, never defaulted (FR-003) |
| `preference_profile` | `PreferenceProfile \| None` | Set once the Preference Agent completes and the user confirms it |
| `discovery_attempts` | `list[CandidatePool]` | At most 2 entries (initial + one retry) |
| `recommendation_package` | `RecommendationPackage \| None` | Final output, once produced |

## State transitions (Orchestrator-owned)

```text
intake_or_input_received
  → preferences_interpreted (Preference Agent runs; FR-004)
  → preferences_confirmed (user reviews/corrects; FR-006)
  → discovery_attempted[retry_number=0] (Discovery Agent runs)
      ├─ candidates found → ranked_and_selected (Recommendation Agent runs) → done
      └─ zero candidates → discovery_attempted[retry_number=1, relaxed_constraint=<next in priority order>]
            ├─ candidates found → ranked_and_selected → done
            └─ zero candidates → no_match_explained → done
```

A `TmdbErrorInfo` on any `CandidatePool` short-circuits this flow directly to a controlled-failure terminal state (FR-027), independent of the zero-candidate retry path.
