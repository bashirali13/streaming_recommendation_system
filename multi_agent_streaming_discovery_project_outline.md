# Multi-Agent Streaming Discovery Assistant

*Project outline for a contract-driven movie and TV recommendation system*

> **Design intent**  
> Demonstrate multi-agent orchestration, structured JSON handoffs, tool calling, bounded retry behavior, SDD, and TDD without RAG, vector storage, open-ended research, or citation-heavy output.

# Summary

A terminal-based streaming discovery assistant that helps users choose a movie or TV show from vague moods, specific constraints, or a combination of both. The system guides the user through an optional intake, translates natural-language preferences into structured data, retrieves candidates from TMDB, ranks candidate fit, and returns three distinct recommendations.

The project is recommendation-oriented rather than fact-oriented. TMDB supplies structured candidate metadata; specialized agents collaborate to interpret taste, discover content, rank fit, and curate a concise response.

# Goal

- Accept vague requests such as “dark, moody, Eastern European vibes.”
- Accept specific requests such as “Netflix or Hulu, movie, after 2010, powerful female lead, not superhero.”
- Guide users with optional terminal prompts while allowing unknown fields to remain blank.
- Return a Best Match, Safe Pick, and Wildcard Pick rather than an oversized list.
- Use TMDB as the primary external tool for movie, TV, metadata, similar-title, and provider discovery.
- Demonstrate visible agent collaboration through typed JSON contracts and deterministic orchestration.
- Use acceptance criteria based on agents and planned functionality used to drive tests before implementation through SpecKit and TDD.
- Stretch goal: Front-end

# Scope and Constraints

> **Entry assumption**  
> The user intends to find something to watch. The assistant is not a general film research system, review aggregator, or factual question-answering tool.

- MVP supports movies, TV series, or either.
- MVP returns exactly three primary recommendation roles when enough candidates exist.
- No web scraping, RAG, vector database, or SQLite persistence is required.
- TMDB is the only required live external data source.
- Session state is held in memory and may optionally export JSON or Markdown.
- Provider availability is presented from TMDB data when available and should not be treated as a guaranteed current subscription listing.
- Maximum one broadened discovery retry after zero candidates.
- Raw TMDB payloads are never shown directly to the user.

# Terminal Conversation Flow

The terminal provides lightweight guidance without forcing a full questionnaire. All questions are optional unless a missing value blocks discovery.

| Step | Prompt focus |
|----|----|
| 1\. Format | Movie, TV show, or either? |
| 2\. Services | Which streaming services should be considered? |
| 3\. Mood and interests | What mood, genre, style, setting, or “vibe” are you looking for? |
| 4\. Exclusions | Anything to avoid, such as genres, themes, or franchises? |
| 5\. Optional constraints | Release year, runtime, language, recent favorites, disliked titles, or additional notes. |
| 6\. Confirmation | Summarize the interpreted Preference Profile and allow corrections before discovery. |

> **Prompting rule**  
> Ask only for information that improves the next decision. Blank answers remain unspecified rather than being replaced with invented preferences.

# Project Architecture

**Terminal User → Orchestrator → Preference Agent → Discovery Agent → Recommendation Agent → Terminal User**

All inter-agent communication uses validated Pydantic models serialized as JSON. Agents do not pass unstructured essays to one another.

## Orchestrator Agent

**Purpose:** Owns session state, workflow routing, retries, and final assembly.

| Responsible for | Not responsible for |
|----|----|
| • Run optional intake and preserve user answers | • Interpret taste itself |
| • Determine when preferences are sufficient for discovery | • Call TMDB directly |
| • Invoke worker agents in the required order | • Rank or invent candidates |
| • Validate each handoff against its schema | • Silently relax hard constraints |
| • Detect zero-result discovery and apply one bounded retry |  |
| • Stop and expose unresolved constraints after the retry |  |
| • Return the RecommendationPackage to the user |  |

**Contract:** Consumes UserSessionState and agent results; produces WorkflowDecision and final RecommendationPackage.

## Preference Agent

**Purpose:** Translates natural language and intake answers into a structured PreferenceProfile.

| Responsible for | Not responsible for |
|----|----|
| • Extract format, services, genres, tone, setting, themes, language, year, runtime, likes, dislikes, and exclusions | • Call TMDB |
| • Separate hard constraints from soft preferences | • Recommend titles |
| • Preserve ambiguity instead of over-interpreting it | • Relax constraints |
| • Identify one blocking clarification when required | • Score candidates |

**Contract:** Consumes raw user request and intake answers; produces PreferenceProfile.

## Discovery Agent

**Purpose:** Uses TMDB to produce a bounded candidate pool.

| Responsible for | Not responsible for |
|----|----|
| • Map structured preferences to supported TMDB queries | • Interpret ambiguous user intent |
| • Search or discover movies and TV shows | • Rank personal fit |
| • Retrieve selected additional details and watch-provider data | • Write final recommendations |
| • Normalize TMDB payloads into CandidateMedia objects | • Perform general web search or scraping |
| • Return an explicit zero-results status when no candidate qualifies |  |

