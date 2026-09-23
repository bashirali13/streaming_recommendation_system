"""Guided-intake CLI flow (User Story 6): the optional five-question
walkthrough (format, services, mood/interests, exclusions, optional
constraints) from spec.md's Assumptions, feeding into the same
confirmation/correction step User Story 1 already made interactive
(cli/output.py's `default_confirm`) -- no new interactivity mechanism is
built here, only the guided-intake-specific prompts.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich.console import Console

from streaming_discovery.agents.orchestrator import Orchestrator
from streaming_discovery.cli.export import export_session_json, export_session_markdown
from streaming_discovery.cli.output import (
    InputFunc,
    PrintFunc,
    build_orchestrator,
    default_confirm,
    render_package,
)
from streaming_discovery.cli.rich_ui import (
    build_console,
    print_confirmation_summary,
    print_recommendation_package,
    print_welcome_banner,
)
from streaming_discovery.config import Settings
from streaming_discovery.contracts.preference_profile import PreferenceProfile
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


def _already_answered(key: str, profile: PreferenceProfile) -> bool:
    """Whether a partial `PreferenceProfile` already interpreted from
    free text alone fully covers this guided question (T085; spec.md
    line 308). Only the three questions that map 1:1 to a single
    profile field can ever be reported as fully answered -- the two
    compound questions (mood_and_interests, optional_constraints) each
    cover several fields at once, so a binary skip could silently drop
    whichever of those free text didn't cover; they are previewed via
    `_already_noted_note` instead of skipped.
    """
    if key == "format":
        return profile.media_type is not None
    if key == "services":
        return bool(profile.providers)
    if key == "exclusions":
        return bool(profile.excluded_genres)
    return False


def _already_noted_note(key: str, profile: PreferenceProfile) -> str | None:
    """A short preview of what free text already captured for a
    compound guided question, to append to its prompt so answering
    feels additive rather than a blind re-ask. `None` when there is
    nothing to show, or for a single-field question (those are skipped
    outright by `_already_answered` instead of previewed).
    """
    if key == "mood_and_interests":
        parts = [
            *profile.genres,
            *profile.tone_descriptors,
            *profile.setting_descriptors,
            *profile.theme_descriptors,
        ]
    elif key == "optional_constraints":
        parts = []
        if profile.year_min is not None or profile.year_max is not None:
            parts.append(f"{profile.year_min or 'any'}-{profile.year_max or 'any'}")
        if profile.runtime_max_minutes is not None:
            parts.append(f"under {profile.runtime_max_minutes} min")
        if profile.season_count_max is not None:
            parts.append(f"at most {profile.season_count_max} seasons")
        parts.extend(profile.languages)
        parts.extend(profile.liked_titles)
        parts.extend(profile.disliked_titles)
        if profile.additional_notes:
            parts.append(profile.additional_notes)
    else:
        parts = []
    return f"(already noted: {', '.join(parts)}) " if parts else None


async def run_guided_intake(
    *,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
    partial_profile: PreferenceProfile | None = None,
) -> dict[str, str | None]:
    """Ask the five optional intake prompts in the fixed sequence; a
    blank answer stays unspecified (FR-002, FR-003), never defaulted.

    `partial_profile`, if given, is what free text alone already
    interpreted into a `PreferenceProfile` (T085): a question already
    fully answered by it is skipped outright rather than re-asked, and
    a compound question that's partially covered gets an "already
    noted" preview appended to its prompt instead.
    """
    print_func("A few optional questions -- press Enter to skip any of them.")
    answers: dict[str, str | None] = {}
    for key, prompt in _INTAKE_PROMPTS.items():
        if partial_profile is not None:
            if _already_answered(key, partial_profile):
                answers[key] = None
                continue
            note = _already_noted_note(key, partial_profile)
            if note:
                prompt = f"{prompt}{note}"
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
    console: Console | None = None,
) -> None:
    """The unified guided-discovery entry point: an optional leading
    free-text prompt, then the five guided questions, then the shared
    confirmation step -- surfacing a conflict between the two input
    sources before the user confirms (spec.md Edge Cases).

    `console`, if given, switches the confirmation summary and final
    recommendation rendering to the styled Rich presentation
    (cli/rich_ui.py) instead of the plain-text default; `print_func` is
    still used for the intake prompts/questions either way. Leaving
    `console` unset (the default) keeps the original plain-text
    behavior unchanged, so every existing test that doesn't pass one
    keeps working exactly as before.
    """
    if console is not None:
        print_welcome_banner(console)
    print_func(
        "What are you in the mood to watch? "
        "(Press Enter to skip straight to a few guided questions.)"
    )
    raw_user_input = input_func("> ").strip() or None

    # T085: when free text was given, interpret it alone first so the
    # guided questions it already answers can be skipped (or, for a
    # compound question, previewed) instead of re-asked. A bounded,
    # separate LLM call from the one that produces the final profile --
    # if it fails outright, fall back to asking every question as
    # before, rather than letting a purely-optimistic pre-check take
    # down the whole session (the final interpret call inside
    # run_single_attempt still reports a real failure normally).
    partial_profile: PreferenceProfile | None = None
    if raw_user_input:
        try:
            partial_profile = await orchestrator.interpret_preferences(
                raw_user_input=raw_user_input, intake_answers=None
            )
        except ModelCallError:
            partial_profile = None

    intake_answers = await run_guided_intake(
        input_func=input_func, print_func=print_func, partial_profile=partial_profile
    )

    conflict = _detect_format_conflict(raw_user_input, intake_answers)
    if conflict:
        print_func(f"\nHeads up: {conflict}. Please resolve this at the confirmation step below.")

    async def confirm(profile) -> dict | None:
        render_summary = (
            (lambda p: print_confirmation_summary(console, p)) if console is not None else None
        )
        return await default_confirm(
            profile, input_func=input_func, print_func=print_func, render_summary=render_summary
        )

    try:
        if console is not None:
            with console.status(
                "[bold blue]Finding something to watch...[/bold blue]", spinner="line"
            ):
                package = await orchestrator.run_single_attempt(
                    raw_user_input=raw_user_input, intake_answers=intake_answers, confirm=confirm
                )
        else:
            package = await orchestrator.run_single_attempt(
                raw_user_input=raw_user_input, intake_answers=intake_answers, confirm=confirm
            )
    except TmdbAdapterError as exc:
        print_func(f"\nTMDB is currently unavailable: {exc.error.detail}")
        return
    except ModelCallError as exc:
        print_func(f"\nThe interpretation step failed: {exc}")
        return

    if console is not None:
        print_recommendation_package(console, package)
    else:
        print_func(render_package(package))

    await _offer_export(orchestrator, input_func=input_func, print_func=print_func)


async def _offer_export(
    orchestrator: Orchestrator, *, input_func: InputFunc, print_func: PrintFunc
) -> None:
    """Ask whether to export the session (FR-024) -- user-initiated,
    never automatic; skipped on a blank answer.
    """
    answer = (
        input_func("\nExport this session? (json / markdown / press Enter to skip): ")
        .strip()
        .lower()
    )
    if answer not in ("json", "markdown"):
        return
    default_name = "session.json" if answer == "json" else "session.md"
    path = Path(input_func(f"Save as [{default_name}]: ").strip() or default_name)
    if answer == "json":
        export_session_json(orchestrator.session, path)
    else:
        export_session_markdown(orchestrator.session, path)
    print_func(f"Saved to {path}")


def main() -> None:
    """The real terminal entry point (`[project.scripts]` in
    pyproject.toml): the unified guided-discovery flow, with the styled
    Rich UI.
    """
    settings = Settings()
    orchestrator = build_orchestrator(settings)
    asyncio.run(run_guided_cli(orchestrator, console=build_console()))


if __name__ == "__main__":
    main()
