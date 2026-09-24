"""FakeModelProvider: deterministic, fixture-backed fake `ModelProvider`
for tests and the credential-free demo mode (NFR-004).
"""

from __future__ import annotations

from typing import TypeVar

from streaming_discovery.llm.provider import ModelCallError

T = TypeVar("T")


class FakeModelProvider:
    """Returns a pre-configured response for a given prompt (or raises
    `ModelCallError` a configured number of times first) instead of
    calling a real model.

    `responses` maps `user_prompt` to the value `generate()` should
    return for it -- deterministic, so the same input always produces
    the same structured output in tests. `defaults_by_type` answers any
    prompt of a given output type that has no exact entry -- for calls whose
    exact prompt a test does not care about (e.g. a ranking-only judge call).
    `fail_times` makes the first N calls raise `ModelCallError` before
    succeeding; `always_fail=True` never succeeds. Both exist to exercise the bounded-retry wrapper
    (FR-028) without a real model.
    """

    def __init__(
        self,
        *,
        responses: dict[str, object] | None = None,
        fail_times: int = 0,
        always_fail: bool = False,
        defaults_by_type: dict[type, object] | None = None,
    ) -> None:
        self._responses = responses or {}
        self._defaults_by_type = defaults_by_type or {}
        self._fail_times = fail_times
        self._always_fail = always_fail
        self.call_count = 0

    async def generate(self, *, system_prompt: str, user_prompt: str, output_type: type[T]) -> T:
        self.call_count += 1
        if self._always_fail or self.call_count <= self._fail_times:
            raise ModelCallError(f"FakeModelProvider configured to fail (call {self.call_count})")
        if user_prompt not in self._responses and output_type in self._defaults_by_type:
            return self._defaults_by_type[output_type]  # type: ignore[return-value]
        if user_prompt not in self._responses:
            raise KeyError(
                f"FakeModelProvider has no configured response for prompt: {user_prompt!r}"
            )
        return self._responses[user_prompt]  # type: ignore[return-value]
