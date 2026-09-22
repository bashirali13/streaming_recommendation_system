"""Terminal rendering and the free-text CLI entry point for User Story 1.

Guided-intake prompts are added in User Story 6 (tasks.md T068); this
module covers the free-text path plus the confirmation step FR-006
requires for every request, not only guided intake.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from streaming_discovery.agents.discovery_agent import DiscoveryAgent
from streaming_discovery.agents.orchestrator import Orchestrator, build_confirmation_summary
from streaming_discovery.agents.preference_agent import PreferenceAgent
from streaming_discovery.agents.recommendation_agent import RecommendationAgent
from streaming_discovery.config import Settings
from streaming_discovery.contracts.recommendation_package import RecommendationPackage
from streaming_discovery.llm.provider import ModelCallError, ModelProvider
from streaming_discovery.tmdb.client import TmdbAdapterError, TmdbClient

# Fields the confirmation-correction syntax treats as list-valued
# ("field=value1|value2"); every other field is a plain scalar.
_LIST_FIELDS = {
    "providers",
    "genres",
    "excluded_genres",
    "tone_descriptors",
    "setting_descriptors",
    "theme_descriptors",
    "languages",
    "liked_titles",
    "disliked_titles",
    "hard_override_fields",
}

InputFunc = Callable[[str], str]
PrintFunc = Callable[[str], None]


def _parse_correction(raw: str) -> dict:
    correction: dict = {}
    for pair in raw.split(","):
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if key in _LIST_FIELDS:
            correction[key] = [v.strip() for v in value.split("|") if v.strip()]
        else:
            correction[key] = value
    return correction


async def default_confirm(
    profile, *, input_func: InputFunc = input, print_func: PrintFunc = print
) -> dict | None:
    """Interactive terminal confirmation (FR-006): print the interpreted
    summary, offer a chance to correct it. Returns `None` when the user
    accepts as-is (blank input), or a correction dict otherwise.
    `input_func`/`print_func` are injectable so this is testable without
    real stdin/stdout.
    """
    print_func("\nHere's what I understood:")
    print_func(build_confirmation_summary(profile))
    answer = input_func(
        "\nPress Enter to continue, or type a correction "
        "(e.g. media_type=tv, providers=Netflix|Hulu): "
    ).strip()
    if not answer:
        return None
    return _parse_correction(answer) or None


def render_package(package: RecommendationPackage) -> str:
    """Render a `RecommendationPackage` as plain text -- never raw JSON
    (FR-021), always naming a relaxed constraint or a no-match reason
    when present.
    """
    lines: list[str] = []
    for role_label, pick in (
        ("Best Match", package.best_match),
        ("Safe Pick", package.safe_pick),
        ("Wildcard Pick", package.wildcard_pick),
    ):
        if pick is None:
            continue
        year = pick.candidate.release_year or "n/a"
        lines.append(f"\n{role_label}: {pick.candidate.title} ({year})")
        lines.append(f"  {pick.rationale}")
        if pick.confidence_note:
            lines.append(f"  Note: {pick.confidence_note}")
        if pick.candidate.provider_names:
            providers = ", ".join(pick.candidate.provider_names)
            lines.append(f"  Available on: {providers} (not a live availability guarantee)")

    if package.relaxed_constraint is not None:
        lines.append(
            f"\n(To find these matches, the {package.relaxed_constraint.value} "
            "constraint was relaxed.)"
        )
    if package.unresolved_notes:
        lines.append(f"\n{package.unresolved_notes}")
    if not lines:
        lines.append("No recommendations could be produced.")
    return "\n".join(lines)


def _build_orchestrator(settings: Settings) -> Orchestrator:
    """Production wiring: real TMDB/model clients from `Settings`. Demo
    mode uses fixture-backed fakes instead (wired separately, per NFR-004
    -- see the quickstart.md walkthroughs)."""
    from streaming_discovery.tmdb.client import build_real_tmdb_client

    tmdb_client: TmdbClient = build_real_tmdb_client(settings.tmdb_api_token)
    model_provider: ModelProvider = _RealModelProvider(
        model_name=settings.model_name, api_key=settings.openrouter_api_key
    )
    return Orchestrator(
        preference_agent=PreferenceAgent(
            provider=model_provider, max_additional_attempts=settings.llm_retry_max_attempts
        ),
        discovery_agent=DiscoveryAgent(tmdb_client=tmdb_client),
        recommendation_agent=RecommendationAgent(
            provider=model_provider, max_additional_attempts=settings.llm_retry_max_attempts
        ),
        region=settings.region,
    )


class _RealModelProvider:
    """Production `ModelProvider`: one PydanticAI `Agent` per call,
    pointed at OpenRouter via its OpenAI-compatible API. Built here
    (rather than in llm/provider.py) since it's the CLI's concern which
    real provider backs the abstract interface -- llm/provider.py stays
    free of any specific SDK/provider import.
    """

    def __init__(self, *, model_name: str, api_key: str) -> None:
        self._model_name = model_name
        self._api_key = api_key

    async def generate(self, *, system_prompt: str, user_prompt: str, output_type):
        from pydantic_ai import Agent
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        model = OpenAIChatModel(
            self._model_name,
            provider=OpenAIProvider(base_url="https://openrouter.ai/api/v1", api_key=self._api_key),
        )
        agent = Agent(model, output_type=output_type, system_prompt=system_prompt)
        try:
            result = await agent.run(user_prompt)
        except Exception as exc:  # pydantic-ai's own transport/provider errors
            raise ModelCallError(f"Model call failed: {exc}") from exc
        return result.output


async def run_cli(
    orchestrator: Orchestrator,
    *,
    input_func: InputFunc = input,
    print_func: PrintFunc = print,
) -> None:
    raw_input_text = input_func("What are you in the mood to watch? ").strip()

    async def confirm(profile) -> dict | None:
        return await default_confirm(profile, input_func=input_func, print_func=print_func)

    try:
        package = await orchestrator.run_single_attempt(
            raw_user_input=raw_input_text, confirm=confirm
        )
    except TmdbAdapterError as exc:
        print_func(f"\nTMDB is currently unavailable: {exc.error.detail}")
        return
    except ModelCallError as exc:
        print_func(f"\nThe interpretation step failed: {exc}")
        return

    print_func(render_package(package))


def main() -> None:
    settings = Settings()
    orchestrator = _build_orchestrator(settings)
    asyncio.run(run_cli(orchestrator))


if __name__ == "__main__":
    main()
