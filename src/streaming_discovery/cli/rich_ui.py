"""Rich-based terminal presentation layer.

This module is presentation only -- styling and layout. The content
decisions (which fields to show, what the wording says) live in
`agents.orchestrator.build_confirmation_summary` and
`cli.output.render_package`, which stay the plain-text source of truth
(and stay covered by their own existing tests); this module just prints
that same information with panels, tables, and color instead of bare
`print()` calls, for a cleaner terminal experience.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.contracts.recommendation_package import RecommendationPackage

_ROLE_DISPLAY: dict[str, tuple[str, str]] = {
    "Best Match": ("bold green", "*"),
    "Safe Pick": ("bold cyan", "*"),
    "Wildcard Pick": ("bold magenta", "*"),
}

# (label, PreferenceProfile attribute, is_list)
_SUMMARY_FIELDS: list[tuple[str, str, bool]] = [
    ("Format", "media_type", False),
    ("Providers", "providers", True),
    ("Genres", "genres", True),
    ("Excluding genres", "excluded_genres", True),
    ("Tone", "tone_descriptors", True),
    ("Setting", "setting_descriptors", True),
    ("Themes", "theme_descriptors", True),
    ("Languages", "languages", True),
    ("Runtime under", "runtime_max_minutes", False),
    ("Seasons at most", "season_count_max", False),
    ("Liked titles", "liked_titles", True),
    ("Disliked titles", "disliked_titles", True),
    ("Notes", "additional_notes", False),
]


def build_console() -> Console:
    """The console used for real terminal sessions. Tests construct
    their own `Console(file=..., force_terminal=False)` instead, to
    capture and assert on output without a real terminal.
    """
    return Console()


def print_welcome_banner(console: Console) -> None:
    console.print(
        Panel(
            Text("Find something to watch, from a mood or a specific ask.", justify="center"),
            title="[bold]Streaming Discovery Assistant[/bold]",
            border_style="bold blue",
        )
    )


def print_confirmation_summary(console: Console, profile: PreferenceProfile) -> None:
    """A table of only the populated fields in `profile` (FR-006) --
    same content `build_confirmation_summary` produces as plain text,
    styled as a table here instead.
    """
    table = Table(title="Here's what I understood", show_header=False, border_style="blue")
    table.add_column("Field", style="bold")
    table.add_column("Value")

    any_row = False
    for label, attr, is_list in _SUMMARY_FIELDS:
        value = getattr(profile, attr)
        if is_list:
            if not value:
                continue
            display_value = ", ".join(value)
        else:
            if value is None:
                continue
            display_value = value.value if hasattr(value, "value") else str(value)
        table.add_row(label, display_value)
        any_row = True

    if profile.year_min is not None or profile.year_max is not None:
        table.add_row("Year range", f"{profile.year_min or 'any'}-{profile.year_max or 'any'}")
        any_row = True

    if not any_row:
        console.print("[dim](no preferences captured yet)[/dim]")
        return
    console.print(table)


def print_recommendation_package(console: Console, package: RecommendationPackage) -> None:
    """One styled panel per filled role, then the relaxed-constraint
    disclosure and/or no-match explanation -- same content
    `cli.output.render_package` produces as plain text.
    """
    any_pick = False
    for role_label, pick in (
        ("Best Match", package.best_match),
        ("Safe Pick", package.safe_pick),
        ("Wildcard Pick", package.wildcard_pick),
    ):
        if pick is None:
            continue
        any_pick = True
        style, marker = _ROLE_DISPLAY[role_label]
        year = pick.candidate.release_year or "n/a"

        body = Text(pick.rationale)
        if pick.confidence_note:
            body.append("\n\n")
            body.append(f"Note: {pick.confidence_note}", style="italic yellow")
        if pick.candidate.provider_names:
            providers = ", ".join(pick.candidate.provider_names)
            body.append("\n\n")
            body.append(f"Available on: {providers}", style="dim")
            body.append(" (not a live availability guarantee)", style="dim italic")

        console.print(
            Panel(
                body,
                title=f"[{style}]{marker} {role_label}: {pick.candidate.title} ({year})[/{style}]",
                border_style=style.split()[-1],
                expand=False,
            )
        )

    if package.relaxed_constraint is not None:
        console.print(
            f"[yellow]Note:[/yellow] the [bold]{package.relaxed_constraint.value}[/bold] "
            "constraint was relaxed to find these matches."
        )
    if package.unresolved_notes:
        console.print(f"[red]{package.unresolved_notes}[/red]")
    if not any_pick and not package.unresolved_notes:
        console.print("[red]No recommendations could be produced.[/red]")
