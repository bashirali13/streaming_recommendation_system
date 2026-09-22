# Contract: Preference Agent

**Boundary**: Terminal user input / guided-intake answers → Preference Agent → `PreferenceProfile` (consumed by the Orchestrator and Recommendation Agent).

## Consumes

- `raw_user_input: str | None` — free-text request, if the user provided one.
- `intake_answers: dict[str, str | None]` — guided-intake answers, any of which may be `None`/blank.

At least one of the two MUST be non-empty; the Orchestrator does not invoke this agent with both empty (spec FR-001).

## Produces

`PreferenceProfile` — see `data-model.md`.

## Behavioral guarantees (map to spec requirements)

- MUST NOT invent a value for any field neither the free text nor the intake answers addressed; unspecified stays `None`/empty (FR-003).
- MUST classify every populated field as hard or soft using the fixed default classification in `data-model.md` (`media_type`, `excluded_genres`, `providers` = hard by default; everything else = soft by default), except where the user's own language marks an otherwise-soft field non-negotiable, in which case that field name is added to `hard_override_fields` (FR-005).
- MUST NOT call TMDB or any external data source (outline: Preference Agent non-responsibilities).
- MUST NOT recommend or rank titles (outline: Preference Agent non-responsibilities).
- MUST NOT resolve an internally conflicting request (e.g., excluding a genre while naming a liked title in that genre) on its own; it surfaces the conflict for the Orchestrator/user rather than silently picking a side (spec Edge Cases).

## Failure modes

| Condition | Required behavior |
|---|---|
| Output fails `PreferenceProfile` schema validation | Treated as a controlled failure at the Orchestrator boundary (FR-022) — never passed downstream unvalidated |
| Underlying model call fails outright (timeout/outage/rate limit) | Retried 1–2 times by the calling code, then a controlled user-visible error (FR-028) — this agent's contract does not change; the retry wraps the call, it does not alter what this agent consumes/produces |
| Resulting profile has no field populated at all | Orchestrator treats this as a blocking clarification case, not a valid handoff |

## Non-responsibilities (explicit)

Does not call TMDB, does not rank or recommend, does not relax any constraint, does not score candidate fit.
