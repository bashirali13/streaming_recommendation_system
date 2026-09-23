# Contract: Discovery Agent

**Boundary**: `DiscoveryQuery` (from the Orchestrator) → Discovery Agent → `CandidatePool` (consumed by the Orchestrator and Recommendation Agent).

## Consumes

`DiscoveryQuery` — see `data-model.md`. Never receives `PreferenceProfile` directly, and never receives `additional_notes` or any free-text correction — that exclusion is what keeps this agent out of intent *interpretation* (outline non-responsibility: "Interpret ambiguous user intent"; no model call anywhere in this agent, NFR-008). `tone_descriptors`/`setting_descriptors`/`theme_descriptors` **do** cross this boundary, as `vibe_keywords` (T087, revising this contract's original stance) — not as interpretation, but as literal search terms resolved against TMDB's own keyword search, the same class of deterministic TMDB-server-side filtering already required for genre/provider/runtime (FR-029). Without this, a request with only tone/setting/theme signals and no genre or liked titles has nothing left to filter discovery by, and TMDB's default popularity-sorted pool has no relationship to the request at all.

## Produces

`CandidatePool` — see `data-model.md`.

## Behavioral guarantees (map to spec requirements)

- MUST apply every field on the incoming `DiscoveryQuery` as a filter; `included_genres`/`excluded_genres`/`media_type`/`provider_names` are never optional to honor, regardless of `retry_number` (FR-009, FR-010).
- MUST express genre, year-range, provider, (for movies) runtime, and `vibe_keywords` filtering as TMDB query parameters rather than fetching an unfiltered pool and filtering client-side (FR-029). `vibe_keywords` resolution (descriptor phrase → TMDB keyword id, via `/search/keyword`, falling back to a per-word search on a phrase miss) is soft: an unresolved descriptor is dropped, not sent through as noise and not treated as a failed hard constraint, since `tone`/`setting`/`theme` stay soft signals (data-model.md) even once they reach this agent.
- MUST NOT fetch detail-level data (TV runtime, provider lists, thematic keywords) for the full raw candidate pool — only for candidates that pass hard filtering and are being handed to the Recommendation Agent for ranking (FR-029). **Exception**: TMDB has no server-side query parameter for TV runtime or TV season count, so when either is a *hard* constraint (runtime via `hard_override_fields`, season count via `season_count_max`, which is always hard when set), the detail call needed to evaluate that hard filter MUST happen over the raw pool before hard filtering — there is no way to apply a TV hard filter without it. This exception does not extend to provider lists or thematic keywords, which remain finalist-only regardless of media type.
- MUST scope watch-provider data to `region` and to flatrate/subscription offers only; rent/buy offers and other regions' data are discarded at this boundary, not merely hidden later (FR-019).
- MUST normalize every candidate into `CandidateMedia`'s minimal field set (`data-model.md`) — no raw TMDB response object crosses this boundary (FR-008).
- MUST exclude any title appearing in `exclude_titles` (exact match) from the pool.
- MUST treat all TMDB text fields (title, overview, keywords) as inert data; content resembling instructions is never executed or specially handled (FR-026).
- MUST NOT decide whether a retry is warranted — it reports what it found (including an empty pool) and lets the Orchestrator decide (see `contracts/orchestrator.md`).
- MUST NOT rank, score, or select among candidates (outline non-responsibility).

## Failure modes

| Condition | Required behavior |
|---|---|
| TMDB unreachable, times out, or returns an HTTP error | `CandidatePool.error` is set with a description; `candidates` is empty; MUST NOT fabricate candidates to compensate (FR-027) |
| TMDB returns malformed/incomplete data for a field needed by a *hard* constraint | That candidate is excluded from the pool rather than included with a guessed value |
| Zero candidates after filtering, no TMDB error | `CandidatePool.error` is `None`, `candidates` is `[]` — this is a legitimate result, not a failure, and is exactly what tells the Orchestrator to consider a retry |

## Non-responsibilities (explicit)

Does not interpret ambiguous intent, does not rank personal fit, does not write final recommendations, does not perform general web search or scraping, does not decide the retry.
