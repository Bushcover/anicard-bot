"""/timeline logic: bucket COMPLETED anime into eras and label them.

Entries are grouped by year, or by 2-year buckets when the user's
completion history spans more than 4 distinct years (keeps the timeline
readable for long-time AniList users). Each era is labelled after its
most-frequent genre via a fixed genre -> phrase lookup table, falling
back to a plain "{Genre} Era" template. Fully deterministic and free --
no external calls of any kind.

If two consecutive eras would end up with the same label (their dominant
genre ties or repeats), that undercuts the point of a timeline -- showing
an arc of change. When that happens we first try the era's next-most
frequent genre instead (a real secondary signal from the same data);
if there's no distinct genre to fall back to, the two eras are merged
into one longer block instead of rendering two identical labels back to
back.
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


def era_label(genre: str) -> str:
    return GENRE_FLAVOR.get(genre, f"{genre} Era")


def _top_genre(genre_counter: Counter, avoid: set) -> str | None:
    """Most frequent genre in `genre_counter`, preferring one not in
    `avoid` if such an alternative exists. Returns None if the counter is
    empty."""
    for genre, _ in genre_counter.most_common():
        if genre not in avoid:
            return genre
    top = genre_counter.most_common(1)
    return top[0][0] if top else None


def _merge_ties(raw_eras: list[dict]) -> list[dict]:
    """Collapse consecutive eras whose dominant genre would otherwise
    repeat, trying a secondary genre first and only merging the two eras
    together when no distinct alternative exists.

    Each era's chosen `genre` is stored on the era dict as it's decided
    (avoiding the immediately preceding era's genre) rather than being
    recomputed later, since recomputing from the raw counter without that
    `avoid` context would silently undo the disambiguation."""
    eras: list[dict] = []
    for raw in raw_eras:
        era = {
            "start_year": raw["start_year"],
            "end_year": raw["end_year"],
            "genre_counter": Counter(raw["genre_counter"]),
            "titles": list(raw["titles"]),
        }
        avoid = {eras[-1]["genre"]} if eras and eras[-1]["genre"] else set()
        era["genre"] = _top_genre(era["genre_counter"], avoid)
        eras.append(era)

        # Cascade: merging can make the combined era tie the one before
        # it too, so keep resolving backwards until neighbors differ.
        while len(eras) >= 2:
            prev, cur = eras[-2], eras[-1]
            if prev["genre"] is None or cur["genre"] is None or cur["genre"] != prev["genre"]:
                break

            # No distinct secondary genre available for `cur` -- it's a
            # continuation of the same dominant taste, not a new era.
            prev["end_year"] = cur["end_year"]
            prev["genre_counter"].update(cur["genre_counter"])
            for title in cur["titles"]:
                if title not in prev["titles"] and len(prev["titles"]) < 2:
                    prev["titles"].append(title)
            eras.pop()

            # prev's counter just grew, so its best genre may have
            # changed -- recompute it against *its* predecessor's genre.
            avoid = {eras[-2]["genre"]} if len(eras) >= 2 and eras[-2]["genre"] else set()
            prev["genre"] = _top_genre(prev["genre_counter"], avoid)

    for era in eras:
        era["label"] = era_label(era["genre"]) if era["genre"] else "Anime Era"
        del era["genre_counter"]
        del era["genre"]

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
                "titles": seen_titles,
            }
        )

    eras = _merge_ties(raw_eras)

    for i, era in enumerate(eras):
        era["color"] = ERA_COLORS[i % len(ERA_COLORS)]
        era["current"] = False
    eras[-1]["current"] = True

    return eras
