# CLAUDE.md

Guidance for Claude Code (or any contributor) implementing this repository. This file tells you **how** to build; it does not restate **what** to build or **why** — those live in `specs/001-streaming-discovery-assistant/` and `.specify/memory/constitution.md`. If anything here ever conflicts with the constitution, the constitution wins; fix this file, not the other way around.

## Start here

- **Principles**: `.specify/memory/constitution.md` (v1.0.0, 7 principles). Read it before writing code. This file only adds operational detail on top of it.
- **What's being built and why**: `specs/001-streaming-discovery-assistant/spec.md`.
- **How it's built**: `specs/001-streaming-discovery-assistant/plan.md`, `research.md`, `data-model.md`, `contracts/*.md`.
- **What to do, in what order**: `specs/001-streaming-discovery-assistant/tasks.md` — the single source of truth for task sequencing. Work through it top to bottom; do not reorder phases without updating that file's Dependencies section to match.

## Development rules (TDD, non-negotiable)

This project's Principle I is test-first, not test-eventually:

1. Find the task in `tasks.md`. If it's an implementation task, its preceding test task(s) must already exist and must currently **fail**. If they don't exist yet, something is out of order — stop and fix the sequencing before writing implementation code.
2. Write the test first if it isn't written. Run it. Confirm it fails for the right reason (not a typo or import error).
3. Write the minimal implementation to make it pass.
4. Refactor with tests green.
5. Run the full suite (`pytest`) before considering the task done — a task that passes its own test but breaks another isn't done.
6. Check the task off in `tasks.md` in the same commit that completes it, so the file stays accurate. A stale `tasks.md` (checked-off work that isn't done, or done work left unchecked) is itself a defect — this project has already caught and fixed exactly that kind of drift once (see the process log), don't reintroduce it.
7. Commit per completed task or small logical cluster of tasks — not one commit per whole phase, and not one commit per file touched. The commit message should say which task(s) it completes.

No implementation code for a capability without a documented acceptance criterion behind it (spec.md FR/AC, or a task in `tasks.md`). If you find yourself writing code that doesn't map to either, stop and check whether a requirement is missing or the code is out of scope.

## Agent boundaries

Four components, four contracts (`specs/001-streaming-discovery-assistant/contracts/*.md` has the full behavioral guarantees, failure modes, and non-responsibilities for each — read the relevant one before touching that agent's file):

| Component | File | Calls a model? | One-line boundary |
|---|---|---|---|
| Orchestrator | `src/streaming_discovery/agents/orchestrator.py` | **No** | Owns session state, sequencing, the retry decision, and contract validation at every handoff. Never interprets text, never calls TMDB, never ranks. |
| Preference Agent | `src/streaming_discovery/agents/preference_agent.py` | Yes | Free text/intake → `PreferenceProfile`. Never calls TMDB, never ranks, never relaxes a constraint. |
| Discovery Agent | `src/streaming_discovery/agents/discovery_agent.py` | **No** | `DiscoveryQuery` → `CandidatePool` via the TMDB adapter. Never interprets intent, never ranks, never decides whether to retry. |
| Recommendation Agent | `src/streaming_discovery/agents/recommendation_agent.py` | Yes | `PreferenceProfile` + `CandidatePool` → `RecommendationPackage`. Never calls TMDB, never modifies the profile, never fact-checks beyond the candidate's own data. |

The Orchestrator/Discovery-Agent "no model" line is load-bearing (constitution Principle II, spec NFR-008) — if you find yourself wanting to add a model call to either, that's a sign the work belongs in one of the other two agents instead, not a reason to relax the rule.

Every handoff between these four is a validated Pydantic model (`src/streaming_discovery/contracts/`). A handoff that fails validation is a controlled failure — raise/surface it, never coerce or default around it.

## Scope boundaries (what this project deliberately does not do)

From `spec.md`'s Non-Goals and the constitution's Technology & Architectural Constraints — enforced, not aspirational:

- **TMDB is the only external data source.** No web search, no scraping, no second live API. If a requirement seems to need more/better data than TMDB provides, that's a spec conversation, not a "just add a scraper" decision.
- **No RAG, no vector store, no embeddings-based search.** Candidate discovery is TMDB's own search/discover/similar endpoints, full stop.
- **No persistence.** In-memory session state only; the optional export (FR-024) is a one-time write-out, not a database.
- **Terminal-only interface.** No web/GUI front-end in this feature.
- **Exactly one discovery retry, exactly 1–2 LLM-call retries** — both bounded and independent of each other (FR-011, FR-028). Do not add a third retry path or a backoff library for either; the bound is the point.
- **Detail-level TMDB data (runtime, provider lists, keywords) is fetched only for finalist candidates**, not the whole raw pool, except where a hard TV constraint (runtime or season count) requires evaluating it earlier — see `contracts/discovery-agent.md`'s hard-filter exception before changing fetch timing.
- **Internal contracts never mirror TMDB's raw shape.** Before adding a field to any contract, name its consumer and the requirement it supports (FR-030) — if you can't, don't add it. See `spec.md`'s Domain Model Minimization Rationale for the standard this is held to.

## Configuration and secrets

- Runtime configuration is `src/streaming_discovery/config.py` (`pydantic-settings`, reads `.env`). Never hardcode a region, a retry count, or a credential in code — add a `Settings` field.
- `.env` holds real credentials and is git-ignored; `.env.example` documents the required variables and is committed. Keep them in sync when you add a new setting.
- Demo/test mode (`Settings.demo_mode`, and the fixture-backed fakes in `tmdb/fake_client.py` and `llm/fake_provider.py`) must never require a real credential. If a test fails without `.env` populated, that test is wired to the wrong implementation.

## Running things

- `pytest` — full suite. Should pass with zero live network/model calls at all times.
- `ruff check` / `ruff format` — lint/format before committing.
- See `specs/001-streaming-discovery-assistant/quickstart.md` for the 10 scenario walkthroughs (demo-mode, fixture-backed) that double as the project's own acceptance demo.
