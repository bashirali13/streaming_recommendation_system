"""RecommendationAgent: scores, ranks, and packages discovered candidates
into the final recommendation set.

See specs/001-streaming-discovery-assistant/contracts/recommendation-agent.md.

Per constitution Principle II, only the *wording* of each rationale comes
from a language model; every decision that matters -- hard filtering,
soft-fit scoring, role assignment, near-duplicate exclusion, and whether
evidence for a subjective trait is weak enough to flag -- is deterministic
code, unit-testable without a model call (NFR-001).
"""

from __future__ import annotations

from pydantic import BaseModel

from streaming_discovery.contracts.candidate_media import CandidateMedia
from streaming_discovery.contracts.candidate_pool import CandidatePool
from streaming_discovery.contracts.enums import MediaType, RecommendationRole
from streaming_discovery.contracts.preference_profile import PreferenceProfile
from streaming_discovery.contracts.recommendation_package import (
    Recommendation,
    RecommendationPackage,
)
from streaming_discovery.llm.provider import ModelProvider, generate_with_retry

RATIONALE_SYSTEM_PROMPT = """\
You write a short, concrete rationale for one recommended title, given a
user's stated preferences and that title's overview. Name specific
matching (and, if relevant, mismatching) factors. Never invent a fact
about the title that isn't in its overview. If asked to flag weak
evidence, name the uncertainty plainly rather than overstating the match.
If "Additional notes from the user" states something to avoid (a
franchise, studio, character, or similar) and the title or overview
conflicts with it, say so plainly and prominently -- treat it as a real
problem with this pick, not a minor caveat.

CRITICAL: set for_title to the exact "Title" given below, copied
verbatim, and write your rationale ONLY about that exact title. Even if
you believe a different real movie or show would fit the user's
preferences better, you must NOT substitute it, mention it as the
recommendation, or write your rationale as if it were the subject. If
the given title is a poor match, say so honestly and specifically about
THIS title -- a weak or negative rationale about the correct title is
always the right answer; a rationale about a different title never is.
"""


class _RationaleOutput(BaseModel):
    for_title: str
    text: str
    confidence_note: str | None = None


_MAX_TITLE_MISMATCH_RETRIES = 1
"""Bounded, separate from the network-level retry generate_with_retry
already does for outright call failures (FR-028) -- this is a distinct
failure mode (a well-formed response about the wrong title), so it gets
its own, smaller bound rather than reusing max_additional_attempts."""


def _normalize_title(title: str) -> str:
    return title.strip().strip("*_\"'").strip().lower()


def _for_title_matches(claimed: str, actual: str) -> bool:
    return _normalize_title(claimed) == _normalize_title(actual)


def build_rationale_prompt(
    profile: PreferenceProfile, *, title: str, overview: str, weak_evidence: bool
) -> str:
    """Pure function so tests can compute the same key `FakeModelProvider`
    should respond to, without duplicating prompt-construction logic.
    """
    descriptors = profile.tone_descriptors + profile.setting_descriptors + profile.theme_descriptors
    lines = [f"Title: {title}", f"Overview: {overview}"]
    if profile.genres:
        lines.append(f"Wanted genres: {', '.join(profile.genres)}")
    if descriptors:
        lines.append(f"Wanted tone/setting/themes: {', '.join(descriptors)}")
    if profile.additional_notes:
        lines.append(f"Additional notes from the user: {profile.additional_notes}")
    if weak_evidence:
        lines.append("Note: the overview gives little evidence for the requested tone; say so.")
    return "\n".join(lines)


def _mentions_excluded_keyword(profile: PreferenceProfile, candidate: CandidateMedia) -> bool:
    """T091: final safety net for excluded_keywords (e.g. "Marvel"/"DC"),
    checking the candidate's title/overview/thematic_keywords -- this
    can catch a case the Discovery Agent's own bulk-item text check
    can't, since thematic_keywords is enrichment data only available
    once this agent receives the candidate, after that earlier check
    already ran on the un-enriched bulk item.
    """
    if not profile.excluded_keywords:
        return False
    haystack = " ".join([candidate.title, candidate.overview, *candidate.thematic_keywords])
    haystack = haystack.lower()
    return any(term.lower() in haystack for term in profile.excluded_keywords)


