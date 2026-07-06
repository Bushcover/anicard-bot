"""Tests for bot.py's popularity-ranking scope selection/labeling.

Regression coverage for a real bug: /rarest displayed a bare rank number
(e.g. "#10") picked from a narrow year/format-scoped ranking, right next
to a low raw popularity count -- reading as contradictory since "#10"
looks like a top-10-all-time hit. The scope must be surfaced so the
number and the "rare" framing agree.
"""
from bot import describe_ranking_scope, select_popularity_ranking


def test_prefers_overall_all_time_ranking_when_available():
    rankings = [
        {"rank": 50, "type": "POPULAR", "format": "TV", "allTime": False, "year": 2020},
        {"rank": 5, "type": "POPULAR", "format": None, "allTime": True, "year": None},
    ]
    chosen = select_popularity_ranking(rankings)
    assert chosen["rank"] == 5
    assert describe_ranking_scope(chosen) == "all-time"


def test_falls_back_to_all_time_format_scoped_ranking():
    rankings = [
        {"rank": 100, "type": "POPULAR", "format": "TV", "allTime": True, "year": None},
    ]
    chosen = select_popularity_ranking(rankings)
    assert chosen["rank"] == 100
    assert describe_ranking_scope(chosen) == "all-time TV"


def test_falls_back_to_year_scoped_ranking_and_labels_its_scope():
    """This is exactly what happened for a real favourite with no all-time
    ranking at all -- only a narrow year+format snapshot."""
    rankings = [
        {"rank": 10, "type": "POPULAR", "format": "TV", "allTime": False, "year": 2005},
        {"rank": 64, "type": "RATED", "format": "TV", "allTime": False, "year": 2005},
    ]
    chosen = select_popularity_ranking(rankings)
    assert chosen["rank"] == 10
    assert describe_ranking_scope(chosen) == "2005 TV"


def test_no_popular_ranking_at_all_returns_none():
    rankings = [{"rank": 64, "type": "RATED", "format": "TV", "allTime": False, "year": 2005}]
    assert select_popularity_ranking(rankings) is None
    assert describe_ranking_scope(None) is None
