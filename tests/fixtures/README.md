# Test Fixtures

This directory holds recorded data used to make every automated test and the fixture-backed demo mode run **without any live network or model call** (spec.md NFR-004, FR-025).

## Layout

- `tmdb/` — recorded TMDB API responses (JSON), one file per endpoint/scenario needed by a test or quickstart scenario. Each fixture is a real, minimized TMDB response shape (or a deliberately malformed one for error-path tests), not a hand-invented shortcut — the goal is to test against data shaped the way TMDB actually returns it, before `normalize.py` shrinks it down to `CandidateMedia`.
- `llm/` — recorded/deterministic model responses (JSON) used by `FakeModelProvider`, one file per scenario, so the same input always produces the same structured output in tests.

## Rules

- **No test in `tests/` may make a live HTTP call or a live model API call.** Every test either uses `FakeTmdbClient`/`FakeModelProvider` (backed by files here) or exercises pure deterministic code with in-memory data.
- **No fixture file contains a real credential.** They are TMDB/model *response* payloads, not request configuration — no API keys belong in this directory.
- Fixture filenames should describe the scenario they back (e.g., `discover_movie_specific_constraint.json`, `discover_zero_results.json`, `similar_titles_arrival.json`), so a failing test's fixture is easy to find and inspect.
- When a fixture needs to represent a TMDB error condition (timeout, HTTP error, malformed response), that's expressed through `FakeTmdbClient`'s injectable failure mode (see `tmdb/fake_client.py`), not by hand-crafting an invalid JSON file — the failure mode is the more direct and readable way to express "TMDB failed this way."

Fixtures are added incrementally as each task in `tasks.md` needs them — this directory starts empty except for this file.
