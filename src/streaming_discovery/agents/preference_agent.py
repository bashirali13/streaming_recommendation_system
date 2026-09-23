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
  Thriller, TV Movie, War, War & Politics, Western. "Only use one of
  these exact names" means normalize a close synonym to the matching
  official name, not skip genres entirely when the user's own wording
  doesn't match verbatim -- e.g. "cartoon", "cartoon animation",
  "animated", and "anime" all mean the genre "Animation" and MUST be
  normalized to it; "rom-com" means "Romance" and "Comedy" (both);
  "sci-fi" means "Science Fiction". Only drop a genre-sounding word
  entirely if it truly has no reasonable official-list equivalent.
- CRITICAL: whatever the user says the content should be ABOUT --
  subject matter, content category, or character type, not just mood --
  must end up SOMEWHERE, never silently dropped. If it exactly matches
  one of the genre names above, use genres. If it does NOT (this
  includes plenty of ordinary content-category words that are not
  official genre names, e.g. "superhero", "heist", "zombie", "spy",
  "true crime", "coming-of-age"), it still MUST go in theme_descriptors
  -- do not treat "not an official genre" as a reason to drop it or as
  meaning it doesn't belong anywhere. Concrete example: "I want a
  superhero movie" -> genres: [] (since "Superhero" is not in the list
  above), theme_descriptors: ["superhero"] (never theme_descriptors: []
  -- the core subject of the request must not vanish).
- theme_descriptors is ONLY for concrete, nameable subject matter -- a
  premise, setting, character type, or plot element you could point to
  in the film itself (heist, zombie, road trip, spy, found family).
  Words describing a film's REPUTATION, ERA-FEEL, or overall QUALITY --
  "classic", "cult", "iconic", "acclaimed", "underrated", "timeless",
  "beloved", "nostalgic", "feel-good" -- are NOT subject matter and
  belong in tone_descriptors instead, exactly like "dark"/"gritty"/
  "cozy"/"atmospheric" already do. This distinction matters downstream:
  theme_descriptors drives an actual search filter and can rule a title
  out entirely, while tone_descriptors only ever affects ranking and
  explanation text. A word describing how OLD or how WELL-REGARDED a
  film is must never be treated as if it names what the film is about.
  Concrete example: "a classic family movie" -> theme_descriptors: []
  (no concrete subject was named), tone_descriptors: ["classic"] (never
  theme_descriptors: ["classic"] -- "classic" describes reputation/era,
  not subject matter, and using it as a hard search filter eliminates
  older titles that were never tagged with a literal "classic" keyword
  by the underlying database, even when they're exactly what the user
  wants).
- If the user excludes something that is NOT one of those exact genre
  names -- a franchise, cinematic universe, studio, character, real
  actor, director, or similar -- put each excluded thing in
  excluded_keywords, one item per thing excluded, never in
  excluded_genres and never only described in additional_notes.
  Concrete example: "not Marvel or DC" -> excluded_keywords: ["Marvel",
  "DC"] (two separate items, not one combined string, and never left
  describing this only in additional_notes). A real person's name (an
  actor or director the user wants avoided, e.g. "nothing with Jason
  Statham") belongs here too, using their name exactly as given --
  excluded_keywords: ["Jason Statham"], never additional_notes. An
  explicit exclusion always belongs in a field a downstream filter can
  actually enforce.
- If the user specifies a language for the movie or show itself (e.g.
  "in Spanish", "a Korean drama", "French films", "something in its
  original Japanese"), put it in languages using the language's common
  English name (e.g. "Spanish", "Korean", "French", "Japanese") -- never
  in theme_descriptors, setting_descriptors, or additional_notes. Do NOT
  populate languages from an incidental mention that isn't a request
  about the content's own language (e.g. a setting like "set in Japan"
  or a franchise mention does not imply a language preference).
- additional_notes is for context that doesn't fit any other field
  (e.g. "watching with my kids," "on a rainy day") -- never use it as a
  place to describe an exclusion or the core subject of the request;
  genres/theme_descriptors/excluded_genres/excluded_keywords/languages/
  disliked_titles exist for that and are the only fields anything
  downstream actually reads to filter or rank candidates.
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
