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
| `excluded_genres` | `list[str]` | Hard constraint — never relaxed (FR-010); only TMDB's fixed genre vocabulary (see preference_agent.py's system prompt) |
| `excluded_keywords` | `list[str]` | Hard constraint — never relaxed (FR-010). For an exclusion that isn't one of TMDB's fixed genre names — a franchise, studio, character universe, etc. (e.g. "not Marvel or DC") — captured here instead of `excluded_genres`, and never left only in `additional_notes` (T091), which nothing downstream enforces. Resolved to TMDB keyword ids inside `RealTmdbClient.discover()` via `/search/keyword` and applied as `without_keywords`; also re-checked as a title/overview/thematic_keywords text match in both the Discovery Agent's bulk-item filter and the Recommendation Agent's hard filter, since TMDB's own keyword tagging isn't guaranteed complete for every excluded concept — the text-match layers are what actually uphold "never silently drop a hard constraint" when keyword resolution alone can't |
| `tone_descriptors` | `list[str]` | Free-text mood/vibe terms (e.g., "dark", "moody"); soft; consumed by the Recommendation Agent (scoring/rationale) and, since T101, also by the Discovery Agent as part of `vibe_keywords` (see that field's own row for why this is safe) |
| `setting_descriptors` | `list[str]` | Same treatment as `tone_descriptors`, kept as a distinct field for rationale specificity (spec Assumptions) |
| `theme_descriptors` | `list[str]` | Same treatment as `tone_descriptors` |
| `languages` | `list[str]` | Soft unless the user marks it required. The user's common English name for the language (e.g. "Spanish", "Korean") — resolved to a TMDB ISO 639-1 code inside `RealTmdbClient.discover()` via TMDB's own `/configuration/languages` list (T104). Until T104 this field was captured by the Preference Agent and shown in the confirmation summary but never actually reached `DiscoveryQuery` or `discover()` at all — the same class of dead-field bug T090 found and fixed once for `additional_notes` |
| `year_min` / `year_max` | `int \| None` | Soft by default; relaxable via `RelaxableConstraint.year_range` |
| `runtime_max_minutes` | `int \| None` | Soft by default; relaxable via `RelaxableConstraint.runtime` |
| `season_count_max` | `int \| None` | TV-only; hard only when the user explicitly caps it (e.g., "nothing with more than three seasons" — User Story 5), so it is always added to `hard_override_fields` when set, never left soft by default. Not part of `RelaxableConstraint` — a season-count cap the user stated is never relaxed |
| `liked_titles` | `list[str]` | Drives similarity-based discovery (User Story 3) |
| `disliked_titles` | `list[str]` | Soft negative signal for the Recommendation Agent; exact matches also excluded by the Discovery Agent at pool assembly |
| `additional_notes` | `str \| None` | Free-form, unparsed remainder; soft, consumed only by the Recommendation Agent's rationale step |
| `hard_override_fields` | `list[str]` | Usually populated by user choice: names of otherwise-soft fields (`runtime_max_minutes`, `year_min`/`year_max`, `providers`) the user explicitly marked non-negotiable ("it MUST be...", per the outline's "user-designated hard constraints"). One field enters this list automatically rather than by user choice: `season_count_max` is always added here whenever it is set at all (see its own row below) — a stated season cap has no soft form. Fields not listed here keep their default hard/soft classification; `media_type`, `excluded_genres`, and `excluded_keywords` are always hard and never appear here |

**Validation rules**: at least one of `media_type`, `providers`, `genres`, `tone_descriptors`, `setting_descriptors`, `theme_descriptors`, `liked_titles` must be non-empty/non-null (an entirely empty profile cannot proceed to discovery — this is the "blocking clarification" case the Preference Agent's non-responsibility list still requires the Orchestrator to detect). `year_min <= year_max` when both are set.

## DiscoveryQuery

Derived by the Orchestrator from a `PreferenceProfile` plus retry state; consumed by the Discovery Agent (FR-007, FR-029). Excludes `additional_notes` and any free-text correction — that is the boundary that keeps the Discovery Agent out of intent *interpretation* (spec Key Entities; no model call anywhere in this agent, NFR-008). `tone_descriptors`/`setting_descriptors`/`theme_descriptors` all cross this boundary, as `vibe_keywords` (T087) — see that field's own row below for why this isn't "interpretation," and for the T089/T101 history of tone specifically being excluded and then deliberately folded back in for a different, now-safe reason.

| Field | Type | Notes |
|---|---|---|
| `media_type` | `MediaType` (resolved, not `either`) | Required — the Orchestrator resolves `either` into one query per attempt, or a merged strategy; see `contracts/discovery-agent.md` |
| `provider_names` | `list[str]` | Passed through from `PreferenceProfile.providers` |
| `region` | `str` | From configuration (FR-020), not from the user |
| `included_genres` / `excluded_genres` | `list[str]` | `excluded_genres` is never emptied by relaxation |
| `excluded_keywords` | `list[str]` | From `PreferenceProfile.excluded_keywords` (T091). Never emptied by relaxation, like `excluded_genres` — always hard |
| `vibe_keywords` | `list[str]` | From `PreferenceProfile.tone_descriptors + setting_descriptors + theme_descriptors` (T087; `tone_descriptors` excluded by T089, then folded back in by T101 once T100 gave resolution AND-first/OR-fallback semantics — tone can now only narrow a search anchored by a real theme/setting, never substitute for one via an ungated OR, and `RecommendationAgent`'s relevance floor still independently requires a genuine `theme_descriptors` match to be selectable whenever a theme was stated, regardless of how a candidate entered the pool). Resolved to TMDB keyword ids inside `RealTmdbClient.discover()` via `/search/keyword` — a deterministic external lookup, not model-based interpretation, so this doesn't reintroduce a model call into the Discovery Agent (NFR-008). Soft: an unresolved descriptor is dropped rather than failed closed. When 2+ ids resolve, AND semantics are tried first, falling back to OR only if AND finds nothing at all, entirely within one `discover()` call (T100) — a query-construction detail, not a disclosed relaxation. Emptied when `relaxed_constraint == tone`, alongside `included_genres`, for the same reason both exist as a proxy for "vibe precision" on the retry |
| `languages` | `list[str]` | From `PreferenceProfile.languages` (T104). Resolved to a single TMDB ISO 639-1 code inside `RealTmdbClient.discover()` via `/configuration/languages` — TMDB's `with_original_language` param, unlike `with_genres`/`with_keywords`/`with_companies`, accepts exactly one value (confirmed live, no comma/pipe support), so only the first name that resolves is used even though this field is a list. Soft: an unresolved name is dropped, not failed closed |
| `year_min` / `year_max` | `int \| None` | May be widened only when `relaxed_constraint == year_range` |
| `runtime_max_minutes` | `int \| None` | Applied server-side for movies; enforced as a post-filter for TV (see `contracts/discovery-agent.md`). May be widened only when `relaxed_constraint == runtime` |
| `season_count_max` | `int \| None` | TV-only hard constraint; TMDB has no server-side season-count filter, so — like TV runtime — it is enforced as a post-filter over detail-level data. Never widened by the retry: `excluded_genres`, `media_type`, and any hard-override field including this one stay identical across attempts |
| `similarity_seed_titles` | `list[str]` | Resolved from `PreferenceProfile.liked_titles` (title → TMDB id resolution happens inside the Discovery Agent, not in this contract) |
| `exclude_titles` | `list[str]` | From `PreferenceProfile.disliked_titles`, for exact-match exclusion at pool assembly |
| `relaxed_constraint` | `RelaxableConstraint \| None` | `None` on the initial attempt; set to exactly one value on the retry attempt |
| `retry_number` | `int` | `0` for the initial attempt, `1` for the (only allowed) retry — FR-011/NFR-007 |
| `result_limit` | `int` | Bounded page/result cap — NFR-003 |

**Validation rules**: `retry_number` ∈ {0, 1}. `relaxed_constraint` MUST be `None` when `retry_number == 0`, and MUST be set when `retry_number == 1`. `excluded_genres`, `excluded_keywords`, and `media_type` MUST be identical between the initial and retried query for the same session (hard constraints never change across attempts — FR-010).

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
| `vote_count` | `int \| None` | Confidence weight for `vote_average` (T108, FR-014): ranking uses a Bayesian-weighted rating (`_effective_rating`) that shrinks a thinly-voted score toward the catalog mean, so a 9.16 from 373 votes no longer outranks an 8.64 from 7,938. Present on TMDB's bulk list items, so not enrichment-gated. `None` = source didn't say, and the raw rating is used |
| `runtime_minutes` | `int \| None` | **Enrichment field** for display/ranking; populated for ranking-stage candidates per FR-029. When runtime is a *hard* TV constraint, this same detail data is fetched earlier, over the raw pool, purely to filter — see the Discovery Agent contract's hard-filter note |
| `season_count` | `int \| None` | TV-only. Same treatment as `runtime_minutes`: a display/ranking enrichment field normally, but fetched over the raw pool for hard filtering when `season_count_max` is a stated hard constraint (User Story 5) |
| `provider_names` | `list[str]` | **Enrichment field** — flatrate-only, configured region only (FR-019); populated only for candidates reaching ranking |
| `thematic_keywords` | `list[str]` | **Enrichment field** — populated only for candidates reaching ranking |
| `collection_id` | `int \| None` | **Enrichment field**, movie-only (TMDB collections have no TV equivalent) — TMDB `belongs_to_collection.id` (T105), already present on the base `/movie/{id}` response (no `append_to_response` needed). Consumer: `RecommendationAgent`'s dedup step (FR-016 — "the same title, or a direct sequel/prequel/alternate-cut"), since exact-title matching alone can't catch two differently-titled entries in the same franchise |

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

**`TmdbErrorInfo`** (nested type): `{ kind: Literal["timeout", "http_error", "malformed_response"], detail: str }`. `detail` is a short, developer-facing description (e.g., the HTTP status code or the validation failure) — it is never shown to the user directly; the Orchestrator turns it into the controlled, user-facing message (FR-027).

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