**Contract:** Consumes DiscoveryQuery; produces CandidatePool with normalized TMDB metadata and query metadata.

## Recommendation Agent

**Purpose:** Scores, ranks, and packages discovered candidates into the final recommendation set.

| Responsible for | Not responsible for |
|----|----|
| • Apply hard filters before scoring | • Call TMDB |
| • Score soft preference fit | • Change the PreferenceProfile |
| • Explain key match and mismatch factors | • Fabricate facts absent from candidate data |
| • Select Best Match, Safe Pick, and Wildcard Pick | • Run open-ended fact checking |
| • Avoid duplicate or near-identical choices | • Return long lists or raw JSON |
| • Write concise user-facing rationales |  |
| • Include major caveats and provider information when present |  |
| • Reduce confidence when evidence for subjective traits is weak |  |

**Contract:** Consumes PreferenceProfile and CandidatePool; produces RecommendationPackage.

# Core Structured Contracts

| Contract | Key fields |
|----|----|
| PreferenceProfile | media_type, providers, genres, excluded_genres, tones, settings, themes, languages, year_min/year_max, runtime_max, liked_titles, disliked_titles, hard_constraints, soft_preferences |
| DiscoveryQuery | TMDB endpoint strategy, filters, provider region, page/result limit, relaxed_constraint, retry_number |
| CandidateMedia | tmdb_id, media_type, title, overview, genre_ids/genres, release date, vote average, popularity, language, runtime when retrieved, provider metadata, source status |
| CandidatePool | query metadata, candidates, total_results, retry_required, errors |
| RecommendationPackage | best_match, safe_pick, wildcard_pick, applied_constraints, relaxed_constraints, unresolved_notes |

# TMDB Integration

TMDB returns structured JSON. The Discovery Agent should normalize only the fields required by downstream contracts instead of coupling the full application to raw responses.

- Candidate discovery may use search, discover, similar-title, details, genre, and watch-provider endpoints as appropriate.
- Common list results contain identifiers, titles or names, overviews, genre identifiers, release or first-air dates, language, popularity, vote data, and poster paths.
- Additional detail calls may be used only when needed for constraints such as runtime.
- Provider lookups should use a configured region and retain provider metadata with the candidate.
- All network access is isolated behind a TMDB client adapter with timeouts, pagination limits, and controlled error responses.
- Tests use TMDB fixtures and fake clients, not live requests.

# Zero-Result Retry Policy

The retry is a visible orchestration feature, not an unlimited search loop.

- Initial discovery applies all hard constraints and supported soft filters.
- If zero candidates are returned, the Orchestrator selects one pre-approved soft constraint to relax.
- Preferred relaxation order: subjective vibe precision, runtime maximum, then release-year range. Explicit exclusions, media type, and user-designated hard constraints are not relaxed.
- The Orchestrator records the relaxed field and invokes the Discovery Agent once more.
- If the retry also returns zero candidates, the system stops and explains which constraints prevented a match.
- Any relaxed constraint is displayed in the final recommendation package.

# SDD and TDD Approach

SpecKit is used to define the feature specification, clarify requirements, create the implementation plan, and break work into testable stories. Acceptance criteria and definition of done are written before implementation. Each story follows red, green, refactor.

- Vision and scope: problem statement, user value, constraints, and non-goals.
- Agent contracts: typed inputs, outputs, responsibilities, non-responsibilities, and failure states.
- Domain model: session state, preferences, discovery query, candidates, ranking, and final package.
- ADRs: TMDB adapter strategy, LLM provider/model choice, retry policy, scoring approach, and in-memory state.
- Tests are written before production code for orchestrator routing, contracts, filtering, ranking, retry behavior, and terminal interaction.
- LLM outputs are schema-validated; deterministic code owns hard filters, field validation, retry limits, and result-count rules.

## Acceptance Criteria Themes

- Vague and specific requests both produce a valid PreferenceProfile.
- Blank optional intake answers remain null or empty.
- Hard exclusions are never silently relaxed.
- Discovery returns normalized CandidateMedia objects rather than raw TMDB records.
- Zero initial candidates trigger exactly one broader retry.
- The broader retry records which soft constraint changed.
- If the retry fails, the workflow terminates without looping.
- Ranking applies hard filters before soft scoring.
- The Recommendation Agent returns Best Match, Safe Pick, and Wildcard Pick with distinct titles when enough candidates exist.
- TMDB errors and malformed LLM output produce controlled failures.
- All inter-agent handoffs validate against their Pydantic contracts.

## Definition of Done

- Each story has acceptance criteria before implementation.
- Unit, contract, integration, end-to-end, and adversarial tests pass.
- TMDB access is isolated behind a tested adapter and mocked in automated tests.
- A fixture-backed demo runs without API or model credentials.
- Agent responsibilities and non-responsibilities are documented and enforced.
- The retry path and no-match path are demonstrated.
- Output is concise, contains no raw JSON, and identifies relaxed constraints.
- Specs, architecture diagram, README, prompt examples, and Claude.md are complete.

