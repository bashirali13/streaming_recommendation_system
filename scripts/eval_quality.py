"""Live end-to-end quality check against a fixed set of prompts (the "gold set").

Not part of the test suite (it needs real credentials and the network). Run:

    uv run python scripts/eval_quality.py            # full set
    uv run python scripts/eval_quality.py --core     # core prompts only
    uv run python scripts/eval_quality.py --show     # also print every pick

For each prompt it runs the real pipeline (real preference model, real TMDB),
with a stub in place of the per-pick rationale model, and checks that:
  * the Preference Agent understood the request (`expect`),
  * at least 3 picks came back, without relaxing anything,
  * every pick actually satisfies the stated facts (genre, year, provider,
    runtime, format, exclusions, season cap).
`expect` is the answer key: what a person means by the prompt.
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from collections import Counter
from datetime import date

from streaming_discovery.agents.recommendation_agent import RecommendationAgent, _RationaleOutput
from streaming_discovery.cli.output import build_orchestrator
from streaming_discovery.config import Settings
from streaming_discovery.llm.provider import ModelCallError
from streaming_discovery.tmdb.client import TmdbAdapterError

Y = date.today().year

# tier "core": things the tool should already get right.
# tier "stretch": harder or vaguer requests; reported separately.
GOLD: list[dict] = [
    # ---- facts only (movies)
    {
        "p": "Romance movie on Netflix or Hulu, after 1990",
        "media": "movie",
        "providers": ["netflix", "hulu"],
        "genres": ["Romance"],
        "year_min": [1990, 1991],
    },
    {
        "p": "A romance movie under 2 hours on Hulu",
        "media": "movie",
        "providers": ["hulu"],
        "genres": ["Romance"],
        "runtime_max": 120,
    },
    {
        "p": "Comedy movie from the 90s",
        "media": "movie",
        "genres": ["Comedy"],
        "year_min": [1990],
        "year_max": [1999],
    },
    {
        "p": "Horror movie on Netflix",
        "media": "movie",
        "providers": ["netflix"],
        "genres": ["Horror"],
    },
    {
        "p": "A war movie released after 2000",
        "media": "movie",
        "genres": ["War"],
        "year_min": [2000, 2001],
    },
    {"p": "Animated family movie", "media": "movie", "genres": ["Animation", "Family"]},
    {
        "p": "Sci-fi movie from the last 5 years",
        "media": "movie",
        "genres": ["Science Fiction"],
        "year_min": [Y - 5],
    },
    {
        "p": "A thriller movie under 100 minutes",
        "media": "movie",
        "genres": ["Thriller"],
        "runtime_max": 100,
    },
    {
        "p": "Action movie on Amazon Prime Video",
        "media": "movie",
        "providers": ["prime"],
        "genres": ["Action"],
    },
    {"p": "A documentary movie about nature", "media": "movie", "genres": ["Documentary"]},
    {
        "p": "A Korean thriller movie",
        "media": "movie",
        "genres": ["Thriller"],
        "languages": ["korean"],
    },
    {
        "p": "Spanish-language drama movie",
        "media": "movie",
        "genres": ["Drama"],
        "languages": ["spanish"],
    },
    {
        "p": "Fantasy movie from before 2000",
        "media": "movie",
        "genres": ["Fantasy"],
        "year_max": [1999, 2000],
    },
    {
        "p": "A western movie on Netflix",
        "media": "movie",
        "providers": ["netflix"],
        "genres": ["Western"],
    },
    {
        "p": "A romantic comedy movie on Netflix",
        "media": "movie",
        "providers": ["netflix"],
        "genres": ["Romance", "Comedy"],
    },
    {
        "p": "Crime movie, nothing horror",
        "media": "movie",
        "genres": ["Crime"],
        "excluded": ["Horror"],
    },
    {
        "p": "Comedy movie but not animated",
        "media": "movie",
        "genres": ["Comedy"],
        "excluded": ["Animation"],
    },
    # ---- facts only (TV)
    {
        "p": "A crime TV series, no more than 3 seasons",
        "media": "tv",
        "genres": ["Crime"],
        "season_max": 3,
    },
    {
        "p": "Mystery TV series on Netflix",
        "media": "tv",
        "providers": ["netflix"],
        "genres": ["Mystery"],
    },
    {"p": "A romance TV series", "media": "tv", "genres": ["Romance"]},
    {"p": "Sci-fi TV show", "media": "tv", "genres": ["Science Fiction"]},
    {"p": "Anime series", "media": "tv", "genres": ["Animation"]},
    {"p": "A comedy TV series on Hulu", "media": "tv", "providers": ["hulu"], "genres": ["Comedy"]},
    {
        "p": "Documentary series on Netflix",
        "media": "tv",
        "providers": ["netflix"],
        "genres": ["Documentary"],
    },
    {"p": "Horror TV show", "media": "tv", "genres": ["Horror"]},
    # ---- facts plus mood words (the case that broke)
    {
        "p": "A sweet, passionate romance movie on Netflix",
        "media": "movie",
        "providers": ["netflix"],
        "genres": ["Romance"],
    },
    {
        "p": "Something cozy and funny: a comedy movie on Hulu",
        "media": "movie",
        "providers": ["hulu"],
        "genres": ["Comedy"],
    },
    {"p": "A dark, gritty crime thriller movie", "media": "movie", "genres": ["Crime", "Thriller"]},
    {"p": "A feel-good family movie", "media": "movie", "genres": ["Family"]},
    {"p": "An atmospheric, slow-burn mystery TV show", "media": "tv", "genres": ["Mystery"]},
    {
        "p": "A romantic movie, something heartwarming, under 2 hours",
        "media": "movie",
        "genres": ["Romance"],
        "runtime_max": 120,
    },
    {"p": "Romance", "genres": ["Romance"]},
    {
        "p": "A passionate romance, Netflix or Hulu, after 1991",
        "providers": ["netflix", "hulu"],
        "genres": ["Romance"],
        "year_min": [1991, 1992],
    },
    # ---- stretch: vaguer, or needs more than plain filters
    {
        "p": "Movies like Inception, only on Netflix, released after 2015",
        "tier": "stretch",
        "media": "movie",
        "providers": ["netflix"],
        "year_min": [2015, 2016],
    },
    {
        "p": "Movies like Knives Out on Hulu",
        "tier": "stretch",
        "media": "movie",
        "providers": ["hulu"],
    },
    {"p": "Show me something to watch tonight", "tier": "stretch"},
    {"p": "A cozy comfort watch", "tier": "stretch"},
    {
        "p": "Surprise me with a well-reviewed movie from the 90s",
        "tier": "stretch",
        "media": "movie",
        "year_min": [1990],
        "year_max": [1999],
    },
    {
        "p": "A mind-bending sci-fi movie",
        "tier": "stretch",
        "media": "movie",
        "genres": ["Science Fiction"],
    },
]

# Genres that TMDB only offers as a combined TV genre, or not at all on TV.
_TV_GENRE_ALIASES = {
    "science fiction": ["sci-fi & fantasy"],
    "fantasy": ["sci-fi & fantasy"],
    "action": ["action & adventure"],
    "adventure": ["action & adventure"],
    "war": ["war & politics"],
}


class _StubRationale:
    """Stands in for the rationale model so the check is fast and free."""

    async def generate(self, *, system_prompt: str, user_prompt: str, output_type):
        title = re.search(r"^Title: (.*)$", user_prompt, re.M).group(1)
        return _RationaleOutput(for_title=title, text="(eval stub)", confidence_note=None)


def _profile_ok(profile, g: dict) -> list[str]:
    bad = []
    if "media" in g and (profile.media_type is None or profile.media_type.value != g["media"]):
        bad.append(f"media={profile.media_type}")
    for want in g.get("providers", []):
        if not any(want in p.lower() for p in profile.providers):
            bad.append(f"provider {want} missing")
    have = {x.lower() for x in profile.genres}
    for want in g.get("genres", []):
        if want.lower() not in have:
            bad.append(f"genre {want} missing")
    for want in g.get("excluded", []):
        if want.lower() not in {x.lower() for x in profile.excluded_genres}:
            bad.append(f"excluded {want} missing")
    for key, attr in (("year_min", "year_min"), ("year_max", "year_max")):
        if key in g and getattr(profile, attr) not in g[key]:
            bad.append(f"{attr}={getattr(profile, attr)}")
    if "runtime_max" in g and profile.runtime_max_minutes != g["runtime_max"]:
        bad.append(f"runtime_max={profile.runtime_max_minutes}")
    for want in g.get("languages", []):
        if not any(want in lang.lower() for lang in profile.languages):
            bad.append(f"language {want} missing")
    if "season_max" in g and profile.season_count_max != g["season_max"]:
        bad.append(f"season_max={profile.season_count_max}")
    return bad


def _genre_ok(c, want: str) -> bool:
    genres = {x.lower() for x in c.genres}
    w = want.lower()
    if w in genres:
        return True
    if c.media_type.value == "tv":
        if any(a in genres for a in _TV_GENRE_ALIASES.get(w, [])):
            return True
        if w in {"romance", "horror", "thriller", "history", "music"}:
            return any(w in k.lower() for k in c.thematic_keywords)
    return False


def _pick_problems(c, g: dict) -> list[str]:
    bad = []
    if "media" in g and c.media_type.value != g["media"]:
        bad.append("wrong format")
    for want in g.get("genres", []):
        if not _genre_ok(c, want):
            bad.append(f"not {want}")
    for ex in g.get("excluded", []):
        if ex.lower() in {x.lower() for x in c.genres}:
            bad.append(f"is {ex}")
    yr = c.release_year
    if yr is not None:
        if "year_min" in g and yr < min(g["year_min"]):
            bad.append(f"year {yr} too old")
        if "year_max" in g and yr > max(g["year_max"]):
            bad.append(f"year {yr} too new")
    if g.get("providers") and not any(
        w in n.lower() for w in g["providers"] for n in c.provider_names
    ):
        bad.append("not on requested service")
    if "runtime_max" in g and c.runtime_minutes is not None and c.media_type.value == "movie":
        if c.runtime_minutes > g["runtime_max"]:
            bad.append(f"{c.runtime_minutes} min")
    if "season_max" in g and c.season_count is not None and c.season_count > g["season_max"]:
        bad.append(f"{c.season_count} seasons")
    return bad


async def _run_one(sem, g: dict) -> dict:
    async with sem:
        o = build_orchestrator(Settings())
        o._recommendation_agent = RecommendationAgent(
            provider=_StubRationale(), max_additional_attempts=0
        )
        out = {"g": g, "error": None, "picks": [], "relaxed": None, "profile_bad": [], "note": None}
        try:
            pkg = await o.run_single_attempt(raw_user_input=g["p"])
        except (TmdbAdapterError, ModelCallError, Exception) as exc:  # noqa: BLE001
            out["error"] = f"{type(exc).__name__}: {str(exc)[:100]}"
            return out
        profile = o.session.preference_profile
        out["profile_bad"] = _profile_ok(profile, g) if profile else ["no profile"]
        out["relaxed"] = pkg.relaxed_constraint.value if pkg.relaxed_constraint else None
        out["note"] = pkg.unresolved_notes
        for pick in (pkg.best_match, pkg.safe_pick, pkg.wildcard_pick):
            if pick:
                out["picks"].append((pick.candidate, _pick_problems(pick.candidate, g)))
        return out


async def main(core_only: bool, show: bool) -> None:
    gold = [g for g in GOLD if not (core_only and g.get("tier") == "stretch")]
    sem = asyncio.Semaphore(4)
    results = await asyncio.gather(*(_run_one(sem, g) for g in gold))

    title_counts = Counter(c.title for r in results for c, _ in r["picks"])
    popular = {t for t, n in title_counts.items() if n >= max(3, 0.15 * len(results))}

    rows = {"core": [], "stretch": []}
    n_picks = n_pick_ok = n_repeat = 0
    for r in results:
        g = r["g"]
        problems = [p for _, ps in r["picks"] for p in ps]
        enough = len(r["picks"]) >= 3
        clean = (
            not r["error"] and not r["profile_bad"] and enough and not r["relaxed"] and not problems
        )
        n_picks += len(r["picks"])
        n_pick_ok += sum(1 for _, ps in r["picks"] if not ps)
        n_repeat += sum(1 for c, _ in r["picks"] if c.title in popular)
        rows[g.get("tier", "core")].append((clean, r, enough, problems))

    def line(clean, r, enough, problems):
        why = []
        if r["error"]:
            why.append(r["error"])
        if r["profile_bad"]:
            why.append("understood wrong: " + ", ".join(r["profile_bad"]))
        if not enough:
            why.append(f"only {len(r['picks'])} picks")
        if r["relaxed"]:
            why.append(f"relaxed {r['relaxed']}")
        if problems:
            why.append(f"{len(problems)} bad pick(s): " + ", ".join(sorted(set(problems))))
        return f"{'PASS' if clean else 'FAIL'}  {r['g']['p']}" + (
            "" if clean else "\n        -> " + "; ".join(why)
        )

    for tier in ("core", "stretch"):
        if not rows[tier]:
            continue
        print(f"\n=== {tier.upper()} ===")
        for clean, r, enough, problems in rows[tier]:
            print(line(clean, r, enough, problems))
            if show:
                for c, ps in r["picks"]:
                    print(
                        f"        {c.title} ({c.release_year}, {c.media_type.value}) {c.genres} "
                        + (f"BAD: {','.join(ps)}" if ps else "")
                    )

    print("\n=== SUMMARY ===")
    for tier in ("core", "stretch"):
        if rows[tier]:
            passed = sum(1 for x in rows[tier] if x[0])
            print(
                f"{tier:8} prompts fully right: {passed}/{len(rows[tier])} "
                f"= {100 * passed // len(rows[tier])}%"
            )
    allr = rows["core"] + rows["stretch"]
    print(
        f"understood correctly     : {sum(1 for x in allr if not x[1]['profile_bad'])}/{len(allr)}"
    )
    print(
        f">=3 picks, no relaxing   : "
        f"{sum(1 for x in allr if x[2] and not x[1]['relaxed'])}/{len(allr)}"
    )
    print(f"needed a relaxed retry   : {sum(1 for x in allr if x[1]['relaxed'])}/{len(allr)}")
    print(
        f"picks satisfying request : {n_pick_ok}/{n_picks} = {100 * n_pick_ok // max(1, n_picks)}%"
    )
    print(f"picks that are 'usual suspects' (same title in >=15% of prompts): {n_repeat}/{n_picks}")
    if popular:
        print("  usual suspects:", ", ".join(sorted(popular)))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--core", action="store_true")
    ap.add_argument("--show", action="store_true")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    asyncio.run(main(a.core, a.show))
