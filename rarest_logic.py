"""/rarest logic: find the single least-popular favourite.

Uses AniList's raw `popularity` count (number of users with the title on
any list) as the primary signal rather than rank, since popularity is a
continuous value that's always present, whereas a resolvable rank can
occasionally be missing for very new or niche entries.
"""
from scoring import ScoredFavourite

# (exclusive upper bound on popularity count, human-scale comparison phrase)
POPULATION_ANCHORS = [
    (50, "fewer people than fit in a single classroom"),
    (500, "fewer people than fit in a small concert hall"),
    (2_000, "fewer people than live on a single city block"),
    (5_000, "fewer people than live in a small town"),
    (20_000, "fewer people than fill a football stadium"),
    (100_000, "fewer people than live in a small city"),
    (1_000_000, "fewer people than live in a mid-sized city"),
]


def scale_comparison(popularity: int) -> str:
    for ceiling, phrase in POPULATION_ANCHORS:
        if popularity < ceiling:
            return phrase
    return "more people than live in most major cities"


def compute_rarest(favourites: list[ScoredFavourite]) -> dict:
    with_pop = [f for f in favourites if f.popularity is not None]
    if not with_pop:
        raise ValueError("No favourites with popularity data.")

    rarest = min(with_pop, key=lambda f: f.popularity)
    most_popular = max(with_pop, key=lambda f: f.popularity)

    return {
        "rarest": rarest,
        "most_popular": most_popular,
        "comparison": scale_comparison(rarest.popularity),
    }
