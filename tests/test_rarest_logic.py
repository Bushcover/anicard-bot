"""Tests for rarest_logic.py.

Regression coverage for a real bug: with only one (distinct) favourite,
"rarest" and "most popular" are trivially the same entry, and the card
was still rendering a contrast row comparing it to itself.
"""
from rarest_logic import compute_rarest
from scoring import ScoredFavourite


def _favourite(title, popularity, rank=None):
    return ScoredFavourite(
        title=title,
        rank=rank,
        rank_scope=None,
        popularity=popularity,
        personal_score=None,
        obscurity=0.0,
    )


def test_single_favourite_has_no_most_popular_contrast():
    favourites = [_favourite("Mushishi", 2_900)]
    result = compute_rarest(favourites)
    assert result["rarest"].title == "Mushishi"
    assert result["most_popular"] is None


def test_multiple_distinct_favourites_still_contrast_normally():
    favourites = [
        _favourite("Mushishi", 2_900),
        _favourite("Attack on Titan", 500_000),
    ]
    result = compute_rarest(favourites)
    assert result["rarest"].title == "Mushishi"
    assert result["most_popular"].title == "Attack on Titan"


def test_all_favourites_tied_on_popularity_also_has_no_contrast():
    """Every favourite sharing the same popularity count means there's no
    meaningful "most popular" to contrast against either."""
    favourites = [_favourite("A", 1_000), _favourite("B", 1_000)]
    result = compute_rarest(favourites)
    assert result["most_popular"] is None
