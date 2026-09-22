# Streaming Discovery Assistant

A terminal-based movie/TV recommendation assistant. Describe what you're in
the mood to watch — vague ("dark, moody, Eastern European vibes"), specific
("Netflix or Hulu, movie, after 2010, powerful female lead, not superhero"),
or similarity-based ("something like Arrival and Severance") — and it
returns exactly three differentiated, explained picks: a **Best Match**, a
**Safe Pick**, and a **Wildcard Pick**, sourced from [TMDB](https://www.themoviedb.org/).

This project is built spec-first and test-first (SDD/TDD) using SpecKit; see
[Project docs](#project-docs) below for the full spec, architecture, and
process history.

## Setup

Requires Python 3.11+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
```

To run against the real TMDB and OpenRouter APIs, copy `.env.example` to
`.env` and fill in real credentials:

```bash
cp .env.example .env
```

```
TMDB_API_TOKEN="your_tmdb_api_token"
OPENROUTER_API_KEY="your_openrouter_api_key"
MODEL_NAME="your_model_name"
REGION="your_region"
```

`TMDB_API_TOKEN` is a TMDB v4 read access token. `OPENROUTER_API_KEY` and
`MODEL_NAME` configure the language model used to interpret free text and
write recommendation rationale, via [OpenRouter](https://openrouter.ai/)'s
OpenAI-compatible API. `REGION` (e.g. `US`) controls which country's
watch-provider list is shown; it is a configuration value, never asked of
the user (FR-020).

## Running it

```bash
uv run streaming-discovery
```

This prompts for a free-text description of what you're in the mood to
watch (or press Enter to skip straight to a few optional guided questions),
confirms its interpretation before searching, then prints the three picks.

## Demo mode (no credentials required)

Every capability in this project is fixture-backed and testable — and
runnable — without any real API credentials. Set `DEMO_MODE=true` (or
`demo_mode=true` in `.env`) to run the full pipeline against deterministic
fakes instead of live TMDB/OpenRouter:

```bash
DEMO_MODE=true uv run streaming-discovery
```

A recorded transcript of every scenario from `quickstart.md`, captured this
way, lives at [`docs/quickstart-walkthrough.md`](docs/quickstart-walkthrough.md)
— regenerate it with `uv run python scripts/record_quickstart_walkthrough.py`.

## Architecture overview

Four components hand off validated Pydantic contracts to each other in a
straight pipeline — no component reaches past its neighbors, and only two
of the four ever call a language model:

```
raw text / intake answers
        │
        ▼
┌─────────────────┐   PreferenceProfile   ┌──────────────┐   DiscoveryQuery    ┌──────────────────┐
│ Preference Agent │ ────────────────────▶ │              │ ──────────────────▶ │  Discovery Agent  │
│   (calls a       │                       │ Orchestrator │                      │  (no model call;  │
│   model)         │                       │ (no model    │                      │  TMDB search /    │
└─────────────────┘                       │  call)       │                      │  discover only)   │
                                            │              │   CandidatePool      └──────────────────┘
                                            │              │ ◀──────────────────────────┘
┌───────────────────┐  RecommendationPackage│              │
│ Recommendation     │ ◀─────────────────── │              │
│ Agent (calls a     │                      └──────────────┘
│ model)             │        ▲ PreferenceProfile + CandidatePool
└───────────────────┘         └──────────────────────────────
```

| Component | Calls a model? | Responsibility |
|---|---|---|
| **Orchestrator** | No | Owns session state, sequencing, the one bounded zero-result retry, and contract validation at every handoff. |
| **Preference Agent** | Yes | Free text / intake answers → `PreferenceProfile`. |
| **Discovery Agent** | No | `DiscoveryQuery` → `CandidatePool`, via the TMDB adapter only. |
| **Recommendation Agent** | Yes | `PreferenceProfile` + `CandidatePool` → `RecommendationPackage` (three roles, ranked and explained). |

The Orchestrator/Discovery-Agent "no model" boundary is deliberate and
enforced (constitution Principle II, spec NFR-008): sequencing, retry
counts, and hard-constraint enforcement must be guaranteed, not
interpreted, so they stay fully deterministic. Every handoff between
components is a validated Pydantic contract (`src/streaming_discovery/contracts/`)
— a handoff that fails validation is a controlled failure, surfaced rather
than coerced around.

TMDB is the sole external data source (no web search, no scraping, no
vector store); session state is in-memory only, with an optional one-time
JSON/Markdown export; the retry policy is exactly one bounded discovery
retry with deterministic soft-constraint relaxation, plus 1–2 independent
LLM-call retries on outright model failure.

See `CLAUDE.md` for the full agent-boundary contract table and development
rules, and `specs/001-streaming-discovery-assistant/contracts/*.md` for
each agent's complete behavioral guarantees, failure modes, and
non-responsibilities.

## Development

```bash
uv run pytest        # full suite, zero live network/model calls
uv run ruff check .   # lint
uv run ruff format .  # format
```

This project follows strict test-first development — see `CLAUDE.md` for
the non-negotiable TDD workflow this codebase was built under.

## Project docs

- [`CLAUDE.md`](CLAUDE.md) — guidance for implementing this repository: TDD rules, agent boundaries, scope boundaries.
- [`.specify/memory/constitution.md`](.specify/memory/constitution.md) — the seven governing principles.
- [`specs/001-streaming-discovery-assistant/spec.md`](specs/001-streaming-discovery-assistant/spec.md) — what's being built and why.
- [`specs/001-streaming-discovery-assistant/plan.md`](specs/001-streaming-discovery-assistant/plan.md), [`research.md`](specs/001-streaming-discovery-assistant/research.md), [`data-model.md`](specs/001-streaming-discovery-assistant/data-model.md), [`contracts/*.md`](specs/001-streaming-discovery-assistant/contracts/) — how it's built.
- [`specs/001-streaming-discovery-assistant/quickstart.md`](specs/001-streaming-discovery-assistant/quickstart.md) — the 10 scenario walkthroughs used as this project's own acceptance demo; recorded transcript at [`docs/quickstart-walkthrough.md`](docs/quickstart-walkthrough.md).
- [`specs/001-streaming-discovery-assistant/tasks.md`](specs/001-streaming-discovery-assistant/tasks.md) — the task-by-task build log.
- [`docs/prompts-history/`](docs/prompts-history/) — high-level summaries of the decisions, pushback, and rationale behind major milestones in this project's development.
