"""ModelProvider: the interface both the Preference Agent and
Recommendation Agent depend on for their one language-model call each
(NFR-008), plus the bounded-retry wrapper around it (FR-028).

The Orchestrator and Discovery Agent never import from this module --
that boundary is what makes them deterministic (constitution Principle
II). The concrete production implementation is built alongside each
agent (tasks.md T041/T043), typically wrapping a PydanticAI Agent or an
OpenAI-compatible client pointed at OpenRouter; `FakeModelProvider`
(fake_provider.py) satisfies the same interface for tests and demo mode
(NFR-004).
"""

from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class ModelCallError(Exception):
    """Raised on an outright model-call failure (timeout, provider
    outage, rate limit) -- as opposed to the model returning output that
    fails the calling agent's own schema validation, which is a separate
    concern handled by that agent/the Orchestrator, not retried here
    (FR-022, FR-028).
    """


class ModelProvider(Protocol):
    async def generate(self, *, system_prompt: str, user_prompt: str, output_type: type[T]) -> T:
        """Make one call to the underlying language model and return its
        response parsed as `output_type`. Must raise `ModelCallError` on
        an outright call failure -- never return a partially-formed
        result or silently substitute a default.
        """
        ...


async def generate_with_retry(
    provider: ModelProvider,
    *,
    system_prompt: str,
    user_prompt: str,
    output_type: type[T],
    max_additional_attempts: int,
) -> T:
    """Bounded-retry wrapper (FR-028): on `ModelCallError`, retry up to
    `max_additional_attempts` more times, then let the final
    `ModelCallError` propagate as a controlled failure. Any other
    exception (e.g. the model's output failing schema validation)
    propagates immediately on the first occurrence -- only an outright
    call failure is retried. This retry is independent of, and does not
    count against, the one discovery retry governed by FR-011.
    """
    attempts_made = 0
    last_error: ModelCallError | None = None
    while attempts_made <= max_additional_attempts:
        try:
            return await provider.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                output_type=output_type,
            )
        except ModelCallError as exc:
            last_error = exc
            attempts_made += 1
    assert last_error is not None  # loop always runs >=1 time
    raise last_error
