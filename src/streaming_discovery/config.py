"""Runtime configuration.

Matches `.env.example` at the repository root. `pydantic-settings` reads
`.env` via its built-in dotenv support -- no separate `python-dotenv`
dependency is used. Never hardcode a region, retry count, or credential in
code; add a field here instead (see CLAUDE.md).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tmdb_api_token: str
    openrouter_api_key: str
    model_name: str
    region: str = "US"
    """Watch-provider region, FR-020. Configuration value with a hardcoded
    fallback; never asked of the user."""

    # Fields with no .env.example entry yet -- defaulted, still overridable.
    llm_retry_max_attempts: int = 2
    """Bounded additional attempts on an outright LLM call failure (FR-028)."""
    demo_mode: bool = False
    """When true, the fixture-backed fakes are wired in instead of the
    real TMDB/model clients (NFR-004)."""
