"""Tests for scoring.py's /taste computation.

Regression coverage for a real bug: the score/archetype looked equally
confident regardless of how many favourites backed them, so
compute_taste must expose a sample size the card can be honest about.
"""
from scoring import ScoredFavourite, compute_taste, obscurity_score


def _favourite(title, rank):
    return ScoredFavourite(
        title=title,
        rank=rank,
        rank_scope="all-time",
        popularity=1000,
        personal_score=None,
        obscurity=obscurity_score(rank),
    )


def test_sample_size_reflects_ranked_favourite_count():
    result = compute_taste([_favourite("A", 100)])
    assert result["sample_size"] == 1

    result = compute_taste([_favourite("A", 100), _favourite("B", 200), _favourite("C", 300)])
    assert result["sample_size"] == 3


def test_sample_size_excludes_unranked_favourites():
    unranked = ScoredFavourite(
        title="No Rank", rank=None, rank_scope=None, popularity=1000, personal_score=None, obscurity=0.0
    )
    result = compute_taste([_favourite("A", 100), unranked])
    assert result["sample_size"] == 1
