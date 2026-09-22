# Architecture

Two diagrams: the static component/contract architecture, and the runtime
sequence for a single request, including both bounded retry paths (the
discovery zero-result retry and the independent LLM-call retry). See
`CLAUDE.md` and `specs/001-streaming-discovery-assistant/contracts/*.md`
for the full behavioral guarantees behind each box below.

## Component architecture

Four components hand off validated Pydantic contracts in a straight
pipeline. Only the Preference Agent and Recommendation Agent call a
language model; the Orchestrator and Discovery Agent are 100%
deterministic (constitution Principle II, spec NFR-008) — that boundary is
enforced, not incidental.

```mermaid
flowchart TB
    User(["Terminal user"])
    CLI["CLI (cli/intake.py, cli/output.py)"]

    subgraph Deterministic["Deterministic -- no model call"]
        Orchestrator["Orchestrator\n(session state, sequencing,\nretry decision, contract validation)"]
        Discovery["Discovery Agent\n(DiscoveryQuery -> CandidatePool)"]
    end

    subgraph ModelBacked["Model-backed"]
        Preference["Preference Agent\n(free text / intake -> PreferenceProfile)"]
        Recommendation["Recommendation Agent\n(profile + pool -> RecommendationPackage)"]
    end

    TMDB[("TMDB API\n(sole external data source)")]
    LLM[("Language model\nvia OpenRouter")]

    User <--> CLI
    CLI --> Orchestrator
    Orchestrator -- "raw text / intake answers" --> Preference
    Preference -- "PreferenceProfile" --> Orchestrator
    Preference <--> LLM
    Orchestrator -- "DiscoveryQuery" --> Discovery
    Discovery -- "CandidatePool" --> Orchestrator
    Discovery <--> TMDB
    Orchestrator -- "PreferenceProfile + CandidatePool" --> Recommendation
    Recommendation -- "RecommendationPackage" --> Orchestrator
    Recommendation <--> LLM
    Orchestrator -- "RecommendationPackage" --> CLI
```

Every arrow labeled with a contract name is a validated Pydantic model
(`src/streaming_discovery/contracts/`); a handoff that fails validation is
raised as a `ContractValidationError`, never coerced around.

## Sequence: one request, both retry paths

The two retries are bounded and independent of each other: **exactly one**
discovery retry (FR-011) with deterministic soft-constraint relaxation, and
**1–2** LLM-call retries (FR-028) on an outright model failure, wherever a
model is called.

```mermaid
sequenceDiagram
    actor User
    participant CLI
    participant Orchestrator
    participant PreferenceAgent as Preference Agent
    participant LLM as Language model
    participant DiscoveryAgent as Discovery Agent
    participant TMDB
    participant RecommendationAgent as Recommendation Agent

    User->>CLI: free text and/or guided intake answers
    CLI->>Orchestrator: run_single_attempt(...)

    Orchestrator->>PreferenceAgent: interpret_preferences(...)
    loop up to 1-2 additional attempts on outright failure (FR-028)
        PreferenceAgent->>LLM: generate(PreferenceProfile)
        LLM-->>PreferenceAgent: profile or ModelCallError
    end
    PreferenceAgent-->>Orchestrator: PreferenceProfile
    Orchestrator->>Orchestrator: validate_handoff(PreferenceProfile)

    Orchestrator->>User: confirm interpreted profile (FR-006)
    User-->>Orchestrator: accept, or correction

    Orchestrator->>Orchestrator: build_discovery_queries(retry_number=0)
    Orchestrator->>DiscoveryAgent: run(DiscoveryQuery)
    DiscoveryAgent->>TMDB: search / discover
    TMDB-->>DiscoveryAgent: raw results
    DiscoveryAgent-->>Orchestrator: CandidatePool
    Orchestrator->>Orchestrator: validate_handoff(CandidatePool)

    alt zero candidates and a soft constraint is eligible to relax
        Orchestrator->>Orchestrator: select_relaxation_constraint (tone -> runtime -> year_range)
        Note over Orchestrator: exactly one retry -- excluded_genres and any<br/>hard_override_fields entry are never relaxed (FR-010)
        Orchestrator->>Orchestrator: build_discovery_queries(retry_number=1, relaxed_constraint)
        Orchestrator->>DiscoveryAgent: run(DiscoveryQuery)
        DiscoveryAgent->>TMDB: search / discover (relaxed)
        TMDB-->>DiscoveryAgent: raw results
        DiscoveryAgent-->>Orchestrator: CandidatePool
    end

    alt still zero candidates after the allowed retry
        Orchestrator-->>CLI: RecommendationPackage(unresolved_notes=...)
    else at least one candidate
        Orchestrator->>RecommendationAgent: recommend(profile, pool)
        loop up to 1-2 additional attempts on outright failure (FR-028)
            RecommendationAgent->>LLM: generate(rationale per candidate)
            LLM-->>RecommendationAgent: rationale or ModelCallError
        end
        RecommendationAgent-->>Orchestrator: RecommendationPackage (Best Match / Safe Pick / Wildcard Pick)
        Orchestrator->>Orchestrator: validate_handoff(RecommendationPackage)
        Orchestrator-->>CLI: RecommendationPackage
    end

    CLI-->>User: three (or fewer) differentiated picks, never raw TMDB JSON
```

A TMDB adapter error at either discovery step short-circuits immediately
with a controlled `unresolved_notes` message (FR-027) rather than
continuing to the retry or to recommendation — not shown above as a
separate branch for clarity, but see `contracts/discovery-agent.md`.
