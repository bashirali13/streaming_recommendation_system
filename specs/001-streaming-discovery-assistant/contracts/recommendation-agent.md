# Contract: Recommendation Agent

**Boundary**: `PreferenceProfile` + `CandidatePool` → Recommendation Agent → `RecommendationPackage` (consumed by the Orchestrator for final assembly/export).

## Consumes

- `preference_profile: PreferenceProfile` — for soft-preference fit scoring and rationale content; also re-applies hard fields as a safety-net filter (defense in depth, not the primary enforcement point).
- `candidate_pool: CandidatePool` — the candidates to rank; if `candidate_pool.error` is set, the Orchestrator does not invoke this agent at all (a TMDB failure short-circuits before ranking).

## Produces

`RecommendationPackage` — see `data-model.md`.

## Behavioral guarantees (map to spec requirements)

- MUST re-apply all hard filters (format, excluded genres, `excluded_keywords`, any `hard_override_fields`) before any soft scoring, even though the Discovery Agent already filtered — this is the ranking-side half of FR-009, protecting against a validation gap upstream rather than duplicating trust in it. For `excluded_keywords` specifically (T091), this re-check also covers `thematic_keywords` — enrichment data this agent is the first to see, so it can catch an exclusion the Discovery Agent's own (title/overview-only, pre-enrichment) check couldn't.
- MUST include `additional_notes` (T090) in the context given to the rationale-writing model call, and flag plainly if a stated exclusion in it conflicts with the candidate — even once `excluded_keywords`/`excluded_genres` give it real structured enforcement, `additional_notes` remains a catch-all for anything a user says that doesn't fit a structured field, and the model should never write a rationale blind to it.
- MUST score remaining candidates against soft preferences (tone/setting/theme descriptors, liked/disliked titles, recency) and produce a ranked order (FR-014).
- MUST fill roles in priority order — Best Match first, then Safe Pick, then Wildcard Pick — populating only as many as there are distinct, non-duplicate qualifying candidates; MUST NOT duplicate a candidate across roles or accept a near-duplicate to fill an empty role (FR-015, FR-016, SC-008).
- MUST write a concise, human-readable rationale per filled role naming key matching and mismatching factors (FR-017).
- MUST attach a `confidence_note` when the evidence for a subjective trait is weak, ambiguous, or absent from the candidate's `overview`/`thematic_keywords` (FR-018).
- MUST include `provider_names` in the rationale/output when present on the candidate, and MUST NOT phrase it as a live-availability guarantee (FR-019).
- MUST NOT alter the incoming `PreferenceProfile` (outline non-responsibility) — any hard-override or relaxation state is read-only here.
- MUST NOT call TMDB (outline non-responsibility) — any enrichment field it needs (runtime, providers, keywords) must already be present on the `CandidateMedia` objects it receives, per the Discovery Agent's finalist-enrichment responsibility.
- MUST NOT fabricate a fact about a candidate that isn't present in its `CandidateMedia` data (outline non-responsibility: "no open-ended fact checking").

## Failure modes

| Condition | Required behavior |
|---|---|
| Output fails `RecommendationPackage` schema validation | Controlled failure at the Orchestrator boundary (FR-022) |
| Underlying model call fails outright | Retried 1–2 times by the calling code, then a controlled error (FR-028) |
| Zero qualifying candidates after hard re-filtering | All three role fields are `None`; `unresolved_notes` explains which constraints blocked a match (FR-012) — this is a valid, schema-conformant output, not an error |

## Non-responsibilities (explicit)

Does not call TMDB, does not modify the PreferenceProfile, does not run open-ended fact-checking, does not return more than three roles or raw candidate data.
