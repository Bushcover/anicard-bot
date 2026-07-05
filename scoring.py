"""Shared favourite data model + /taste distinctiveness scoring.

DISTINCTIVENESS FORMULA (tune RANK_CEILING to taste):

For each favourite with a known AniList "all-time popularity" rank R
(rank 1 = the single most-popular anime on the site), convert it to a
0-100 "obscurity" score on a LOG scale:

    obscurity(R) = 100 * min(1, log10(R + 1) / log10(RANK_CEILING + 1))

A log scale is used because popularity rank is extremely right-skewed:
the difference between rank 1 and rank 100 is far more meaningful than
the difference between rank 5000 and rank 5100. RANK_CEILING is the
rank treated as "maximally obscure" for scoring purposes -- favourites
ranked at or beyond it saturate at 100.

The overall taste score is the unweighted mean of each favourite's
obscurity score. Favourites with no resolvable popularity rank are
excluded from the average entirely.
"""
import math
from dataclasses import dataclass

RANK_CEILING = 5000

# (upper score bound (exclusive), archetype name, sub-label blurb)
# Blurbs describe the tier itself rather than claiming a percentile
# against "other tracked users" -- this bot is stateless and has no
# database of other users' scores to compare against honestly.
ARCHETYPES = [
    (25, "Mainstream Loyalist", "sticks close to what everyone already loves"),
    (50, "Crowd Pleaser", "leans popular with a few personal detours"),
    (75, "Balanced Voyager", "splits time between hits and hidden gems"),
    (101, "Hidden-Gem Hunter", "actively seeks out what the crowd missed"),
]


def obscurity_score(rank: int) -> float:
    rank = max(rank, 1)
    return 100 * min(1.0, math.log10(rank + 1) / math.log10(RANK_CEILING + 1))


def archetype_for(score: float) -> tuple[str, str]:
    for ceiling, name, blurb in ARCHETYPES:
        if score < ceiling:
            return name, blurb
    return ARCHETYPES[-1][1], ARCHETYPES[-1][2]


@dataclass
class ScoredFavourite:
    title: str
    rank: int | None
    popularity: int | None
    personal_score: int | None
    obscurity: float


def compute_taste(favourites: list[ScoredFavourite]) -> dict:
    ranked = [f for f in favourites if f.rank is not None]
    if not ranked:
        raise ValueError("No favourites with a resolvable popularity rank.")

    overall = round(sum(f.obscurity for f in ranked) / len(ranked))
    name, blurb = archetype_for(overall)
    driven_by = sorted(ranked, key=lambda f: f.rank, reverse=True)[:3]

    return {
        "score": overall,
        "archetype": name,
        "archetype_blurb": blurb,
        "driven_by": driven_by,
    }
