"""Optional, user-requested session export to JSON or Markdown (FR-024).

Export is user-initiated at the end of a session, not automatic (spec.md
Assumptions). Reads `Orchestrator.session` (a `UserSessionState`) rather
than re-deriving the same data from the CLI's own local variables.
"""

from __future__ import annotations

from pathlib import Path

from streaming_discovery.agents.orchestrator import build_confirmation_summary
from streaming_discovery.contracts.session_state import UserSessionState


def export_session_json(session: UserSessionState, path: Path) -> None:
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")


def build_session_markdown(session: UserSessionState) -> str:
    lines: list[str] = ["# Streaming Discovery Session", ""]

    if session.raw_user_input:
        lines.append(f"**Request**: {session.raw_user_input}")
        lines.append("")

    if session.preference_profile is not None:
        lines.append("## Preferences applied")
        lines.append("")
        lines.append(build_confirmation_summary(session.preference_profile))
        lines.append("")

    package = session.recommendation_package
    if package is not None:
        any_role = False
        for role_label, pick in (
            ("Best Match", package.best_match),
            ("Safe Pick", package.safe_pick),
            ("Wildcard Pick", package.wildcard_pick),
        ):
            if pick is None:
                continue
            any_role = True
            year = pick.candidate.release_year or "n/a"
            lines.append(f"## {role_label}: {pick.candidate.title} ({year})")
            lines.append("")
            lines.append(pick.rationale)
            lines.append("")
            if pick.confidence_note:
                lines.append(f"*Note: {pick.confidence_note}*")
                lines.append("")
            if pick.candidate.provider_names:
                providers = ", ".join(pick.candidate.provider_names)
                lines.append(f"*Available on: {providers} (not a live availability guarantee)*")
                lines.append("")

        if package.relaxed_constraint is not None:
            lines.append(
                f"*The {package.relaxed_constraint.value} constraint was relaxed to find "
                "these matches.*"
            )
            lines.append("")

        if package.unresolved_notes:
            lines.append(package.unresolved_notes)
            lines.append("")

        if not any_role and not package.unresolved_notes:
            lines.append("No recommendations were produced.")
            lines.append("")

    return "\n".join(lines)


def export_session_markdown(session: UserSessionState, path: Path) -> None:
    path.write_text(build_session_markdown(session), encoding="utf-8")
