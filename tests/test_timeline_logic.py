"""Tests for timeline_logic.py's era labeling.

Covers two real bugs found against live AniList data:

1. Two consecutive eras both ended up labelled "Deep Drama" because a
   genre tie was resolved identically for both buckets, defeating the
   point of a timeline (showing an arc of change).
2. The fix for #1 (avoid the immediately preceding era's genre) could
   still collide two eras later (a 3rd era ping-ponging back to a label
   used two eras ago), and forced a technically-distinct-but-less-honest
   runner-up genre even when the true top genre was clearly dominant.
   The current approach reflects the top TWO genres in the label when
   they're close, instead of picking just one and hoping it looks
   different from its neighbor.
"""
from timeline_logic import build_eras


def test_clearly_dominant_genre_gets_a_single_label():
    entries = [(2019, ["Action"], f"title{i}") for i in range(8)] + [
        (2019, ["Adventure"], "side-title")
    ]
    eras = build_eras(entries)
    assert eras[0]["label"] == "Action Rising"


def test_close_top_two_genres_get_a_blended_label():
    """Mirrors a real account's data: Comedy(97) vs Romance(94) out of 200
    entries -- only a 1.5-point gap, well under the blend threshold."""
    entries = [(2023, ["Comedy", "Romance"], f"both{i}") for i in range(94)]
    entries += [(2023, ["Comedy"], f"comedy_only{i}") for i in range(3)]
    eras = build_eras(entries)
    assert eras[0]["label"] == "Comedy & Romance Era"


def test_three_way_near_tie_still_only_blends_top_two():
    entries = [
        (2019, ["Drama", "Romance", "Sci-Fi"], "A"),
        (2019, ["Drama", "Romance", "Sci-Fi"], "B"),
    ]
    eras = build_eras(entries)
    assert eras[0]["label"] == "Drama & Romance Era"


def test_non_adjacent_collision_no_longer_happens_via_blending():
    """Regression test for the real bug: three eras whose top-two genres
    ping-pong (Comedy/Drama, then Comedy/Romance, then Romance/Comedy)
    used to collide on "Comic Relief" for the 1st and 3rd (non-adjacent)
    eras once the 2nd era's avoidance forced it onto "Heart Eyes". With
    blending, each era's label reflects its own close top-2 split and
    the three end up distinct.
    """
    entries = []
    # 2021-2022: Comedy 26, Drama 23 (close -> blend)
    entries += [(2021, ["Comedy"], f"c1_{i}") for i in range(3)]
    entries += [(2021, ["Comedy", "Drama"], f"cd1_{i}") for i in range(23)]
    # 2023-2024: Comedy 97, Romance 94 (close -> blend)
    entries += [(2023, ["Comedy"], f"c2_{i}") for i in range(3)]
    entries += [(2023, ["Comedy", "Romance"], f"cr2_{i}") for i in range(94)]
    # 2025-2026: Romance 61, Comedy 60 (close -> blend, order flips)
    entries += [(2025, ["Romance"], f"r3_{i}") for i in range(1)]
    entries += [(2025, ["Romance", "Comedy"], f"rc3_{i}") for i in range(60)]

    eras = build_eras(entries)
    labels = [era["label"] for era in eras]
    assert labels == ["Comedy & Drama Era", "Comedy & Romance Era", "Romance & Comedy Era"]
    assert len(labels) == len(set(labels))


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