# Test Strategy

| Test layer | Coverage |
|----|----|
| Unit | Preference parsing helpers, hard filters, scoring rules, relaxation policy, uniqueness rules. |
| Contract | Valid and invalid Pydantic payloads for every agent handoff. |
| TMDB adapter | Success, pagination, empty result, timeout, HTTP error, malformed response, and provider-region fixtures. |
| Integration | Orchestrator sequencing, zero-result retry, downstream contract passing, and controlled failure. |
| End-to-end | Vague request, specific request, streaming-filter request, one-retry success, and one-retry failure. |
| Adversarial | Conflicting constraints, unsupported vibe language, prompt injection in user text or TMDB overview, duplicate candidates, and malformed LLM output. |

# Potential Tech Stack

- Python 3.11+, VS Code, Claude Code CLI, and Git.
- SpecKit for SDD.
- PydanticAI as the initial multi-agent framework candidate.
- DeepSeek v4 Flash 0731 through OpenRouter.
- TMDB API through a small async or synchronous Python client adapter.
- Pydantic for schemas and validation.
- pytest for TDD, fixtures, fake clients, and adversarial tests.
- In-memory session state; optional JSON or Markdown export.
- Structured logs for agent calls, TMDB calls, retries, validation failures, latency, and token use.

# Recommended MVP

- One Orchestrator and three worker agents: Preference, Discovery, and Recommendation.
- Guided but optional terminal intake.
- Movie, TV, or either.
- TMDB candidate discovery and optional provider filtering for one configured region.
- Three recommendation roles only.
- One zero-result retry with deterministic relaxation policy.
- Pydantic JSON contracts for every handoff.
- Fixture-backed deterministic demo mode.
- No persistence, RAG, vector database, scraping, or generic web search.

# Expected User Prompts

**Vague mood:** “Dark, moody, Eastern European vibes.”

**Specific constraints:** “I have Netflix and Hulu. I want a movie after 2010 with a powerful female lead that is not a superhero movie.”

**Similarity:** “I loved Arrival, Ex Machina, and Severance. Give me something thoughtful but not extremely bleak.”

**Runtime:** “I need something funny under 100 minutes for tonight.”

**Exclusions:** “Recommend a mystery series, but no police procedurals and nothing with more than three seasons.”

**Open discovery:** “I do not know what I want. Ask me a few questions and help me choose.”

# Good Demo Scenario

The user selects Movie, identifies Netflix and Hulu, and enters: “After 2010, powerful female lead, tense but not horror, and no superhero movies.” The Preference Agent creates a structured profile. The Discovery Agent returns zero exact matches under an additional short-runtime preference. The Orchestrator removes only the soft runtime preference and retries once. The Recommendation Agent ranks the resulting candidates and returns Best Match, Safe Pick, and Wildcard Pick while identifying the relaxed runtime constraint.

This demonstrates guided intake, TMDB tool use, structured contracts, agent handoffs, deterministic filtering, bounded retry, ranking, curation, and concise output.

# Risks and Controls

| Risk | Control |
|----|----|
| Overlapping agents | Use explicit contracts and non-responsibilities. |
| LLM inconsistency | Validate schemas and keep hard filtering/retry logic deterministic. |
| TMDB outage or limit response | Use timeouts, controlled errors, fixtures, and bounded calls. |
| Subjective-vibe mismatch | Represent vibe as soft preferences and lower confidence when metadata is weak. |
| Provider data uncertainty | Display provider region/source status and avoid guarantees. |
| Output bloat | Always return three recommendation roles, not a large list. |
| Artificial complexity | Do not add databases, RAG, scraping, or agents without an acceptance criterion. |

# Required Artifacts

- SpecKit specifications, plan, and tasks.
- Architecture and sequence diagrams.
- Agent contracts and Pydantic domain models.
- Unit tests (happy path and adversarial)
- Examples of prompts which demonstrate both your thought process as well as rationale for decisions (this might look like pushing back, or it might be asking clarification, want to see how you approached the solution) 
- README
- Claude.md with TDD rules, contract boundaries, and implementation guidance.

# Guiding Principles

- Keep the project simple but intentional.
- Agents build on validated structured outputs rather than free-form prose.
- TMDB supplies candidate data; agents supply interpretation, ranking, and curation.
- Use the LLM for ambiguous preference interpretation and rationale; use deterministic code for invariants.
- Never silently relax a hard constraint.
- One API and a strong orchestration design are sufficient for the MVP.
- The system succeeds by producing useful recommendations and demonstrating disciplined engineering, not by finding an objectively correct answer.
- SDD and TDD should drive development. No implementation until acceptance criteria is decided and test cases are built from those.

> **First implementation slice**  
> Process one specific movie request into a PreferenceProfile, retrieve fixture-backed candidates, filter and rank them, and return three curated picks. Then add live TMDB, guided intake, and the zero-result retry as separate TDD stories.
