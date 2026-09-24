# Contract: Orchestrator

**Boundary**: Terminal user ↔ Orchestrator ↔ {Preference, Discovery, Recommendation} agents. The Orchestrator is the only component with visibility into the whole session; it is a deterministic component (NFR-008) — it does not itself call a language model.

## Consumes

`UserSessionState` (owns and mutates it across the session) plus each worker agent's output, validated against that agent's contract before use (FR-022).

## Produces

The final `RecommendationPackage`, plus whatever terminal-facing text summarizes it. Internally, its retry decision is a plain boolean derived from `len(candidate_pool.candidates)` and `candidate_pool.error` — this project does not define a separate `WorkflowDecision` contract type, since the decision has exactly two deterministic inputs and one bounded consequence (data-model.md's state-transition diagram is the authoritative description of this logic, not a passed object).

## Behavioral guarantees (map to spec requirements)

- MUST run the optional guided intake and/or accept free-text input, preserving blank answers as `None` rather than defaulting them (FR-002, FR-003).
- MUST invoke the Preference Agent, present the resulting profile to the user, and allow correction before invoking the Discovery Agent (FR-006).
- MUST validate every agent's output against its contract before passing it to the next agent; an invalid handoff is a controlled failure, never silently coerced (FR-022).
- MUST invoke the Discovery Agent with `retry_number=0` first. If `candidate_pool.error` is set, MUST stop and report a controlled TMDB failure (FR-027) without attempting a retry. If `candidate_pool.candidates` is empty and no error is set, MUST invoke the Discovery Agent exactly once more with `retry_number=1` and `relaxed_constraint` set to the next value in the fixed priority order (runtime → year_range; never genre, never mood -- T111) that is actually present on the profile (FR-011).
- MUST NOT relax `excluded_genres`, `media_type`, or any field listed in `hard_override_fields` under any circumstance, including on the retry (FR-010).
- MUST stop after the retry's result (success or empty) — never a second retry (FR-012, NFR-007).
- MUST disclose `relaxed_constraint` in the final output whenever it is not `None` (FR-013).
- MUST NOT invoke the Recommendation Agent when the (initial or retried) `candidate_pool.error` is set — a TMDB failure ends the session at the controlled-failure state, not at ranking.
- MUST assemble the final `RecommendationPackage` from the Recommendation Agent's output and present it without ever surfacing a raw TMDB payload or raw inter-agent JSON (FR-008, FR-021).
- MUST offer the optional export (FR-024) after presenting the final result.

## Failure modes

| Condition | Required behavior |
|---|---|
| Any agent's output fails contract validation | Controlled failure; session ends with an explanation, not a crash or a silently-repaired payload |
| `candidate_pool.error` set (initial or retry attempt) | Controlled failure message naming TMDB unavailability; no further retry of either kind is attempted |
| Both discovery attempts return zero candidates, no error | `unresolved_notes` explains which constraints could not be satisfied; session ends normally (not an error state) |
| Fewer than 3 but more than 0 qualifying candidates after the final attempt | Session ends normally with a partial `RecommendationPackage` (Best Match, and Safe Pick if available) — this is success, not a degraded/error path (FR-015, SC-008) |

## Non-responsibilities (explicit)

Does not interpret taste itself, does not call TMDB directly, does not rank or invent candidates, does not silently relax a hard constraint, does not attempt more than one discovery retry.
