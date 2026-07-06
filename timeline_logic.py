"""/timeline logic: bucket COMPLETED anime into eras and label them.

Entries are grouped by year, or by 2-year buckets when the user's
completion history spans more than 4 distinct years (keeps the timeline
readable for long-time AniList users). Fully deterministic and free --
no external calls of any kind.

Each era's label is picked from its genre distribution alone, independent
of neighboring eras:

- If the top genre clearly dominates the runner-up (more than
  BLEND_GAP_THRESHOLD percentage points of the era's entries), the label
  is that single genre's flavor phrase (e.g. "Comic Relief").
- Otherwise the top two genres are close enough that picking just one
  would overstate how one-note the era actually was, so the label blends
  both, e.g. "Comedy & Romance Era".

An earlier version tried to keep adjacent eras visually distinct by
avoiding whichever single genre the previous era used, falling back to a
weaker runner-up genre purely to look different. That's technically
distinct but less honest -- it can pick a genre that covered a minority
of the era's entries just to avoid a repeat. The blend reflects more of
the real signal instead, and as a side effect two eras collide on a label
far less often, since the exact pair (and its order, which follows which
genre led) has to match rather than just a single genre. Two eras with a
genuinely identical distribution (no secondary signal at all, e.g. every
single entry tagged only "Drama") can still land on the same label; that
case is merged into one longer era rather than rendered twice.
"""
from collections import Counter, defaultdict

GENRE_FLAVOR = {
    "Action": "Action Rising",
    "Adventure": "Adventure Bound",
    "Comedy": "Comic Relief",
    "Drama": "Deep Drama",
    "Ecchi": "Guilty Pleasures",
    "Fantasy": "Fantasy Bound",
    "Horror": "Nightmare Fuel",
    "Mahou Shoujo": "Magical Streak",
    "Mecha": "Mecha Overdrive",
    "Music": "On Repeat",
    "Mystery": "Mystery Hour",
    "Psychological": "Mind Games",
    "Romance": "Heart Eyes",
    "Sci-Fi": "Sci-Fi Surge",
    "Slice of Life": "Slower Days",
    "Sports": "Full Sprint",
    "Supernatural": "Supernatural Streak",
    "Thriller": "Edge of the Seat",
}

ERA_COLORS = ["#f87171", "#38bdf8", "#fbbf24", "#a78bfa", "#34d399", "#fb923c"]

# How many percentage points (of the era's entry count) the top genre
# must lead the runner-up by by to get a single-genre label. Below this,
# the two genres are close enough that a blended label is more honest.
BLEND_GAP_THRESHOLD = 18


def era_label(genre: str) -> str:
    return GENRE_FLAVOR.get(genre, f"{genre} Era")


def _label_for_era(genre_counter: Counter, total_entries: int) -> str:
    ranked = genre_counter.most_common()
    if not ranked:
        return "Anime Era"

    top_genre, top_count = ranked[0]
    if len(ranked) == 1:
        return era_label(top_genre)

    second_genre, second_count = ranked[1]
    gap = 100 * (top_count - second_count) / total_entries
    if gap > BLEND_GAP_THRESHOLD:
        return era_label(top_genre)
    return f"{top_genre} & {second_genre} Era"


def _merge_adjacent_duplicate_labels(raw_eras: list[dict]) -> list[dict]:
    """Each era's label is computed from its own genre distribution alone.
    That makes two eras colliding on a label rare, but a genuinely
    identical distribution (no secondary genre at all) can still repeat
    the immediately preceding label -- merge those together rather than
    rendering the same label twice in a row."""
    eras: list[dict] = []
    for raw in raw_eras:
        era = {
            "start_year": raw["start_year"],
            "end_year": raw["end_year"],
            "genre_counter": Counter(raw["genre_counter"]),
            "total_entries": raw["total_entries"],
            "titles": list(raw["titles"]),
        }
        era["label"] = _label_for_era(era["genre_counter"], era["total_entries"])
        eras.append(era)

        # Cascade: merging can make the combined era tie the one before
        # it too, so keep resolving backwards until neighbors differ.
        while len(eras) >= 2 and eras[-1]["label"] == eras[-2]["label"]:
            cur = eras.pop()
            prev = eras[-1]
            prev["end_year"] = cur["end_year"]
            prev["genre_counter"].update(cur["genre_counter"])
            prev["total_entries"] += cur["total_entries"]
            for title in cur["titles"]:
                if title not in prev["titles"] and len(prev["titles"]) < 2:
                    prev["titles"].append(title)
            prev["label"] = _label_for_era(prev["genre_counter"], prev["total_entries"])

    for era in eras:
        del era["genre_counter"]
        del era["total_entries"]

    return eras


def build_eras(entries: list[tuple[int, list[str], str]]) -> list[dict]:
    """entries: list of (completed_year, genres, title) for COMPLETED anime."""
    years = sorted({year for year, _, _ in entries})
    if not years:
        raise ValueError("No completed entries with a known year.")

    distinct_year_count = len(years)
    bucket_size = 1 if distinct_year_count <= 4 else 2
    base_year = years[0]

    buckets: dict[int, list[tuple[int, list[str], str]]] = defaultdict(list)
    for year, genres, title in entries:
        idx = (year - base_year) // bucket_size
        buckets[idx].append((year, genres, title))

    raw_eras = []
    for idx in sorted(buckets):
        items = buckets[idx]
        start_year = base_year + idx * bucket_size
        end_year = min(start_year + bucket_size - 1, years[-1])

        genre_counter = Counter()
        for _, genres, _ in items:
            genre_counter.update(genres)

        seen_titles = []
        for _, _, title in sorted(items, key=lambda x: x[0]):
            if title not in seen_titles:
                seen_titles.append(title)
            if len(seen_titles) == 2:
                break

        raw_eras.append(
            {
                "start_year": start_year,
                "end_year": end_year,
                "genre_counter": genre_counter,
                "total_entries": len(items),
                "titles": seen_titles,
            }
        )

    eras = _merge_adjacent_duplicate_labels(raw_eras)

    for i, era in enumerate(eras):
        era["color"] = ERA_COLORS[i % len(ERA_COLORS)]
        era["current"] = False
    eras[-1]["current"] = True

    return eras
