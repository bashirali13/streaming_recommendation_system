"""Guided-intake CLI flow (User Story 6): the optional five-question
walkthrough (format, services, mood/interests, exclusions, optional
constraints) from spec.md's Assumptions, feeding into the same
confirmation/correction step User Story 1 already made interactive
(cli/output.py's `default_confirm`) -- no new interactivity mechanism is
built here, only the guided-intake-specific prompts.
"""

from __future__ import annotations

from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.cli.output import InputFunc, PrintFunc, default_confirm, render_package
from streaming_discovery.llm.provider import ModelCallError
from streaming_discovery.tmdb.client import TmdbAdapterError

# The six-step sequence from spec.md's Assumptions; step 6 (confirmation)
# reuses default_confirm and isn't a prompt in this dict.
_INTAKE_PROMPTS: dict[str, str] = {
    "format": "Movie, TV show, or either? ",
    "services": "Which streaming services should be considered? ",
    "mood_and_interests": 'What mood, genre, style, setting, or "vibe" are you looking for? ',
    "exclusions": "Anything to avoid, such as genres, themes, or franchises? ",
    "optional_constraints": (
        "Release year, runtime, language, recent favorites, disliked titles, or additional notes? "
    ),
}


async def run_guided_intake(
    *, input_func: InputFunc = input, print_func: PrintFunc = print
) -> dict[str, str | None]:
    """Ask the five optional intake prompts in the fixed sequence; a
    blank answer stays unspecified (FR-002, FR-003), never defaulted.
    """
    print_func("A few optional questions -- press Enter to skip any of them.")
    answers: dict[str, str | None] = {}
    for key, prompt in _INTAKE_PROMPTS.items():
        answer = input_func(prompt).strip()
        answers[key] = answer if answer else None
    return answers


def _detect_format_conflict(
    raw_user_input: str | None, intake_answers: dict[str, str | None]
) -> str | None:
    """A narrow, literal check for the specific case spec.md's Edge
    Cases names (free text says "movie," guided intake says "TV") -- not
    a general-purpose contradiction detector. Returns a human-readable
    description to surface at confirmation, or None.
    """
    if not raw_user_input:
        return None
    format_answer = (intake_answers.get("format") or "").strip().lower()
    if not format_answer:
        return None
    text = raw_user_input.lower()
    mentions_movie = "movie" in text
    mentions_tv = "tv" in text or "show" in text or "series" in text
    if format_answer in ("tv", "tv show", "series") and mentions_movie and not mentions_tv:
        return f'your request mentions "movie" but you answered "{format_answer}" for format'
    if format_answer in ("movie", "film") and mentions_tv and not mentions_movie:
        return (
            f'your request mentions a TV show/series but you answered "{format_answer}" for format'
        )
    return None


async def run_guided_cli(
    orchestrator: Orchestrator,
    *,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> None:
    """The unified guided-discovery entry point: an optional leading
    free-text prompt, then the five guided questions, then the shared
    confirmation step -- surfacing a conflict between the two input
    sources before the user confirms (spec.md Edge Cases).
    """
    print_func(
        "What are you in the mood to watch? "
        "(Press Enter to skip straight to a few guided questions.)"
    )
    raw_user_input = input_func("> ").strip() or None

    intake_answers = await run_guided_intake(input_func=input_func, print_func=print_func)

    conflict = _detect_format_conflict(raw_user_input, intake_answers)
    if conflict:
        print_func(f"\nHeads up: {conflict}. Please resolve this at the confirmation step below.")

    async def confirm(profile) -> dict | None:
        return await default_confirm(profile, input_func=input_func, print_func=print_func)

    try:
        package = await orchestrator.run_single_attempt(
            raw_user_input=raw_user_input, intake_answers=intake_answers, confirm=confirm
        )
    except TmdbAdapterError as exc:
        print_func(f"\nTMDB is currently unavailable: {exc.error.detail}")
        return
    except ModelCallError as exc:
        print_func(f"\nThe interpretation step failed: {exc}")
        return

    print_func(render_package(package))
