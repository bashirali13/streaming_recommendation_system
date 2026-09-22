# Process Log 001: SpecKit Setup Through Task Breakdown

**Covers**: SpecKit initialization, initial specification, architecture/domain-model review, planning, constitution ratification, and task generation for feature `001-streaming-discovery-assistant`.

**Purpose of this document**: a condensed, high-level record of the reasoning, decisions, and back-and-forth behind the project's first milestone — not a transcript. It exists to demonstrate the thought process behind the spec-driven workflow, including where clarification was sought, where the user pushed back on an initial approach, and where the assistant pushed back or defended a design choice.

## 1. SpecKit initialization

The repository had no scaffolding beyond a project outline document. SpecKit was initialized for Claude Code with PowerShell scripts (`specify init --here --integration claude --script ps`), establishing the `/speckit-*` skill set and the `.specify/` templates/workflow used for everything that followed. Committed directly to `main` as foundational tooling, before any feature branch existed.

**Standing decision captured here**: going forward, feature work happens on branches with granular, logical commits — not directly on `main` — and the assistant was authorized to branch, commit, and (later) push without asking each time a logical step is reached.

## 2. Initial specification (`spec.md`)

Built from the project outline (`multi_agent_streaming_discovery_project_outline.md`) into a full SpecKit specification: problem statement, goals, scope/non-goals, six prioritized user journeys, functional and non-functional requirements, key entities, and success criteria — no implementation code, no plan or tasks yet, per the user's explicit instruction.

**Clarification raised (assistant → user)**: three ambiguities in the outline were flagged as `[NEEDS CLARIFICATION]`, prioritized above several lower-impact ones that were instead resolved with documented defaults:

1. What happens when only 1–2 qualifying candidates exist — not zero, but not enough for all three recommendation roles?
2. How is the TMDB watch-provider region determined?
3. What happens when a language-model call fails outright (not just returns invalid output)?

**User's resolution** (with stated reasoning, not just a pick):
- **Q1 → fewer than three roles returned.** The user was explicit that recommendation quality matters more than filling all three slots, and that the system should not broaden constraints just to force a third pick.
- **Q2 → a configuration value (`REGION`) with a fallback**, not an intake question — keeps guided intake and testing simple.
- **Q3 → retry the model call 1–2 times, then a controlled error** — transient failures are expected, but no deterministic fallback interpretation for the MVP.

These were encoded back into the spec as resolved functional requirements (not left as open questions), each traceable to the user's stated rationale.

## 3. Architecture and domain-model review (pushback in both directions)

Before moving to planning, the user reviewed an actual TMDB fixture and pushed back hard on the spec's domain model: TMDB's real payload (watch-provider data alone spans every country) was far larger than anything the application needed, and the instruction was explicit — **do not mirror TMDB's schema; every internal field must have a named consumer and a justifying requirement, or it gets cut.**

This produced a field-by-field audit of every contract (`CandidateMedia`, `DiscoveryQuery`, `CandidatePool`, `RecommendationPackage`), documented in `spec.md`'s "Domain Model Minimization Rationale." Concrete outcomes:

- **Cut**: raw genre ids, `popularity`, `vote_count`, per-candidate `language`, poster/backdrop paths, and roughly a dozen other TMDB-native fields with no consumer in any requirement.
- **Cut**: watch-provider data for every region and for rent/buy offers — narrowed to flatrate-only, configured-region-only.
- **Cut**: `CandidatePool.total_results` and `.retry_required` — the latter because the outline itself assigns the retry *decision* to the Orchestrator alone, and having the Discovery Agent pre-compute it blurred that boundary.
- **Kept, after evaluation**: `DiscoveryQuery` as a contract distinct from `PreferenceProfile`, even though it looked like duplicated fields at first glance — it turned out to be the boundary that keeps the Discovery Agent from ever seeing subjective free-text signals, which is load-bearing for the agent's non-responsibility list, not redundancy.
- **A genuine new finding, not requested**: only two of the four "agents" (Preference, Recommendation) need a language model at all — the Orchestrator's and Discovery Agent's responsibilities are entirely deterministic per the outline's own responsibility tables. This was surfaced as its own requirement (LLM usage boundary) rather than left implicit.

This review is the clearest example of the project's SDD discipline in practice: the domain model was actively challenged and shrunk rather than assumed, on the user's initiative, before any implementation code existed to make that harder.

## 4. Planning (`plan.md`, `research.md`, `data-model.md`, `contracts/`)

The "Potential Tech Stack" section of the outline was converted into concrete decisions with rejected alternatives recorded for each: PydanticAI over LangGraph or a hand-rolled function-calling loop (the pipeline is linear and bounded, not a general graph); `httpx` over `requests`; `pydantic-settings` reused rather than a second config library; a `Protocol`-based real/fake split for both the TMDB adapter and the model provider, which is what makes the credential-free demo mode possible; a small inline bounded retry instead of a retry library; plain stdlib terminal I/O instead of a formatting framework, deferred until a requirement actually needs it.

The Constitution Check gate in `plan.md` came back **N/A** rather than passing by default — at that point `.specify/memory/constitution.md` was still an unfilled template, so there was nothing to check against. This was reported plainly rather than silently skipped, with a recommendation to ratify one.

## 5. Constitution (`constitution.md`, v1.0.0)

Seven principles were ratified, most of them formalizing decisions already made during the spec and architecture review rather than introducing new ones: test-first development (non-negotiable), deterministic core with the LLM confined to two agents, typed contracts designed around consumer need rather than external API shape, hard constraints that are never silently relaxed, bounded and disclosed retries only, intentional simplicity (no element without a traceable requirement), and no fabrication or raw-data leakage to the user. Feature 001's own spec/plan/contracts were named as the reference example future features should match in rigor.

## 6. Task breakdown (`tasks.md`)

73 tasks across 9 phases, organized by user story so each is independently testable, with test tasks made mandatory (not optional, per the newly-ratified constitution) — every implementation task has a preceding, currently-failing test task ahead of it.

**A gap caught during this pass, not before**: User Story 5's acceptance scenario requires a hard "no more than three seasons" constraint, but no field for it existed anywhere in `data-model.md` — a miss from the original data-modeling pass. Rather than writing a task that referenced a nonexistent field, `data-model.md` and the Discovery Agent contract were patched first (a `season_count_max`/`season_count` field pair, plus documenting that TMDB has no server-side season-count filter, so this is a second exception to the "finalist-only enrichment" rule alongside TV runtime). This was called out explicitly as a correction rather than folded in silently.

## What this milestone demonstrates

A full pass through SpecKit's spec → clarify → (architecture review) → plan → constitution → tasks sequence, with two distinct kinds of course-correction on display: the user directing a significant redesign (domain-model minimization, triggered by reviewing real data the spec hadn't accounted for) and the assistant catching and fixing its own gap (the missing season-count field) before it could compound into an unimplementable task. The next log entry will pick up at the first implementation milestone (User Story 1 / MVP).
