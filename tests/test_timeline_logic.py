"""Tests for timeline_logic.py's era disambiguation/merge logic.

Regression coverage for a real bug: two consecutive eras both ended up
labelled "Deep Drama" against real AniList data because a genre tie was
resolved identically for both buckets, defeating the point of a timeline
(showing an arc of change).
"""
from timeline_logic import build_eras


def test_consecutive_ties_get_distinct_labels_via_secondary_genre():
    # 6 distinct years -> 2-year buckets: [2017-18] [2019-20] [2021-22].
    entries = [
        (2017, ["Action"], "Z"),
        (2018, ["Action"], "Y"),
        # 2019-2020: Drama ties with Romance/Sci-Fi at the top.
        (2019, ["Drama", "Romance", "Sci-Fi"], "A"),
        (2019, ["Drama", "Romance", "Sci-Fi"], "B"),
        # 2021-2022: Drama is the outright top genre, but Slice of Life is
        # a real, distinct secondary signal in the same data.
        (2021, ["Drama", "Slice of Life"], "C"),
        (2021, ["Drama", "Slice of Life"], "D"),
        (2022, ["Drama"], "E"),
    ]
    eras = build_eras(entries)
    labels = [era["label"] for era in eras]
    adjacent_pairs = list(zip(labels, labels[1:]))
    assert all(a != b for a, b in adjacent_pairs), f"consecutive eras must not repeat a label: {labels}"
    assert labels == ["Action Rising", "Deep Drama", "Slower Days"]


def test_true_genre_tie_with_no_alternative_merges_instead_of_repeating():
    entries = [
        (2019, ["Drama"], "A"),
        (2020, ["Drama"], "B"),
        (2021, ["Drama"], "C"),
        (2022, ["Drama"], "D"),
    ]
    eras = build_eras(entries)
    labels = [era["label"] for era in eras]
    assert len(labels) == len(set(labels))
    # With no secondary genre ever available, merging into one era is the
    # only way to avoid a repeated label.
    assert len(eras) == 1
    assert eras[0]["start_year"] == 2019
    assert eras[0]["end_year"] == 2022


def test_current_era_is_always_the_last_one():
    entries = [
        (2019, ["Action"], "A"),
        (2023, ["Romance"], "B"),
    ]
    eras = build_eras(entries)
    assert eras[-1]["current"] is True
    assert all(not era["current"] for era in eras[:-1])
