# Process Log 003: Status Checkpoint, Model-Usage Clarification, and Pre-Polish Alignment

**Covers**: the pause-and-review conversation after all six user stories were merged — an implementation status report, two self-discovered gaps, a clarification on why only two of the four agents call a language model, and the resulting pre-Polish fixes — for feature `001-streaming-discovery-assistant`.

**Purpose of this document**: see Process Log 001 — a condensed, high-level record of reasoning, decisions, and course-corrections, not a transcript. This entry also renames this folder from `docs/process-log/` to `docs/prompts-history/`, at the user's request, with no change to what belongs in it.

## 1. The status checkpoint

With all six user stories merged, the user asked to pause before Polish for a full status conversation rather than pushing straight ahead: a high-level implementation overview, anything discovered along the way, how a user would actually run the system, whether it was genuinely usable yet, and what Polish still covered.

The honest answer split three ways. As **tested logic**, the pipeline was complete and proven — 106 tests exercising all six journeys and the retry policy end-to-end against fakes. As **something a person runs with one command**, it was not: two entry points existed (`cli.output.run_cli`, free-text only, wired to `main()`; `cli.intake.run_guided_cli`, the more complete unified flow, wired to nothing), and no `[project.scripts]` entry existed at all. Against **live TMDB/OpenRouter**, the real adapters had never been exercised even once — every test correctly used fakes, but that also meant the `normalize.py` field mappings (built from general knowledge of TMDB's API shape, since the fixture file the user mentioned early in the project was never actually shared) were unverified against a real payload.

## 2. Two gaps found by reviewing the finished implementation, not by any test failing

Neither of these surfaced during the eight phases already built — both were caught only by stepping back and reading the code as a whole during the status review, which is itself worth noting as a reason to schedule review checkpoints rather than only moving forward phase by phase.

- **The tone-relaxation retry was a no-op.** `select_relaxation_constraint` correctly picks `TONE` first when a user's only soft signal is a mood/vibe descriptor — that part was unit-tested from User Story 4 onward. But `build_discovery_queries` had no branch that changed anything about the retried query when `TONE` was the relaxed constraint, because tone/setting/theme descriptors never reach `DiscoveryQuery` by design. Every US4/US5 test happened to use `RUNTIME` or `YEAR_RANGE` relaxation instead, so the gap was never exercised. In practice: a real request whose only soft constraint was a vibe description, returning zero results, would "retry" with the identical query and get the identical zero result.
- **`UserSessionState` was dead code.** Built and contract-tested in Foundational, but nothing in `Orchestrator.run_single_attempt` or either CLI flow ever constructed one. Harmless until Polish's export task, which needs something to export from.

## 3. Clarifying why only two agents call a model

The user asked directly why the Orchestrator and Discovery Agent never touch a language model, wanting the reasoning laid out rather than just asserted. The answer traced back to the pre-implementation architecture review: of the four agents, only the Preference Agent (turning free text into structured fields) and the Recommendation Agent (writing rationale text) do work that is inherently language-shaped. Every guarantee the project treats as non-negotiable — exactly one retry, a hard exclusion never relaxed, no duplicate picks — lives in plain code specifically so it can be *proven*, not just usually true. If the retry decision were made by a model call, "exactly once" would be a hope instead of a tested fact. Keeping those invariants deterministic also means a bad day from the model (odd phrasing, a slow response) can never break a correctness guarantee, only the wording of an explanation.

## 4. Fixes applied, at the user's direction

The user said to proceed with the two recommended fixes and asked, separately, for a clean terminal UI.

- **Tone-relaxation fix**: a failing unit test was written first, confirming the retry query was identical before and after "relaxing" tone; the fix makes relaxing `TONE` drop `included_genres` from that attempt — genre being the only `DiscoveryQuery`-visible proxy for a vibe-driven interpretation — while leaving `excluded_genres` untouched, since that stays hard regardless of which soft constraint is relaxed.
- **Terminal UI**: this explicitly revisited an earlier decision. `research.md`'s original call was "no formatting library for the MVP... revisit if a later story adds a presentation-quality requirement" — the user's request is exactly that trigger. `rich` was added, and a new presentation-only layer (`cli/rich_ui.py`) was built to style the *same* content the existing plain-text builders already produced and tested, rather than re-deciding "what to show" in two places. The richer rendering is opt-in via a `console` parameter, so every prior test kept passing unchanged. The CLI's two disconnected entry points were also unified into one (`streaming-discovery`, via a new `[project.scripts]` entry), since a clean UI matters little if there's no single command to reach it.

## 5. A workflow slip, caught and corrected

While making the fixes above, the assistant never switched back to the feature branch after the previous merge and committed the pre-Polish work directly to `main`. This was caught immediately afterward by checking the current branch before continuing, disclosed to the user rather than left unmentioned, and corrected by fast-forwarding the feature branch to match `main` (the content was already correct and pushed, so no history was rewritten) — then resuming Polish properly on the branch. Included here because the project's own standard, applied to itself: a process deviation gets named, not smoothed over.

**Result**: 115 tests passing, lint/format clean, both branches back in sync. Polish (T073–T081) resumes next.
