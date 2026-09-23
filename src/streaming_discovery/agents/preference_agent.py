"""PreferenceAgent: translates natural language and intake answers into a
structured PreferenceProfile.

See specs/001-streaming-discovery-assistant/contracts/preference-agent.md.

LLM-backed (NFR-008): the only work this class does is ask the model to
fill in a PreferenceProfile; it never calls TMDB, ranks a title, or
relaxes a constraint.
"""

from __future__ import annotations

from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.llm.provider import ModelProvider, generate_with_retry

SYSTEM_PROMPT = """\
You translate a user's streaming-discovery request into a PreferenceProfile.

Rules:
- Extract only what the user actually said. Never invent a value for a
  field the user did not address; leave it null/empty.
- Classify format, explicit exclusions, and providers as hard constraints
  by default. Classify tone, mood, thematic similarity, and recency as
  soft preferences by default.
- If the user's own language marks an otherwise-soft field as
  non-negotiable (e.g. "it MUST be...", "no exceptions"), add that
  field's name to hard_override_fields.
- If the user states a maximum season count for a TV show, always add
  "season_count_max" to hard_override_fields -- a stated season cap is
  never soft.
- genres and excluded_genres are matched against a fixed catalog
  downstream and are silently dropped if they don't match it exactly, so
  only use one of these exact names (never invent your own): Action,
  Action & Adventure, Adventure, Animation, Comedy, Crime, Documentary,
  Drama, Family, Fantasy, History, Horror, Kids, Music, Mystery, News,
  Reality, Romance, Sci-Fi & Fantasy, Science Fiction, Soap, Talk,
  Thriller, TV Movie, War, War & Politics, Western. A descriptive mood
  or vibe that isn't one of these belongs in tone_descriptors/
  setting_descriptors/theme_descriptors instead, never forced into genres.
- If the user excludes something that is NOT one of those exact genre
  names -- a franchise, cinematic universe, studio, character, or
  similar (e.g. "not Marvel or DC", "no Star Wars", "nothing from A24")
  -- put each excluded thing in excluded_keywords, one item per thing
  excluded, never in excluded_genres and never only described in
  additional_notes. An explicit exclusion always belongs in a field a
  downstream filter can actually enforce.
- additional_notes is for context that doesn't fit any other field
  (e.g. "watching with my kids," "on a rainy day") -- never use it as a
  place to describe an exclusion; excluded_genres/excluded_keywords/
  disliked_titles exist for that and are the only fields enforced as
  hard constraints downstream.
- Do not call any tool, recommend a title, or resolve a conflicting
  request yourself -- describe what was said, even if it seems to
  conflict internally.
"""


def build_preference_prompt(
    raw_user_input: str | None, intake_answers: dict[str, str | None]
) -> str:
    """Combine free text and guided-intake answers into one prompt. For a
    pure free-text request (no intake answers), this is the raw text
    unchanged, keeping fixture/test prompts simple and exact-matchable.
    Exposed (not prefixed with an underscore) so tests can compute the
    same key `FakeModelProvider` should respond to.
    """
    if not intake_answers:
        return raw_user_input or ""
    answer_lines = [f"{key}: {value}" for key, value in intake_answers.items() if value]
    parts = [raw_user_input] if raw_user_input else []
    parts.extend(answer_lines)
    return "\n".join(parts)


class PreferenceAgent:
    def __init__(self, *, provider: ModelProvider, max_additional_attempts: int) -> None:
        self._provider = provider
        self._max_additional_attempts = max_additional_attempts

    async def run(
        self, *, raw_user_input: str | None, intake_answers: dict[str, str | None]
    ) -> PreferenceProfile:
        user_prompt = build_preference_prompt(raw_user_input, intake_answers)
        return await generate_with_retry(
            self._provider,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            output_type=PreferenceProfile,
            max_additional_attempts=self._max_additional_attempts,
        )
