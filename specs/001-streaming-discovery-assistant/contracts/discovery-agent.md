# Contract: Discovery Agent

**Boundary**: `DiscoveryQuery` (from the Orchestrator) → Discovery Agent → `CandidatePool` (consumed by the Orchestrator and Recommendation Agent).

## Consumes

`DiscoveryQuery` — see `data-model.md`. Never receives `PreferenceProfile` directly, and never receives `additional_notes`, any free-text correction, or `tone_descriptors` — that exclusion is what keeps this agent out of intent *interpretation* (outline non-responsibility: "Interpret ambiguous user intent"; no model call anywhere in this agent, NFR-008). `tone` is excluded even from `vibe_keywords` because it's a fuzzy/subjective mood signal, not the concrete subject matter TMDB's own keyword catalog is built around — T089 narrowed T087's original scope after a live run where OR-ing a noisy tone-keyword match in let a thematically unrelated candidate into the pool. `setting_descriptors`/`theme_descriptors` **do** cross this boundary, as `vibe_keywords` (T087, revising this contract's original stance) — not as interpretation, but as literal search terms resolved against TMDB's own keyword search, the same class of deterministic TMDB-server-side filtering already required for genre/provider/runtime (FR-029). Without this, a request with only theme/setting signals and no genre or liked titles has nothing left to filter discovery by, and TMDB's default popularity-sorted pool has no relationship to the request at all.

## Produces

`CandidatePool` — see `data-model.md`.

## Behavioral guarantees (map to spec requirements)

- MUST apply every field on the incoming `DiscoveryQuery` as a filter; `included_genres`/`excluded_genres`/`excluded_keywords`/`media_type`/`provider_names` are never optional to honor, regardless of `retry_number` (FR-009, FR-010).
- MUST express genre, year-range, provider, (for movies) runtime, and `vibe_keywords` (setting/theme only — T089) filtering as TMDB query parameters rather than fetching an unfiltered pool and filtering client-side (FR-029). `vibe_keywords` resolution (descriptor phrase → TMDB keyword id, via `/search/keyword`, falling back to a per-word search on a phrase miss) is soft: an unresolved descriptor is dropped, not sent through as noise and not treated as a failed hard constraint, since `setting`/`theme` stay soft signals (data-model.md) even once they reach this agent.
- MUST express `excluded_keywords` (T091 — a franchise/studio/etc. exclusion that doesn't fit `excluded_genres`) as `without_keywords`, resolved the same way as `vibe_keywords`. Unlike `vibe_keywords`, this is hard: since TMDB's own keyword tagging isn't guaranteed complete for every excluded concept, a phrase that resolves to no TMDB keyword id doesn't get to silently drop the exclusion — the agent MUST also reject a bulk candidate whose title/overview literally mentions an excluded term, before spending a detail() call on it, as a second enforcement layer that doesn't depend on TMDB's own tagging (FR-010). For a franchise/studio exclusion specifically, neither of those is reliable on its own — confirmed empirically against real TMDB data, "Spider-Man: Into the Spider-Verse"'s real overview and real keyword tags (`["superhero", "based on comic", "aftercreditsstinger", "alternate universe"]`) never mention "Marvel" at all, while its real `production_companies` field does include "Marvel Entertainment" — so the agent MUST also reject a candidate, after the detail() call, whose `production_companies` names mention an excluded term (T095), the one TMDB field reliably populated with the actual studio/publisher name.
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
