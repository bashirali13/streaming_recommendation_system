# Contract: Discovery Agent

**Boundary**: `DiscoveryQuery` (from the Orchestrator) → Discovery Agent → `CandidatePool` (consumed by the Orchestrator and Recommendation Agent).

## Consumes

`DiscoveryQuery` — see `data-model.md`. Never receives `PreferenceProfile` directly, and never receives `additional_notes` or any free-text correction — that exclusion is what keeps this agent out of intent *interpretation* (no model call anywhere in this agent, NFR-008). `setting_descriptors`/`theme_descriptors` **do** cross this boundary, as `vibe_keywords` — literal search terms resolved against TMDB's own keyword search. `tone_descriptors` (mood words) deliberately do **not** (T111): TMDB's keyword tagging is too sparse for them, and requiring them turned ordinary requests into zero results. Mood is a ranking signal in the Recommendation Agent.


## Produces

`CandidatePool` — see `data-model.md`.

## Behavioral guarantees (map to spec requirements)

- MUST apply every field on the incoming `DiscoveryQuery` as a filter; `included_genres`/`excluded_genres`/`excluded_keywords`/`media_type`/`provider_names` are never optional to honor, regardless of `retry_number` (FR-009, FR-010).
- MUST resolve `languages` to TMDB's `with_original_language` param via `/configuration/languages` (T104) when at least one stated language resolves. Unlike every other resolved list field on this contract, TMDB accepts only a single value here (confirmed live: `with_original_language=ko,ja` matches nothing, unlike the comma/pipe semantics `with_genres`/`with_keywords`/`with_companies` all support), so only the first name that resolves is ever sent, even though `languages` is a list. Soft, like `vibe_keywords`: an unresolved name is dropped, not failed closed.
- MUST express genre, year-range, provider, (for movies) runtime, and `vibe_keywords` (setting/theme) filtering as TMDB query parameters rather than fetching an unfiltered pool and filtering client-side (FR-029). `vibe_keywords` resolution (descriptor phrase → TMDB keyword id, via `/search/keyword`, falling back to a per-word search on a phrase miss) is soft: an unresolved descriptor is dropped. The agent MUST narrow first — every resolved id required (AND), then any (OR) — and accept the first attempt that leaves at least 10 results; otherwise it MUST drop the keyword filter and return the wide pool with the narrow matches kept at the front (T100, T111). A keyword may put the best matches first but MUST NOT leave the user with a handful of results, or none. This happens entirely inside one `discover()` call: it is a query-construction detail, not a disclosed relaxation, and never consumes the Orchestrator's one bounded retry (FR-011).
- MUST express `excluded_keywords` (T091 — a franchise/studio/etc. exclusion that doesn't fit `excluded_genres`) as `without_keywords`, resolved the same way as `vibe_keywords`. Unlike `vibe_keywords`, this is hard: since TMDB's own keyword tagging isn't guaranteed complete for every excluded concept, a phrase that resolves to no TMDB keyword id doesn't get to silently drop the exclusion — the agent MUST also reject a bulk candidate whose title/overview literally mentions an excluded term, before spending a detail() call on it, as a second enforcement layer that doesn't depend on TMDB's own tagging (FR-010). For a franchise/studio exclusion specifically, neither of those is reliable on its own — confirmed empirically against real TMDB data, "Spider-Man: Into the Spider-Verse"'s real overview and real keyword tags (`["superhero", "based on comic", "aftercreditsstinger", "alternate universe"]`) never mention "Marvel" at all, while its real `production_companies` field does include "Marvel Entertainment" — so the agent MUST also reject a candidate, after the detail() call, whose `production_companies` names mention an excluded term (T095), the one TMDB field reliably populated with the actual studio/publisher name.
- MUST resolve `excluded_keywords` against `/search/person` (`resolve_person_ids`) and reject any finalist candidate whose `credits` (cast or crew) includes a resolved person (T107) — an actor or director exclusion (e.g. "nothing with Jason Statham") has no `discover()`-time equivalent at all: TMDB's `/discover` endpoints have no `without_people`/`without_cast`/`without_crew` parameter (confirmed live), unlike genres/keywords/companies, which all support a `without_*` param. This is therefore the *only* enforcement layer for a person exclusion, not an additional one on top of a query-param filter — evaluated after the detail() call (`credits` requires `append_to_response=credits`, added to every `details()` call so this costs no extra request beyond what T095 already needed for `production_companies`), the same place `_mentions_excluded_company` runs.
- MUST NOT fetch detail-level data (TV runtime, provider lists, thematic keywords) for the full raw candidate pool — only for candidates that pass hard filtering and are being handed to the Recommendation Agent for ranking (FR-029). **Exception**: TMDB has no server-side query parameter for TV runtime or TV season count, so when either is a *hard* constraint (runtime via `hard_override_fields`, season count via `season_count_max`, which is always hard when set), the detail call needed to evaluate that hard filter MUST happen over the raw pool before hard filtering — there is no way to apply a TV hard filter without it. This exception does not extend to provider lists or thematic keywords, which remain finalist-only regardless of media type.
- MUST send `with_watch_monetization_types=flatrate` whenever `provider_names` are given (T109). `with_watch_providers` alone matches any offer type (rent, buy, free, ads), so a title only rentable on a named service would pass the discover-time filter yet be dropped by the flatrate-only scoping below, arriving with no "Available on" line. Confirmed live that the parameter changes results.
- MUST express a requested genre in TV terms when querying TV (T113): TMDB's TV genres are a smaller list, so Science Fiction/Fantasy, Action/Adventure and War map to their combined TV genres, and Romance, Horror, Thriller, History and Music (which TV lacks) map to an exact-name keyword. A requested genre MUST NOT be silently dropped.
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
