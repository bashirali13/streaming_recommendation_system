"""Unit test (T110): `_RealModelProvider` never set a temperature, so the
Preference Agent's extraction was sampled at the provider default. Live,
the same prompt ("An action movie made in the last 5 years, avoid anything
with Dwayne Johnson") once came back as a nearly empty profile
(`{media_type: movie}`), yet extracted correctly in 4 of 4 fresh runs;
"A Korean TV drama" captured genre Drama in only 1 of 4. Extraction is a
classification task and must be repeatable, so the provider now takes an
explicit temperature and passes it on every call.
"""

import pytest

from streaming_discovery.cli.output import _RealModelProvider


class _Result:
    output = "ok"


class _RecordingAgent:
    instances: list["_RecordingAgent"] = []

    def __init__(self, model, *, output_type, system_prompt) -> None:
        self.run_kwargs: dict = {}
        _RecordingAgent.instances.append(self)

    async def run(self, user_prompt, **kwargs):
        self.run_kwargs = kwargs
        return _Result()


@pytest.fixture(autouse=True)
def _patch_agent(monkeypatch):
    _RecordingAgent.instances = []
    monkeypatch.setattr("pydantic_ai.Agent", _RecordingAgent)


@pytest.mark.asyncio
async def test_temperature_is_passed_to_the_model_call():
    provider = _RealModelProvider(model_name="m", api_key="k", temperature=0.0)

    await provider.generate(system_prompt="s", user_prompt="u", output_type=str)

    assert _RecordingAgent.instances[0].run_kwargs["model_settings"]["temperature"] == 0.0


@pytest.mark.asyncio
async def test_no_temperature_leaves_the_provider_default_untouched():
    provider = _RealModelProvider(model_name="m", api_key="k")

    await provider.generate(system_prompt="s", user_prompt="u", output_type=str)

    assert not _RecordingAgent.instances[0].run_kwargs.get("model_settings")