def _hard_filter(
    profile: PreferenceProfile, candidates: list[CandidateMedia]
) -> list[CandidateMedia]:
    """Re-applies hard filters as a safety net (defense in depth) even
    though the Discovery Agent already filtered -- the ranking-side half
    of FR-009.
    """
    result = []
    for candidate in candidates:
        wrong_media_type = (
            profile.media_type not in (None, MediaType.EITHER)
            and candidate.media_type != profile.media_type
        )
        if wrong_media_type:
            continue
        if set(candidate.genres) & set(profile.excluded_genres):
            continue
        if _mentions_excluded_keyword(profile, candidate):
            continue
        result.append(candidate)
    return result


def _meets_relevance_floor(profile: PreferenceProfile, candidate: CandidateMedia) -> bool:
    """T092: a candidate must reflect at least one stated theme
    descriptor to be selectable at all, not merely ranked lower --
    closing the gap where a thin, hard-filter-surviving pool got
    force-filled up to 3 picks regardless of relevance (a "hopeful,
    superhero" request's Wildcard Pick was a romance with zero
    superhero relevance, because nothing gated on it). Only gates when
    `theme_descriptors` were actually stated, and only on theme --
    `tone_descriptors` (T089's reasoning: fuzzy mood, not concrete
    subject matter) and `setting_descriptors` are both deliberately
    excluded from this floor, since spec.md User Story 2's own
    acceptance criteria require a vague, tone/setting-only request to
    still surface a weakly-evidenced pick with an honest
    `confidence_note` rather than drop it -- `theme_descriptors` is a
    starker, more binary "is this even about the right kind of story"
    signal than setting ever is, which is why only it gates outright.
    """
    if not profile.theme_descriptors:
        return True
    haystack = " ".join([candidate.overview, *candidate.thematic_keywords]).lower()
    return any(d.lower() in haystack for d in profile.theme_descriptors)


def _soft_score(profile: PreferenceProfile, candidate: CandidateMedia) -> float:
    score = candidate.vote_average
    score += 2.0 * len(set(profile.genres) & set(candidate.genres))
    descriptor_hits = _descriptor_hit_count(profile, candidate)
    score += 1.5 * descriptor_hits
    if candidate.title in profile.liked_titles:
        score += 3.0
    if candidate.title in profile.disliked_titles:
        score -= 5.0  # exact match -- Discovery already hard-excludes this case; safety net
    score -= _disliked_similarity_penalty(profile, candidate)
    return score


def _descriptors(profile: PreferenceProfile) -> list[str]:
    return profile.tone_descriptors + profile.setting_descriptors + profile.theme_descriptors


def _descriptor_hit_count(profile: PreferenceProfile, candidate: CandidateMedia) -> int:
    haystack = " ".join([candidate.overview, *candidate.thematic_keywords]).lower()
    return sum(1 for d in _descriptors(profile) if d.lower() in haystack)


def _disliked_similarity_penalty(profile: PreferenceProfile, candidate: CandidateMedia) -> float:
    """Soft deprioritization for a candidate thematically similar to a
    disliked title (User Story 3) -- distinct from the exact-title-match
    case above, which Discovery already hard-excludes. This agent cannot
    call TMDB to learn a disliked title's own genres/keywords
    (contracts/recommendation-agent.md), so "similar" is approximated the
    same way tone-descriptor matching is: a mention of the disliked
    title's name in the candidate's own overview/keywords. Weaker than
    the exact-match penalty, since it's a weaker signal.
    """
    if not profile.disliked_titles:
        return 0.0
    haystack = " ".join([candidate.overview, *candidate.thematic_keywords]).lower()
    hits = sum(1 for title in profile.disliked_titles if title.lower() in haystack)
    return 2.0 * hits


def _has_weak_tone_evidence(profile: PreferenceProfile, candidate: CandidateMedia) -> bool:
    descriptors = _descriptors(profile)
    if not descriptors:
        return False
    return _descriptor_hit_count(profile, candidate) == 0


def _is_near_duplicate(a: CandidateMedia, b: CandidateMedia) -> bool:
    return a.title.strip().lower() == b.title.strip().lower()


def _deduplicate(ranked_candidates: list[CandidateMedia]) -> list[CandidateMedia]:
    """`ranked_candidates` is already sorted best-first, so keeping the
    first occurrence of a near-duplicate title and dropping the rest
    keeps the higher-ranked one (spec.md Assumptions).
    """
    kept: list[CandidateMedia] = []
    for candidate in ranked_candidates:
        if any(_is_near_duplicate(candidate, k) for k in kept):
            continue
        kept.append(candidate)
    return kept


_ROLES_IN_PRIORITY_ORDER = (
    RecommendationRole.BEST_MATCH,
    RecommendationRole.SAFE_PICK,
    RecommendationRole.WILDCARD_PICK,
)


class RecommendationAgent:
    def __init__(self, *, provider: ModelProvider, max_additional_attempts: int) -> None:
        self._provider = provider
        self._max_additional_attempts = max_additional_attempts

    async def run(self, profile: PreferenceProfile, pool: CandidatePool) -> RecommendationPackage:
        qualifying = _hard_filter(profile, pool.candidates)
        qualifying = [c for c in qualifying if _meets_relevance_floor(profile, c)]
        ranked = sorted(qualifying, key=lambda c: _soft_score(profile, c), reverse=True)
        selected = _deduplicate(ranked)[:3]

        if not selected:
            return RecommendationPackage(
                relaxed_constraint=pool.relaxed_constraint,
                unresolved_notes="No candidates satisfied your constraints.",
            )

        picks: dict[RecommendationRole, Recommendation] = {}
        for role, candidate in zip(_ROLES_IN_PRIORITY_ORDER, selected, strict=False):
            weak_evidence = _has_weak_tone_evidence(profile, candidate)
            rationale = await self._generate_rationale(
                profile, candidate, weak_evidence=weak_evidence
            )
            picks[role] = Recommendation(
                role=role,
                candidate=candidate,
                rationale=rationale.text,
                confidence_note=rationale.confidence_note if weak_evidence else None,
            )

        return RecommendationPackage(
            best_match=picks.get(RecommendationRole.BEST_MATCH),
            safe_pick=picks.get(RecommendationRole.SAFE_PICK),
            wildcard_pick=picks.get(RecommendationRole.WILDCARD_PICK),
            applied_constraints=profile,
            relaxed_constraint=pool.relaxed_constraint,
        )

    async def _generate_rationale(
        self, profile: PreferenceProfile, candidate: CandidateMedia, *, weak_evidence: bool
    ) -> _RationaleOutput:
        prompt = build_rationale_prompt(
            profile, title=candidate.title, overview=candidate.overview, weak_evidence=weak_evidence
        )
        result = await self._call_rationale_model(prompt)
        if _for_title_matches(result.for_title, candidate.title):
            return result

        for _ in range(_MAX_TITLE_MISMATCH_RETRIES):
            retry_prompt = prompt + (
                "\n\nCorrection: your previous rationale was about a different "
                f'title. Write ONLY about "{candidate.title}" this time -- do '
                "not substitute any other movie or show."
            )
            result = await self._call_rationale_model(retry_prompt)
            if _for_title_matches(result.for_title, candidate.title):
                return result

        return _RationaleOutput(
            for_title=candidate.title,
            text=(
                f"{candidate.title} is being surfaced as a match for your stated "
                "preferences, but a detailed written rationale could not be "
                "reliably generated for it."
            ),
            confidence_note=(
                "This pick's explanation could not be generated reliably; "
                "treat the match as unverified."
            ),
        )

    async def _call_rationale_model(self, prompt: str) -> _RationaleOutput:
        return await generate_with_retry(
            self._provider,
            system_prompt=RATIONALE_SYSTEM_PROMPT,
            user_prompt=prompt,
            output_type=_RationaleOutput,
            max_additional_attempts=self._max_additional_attempts,
        )
