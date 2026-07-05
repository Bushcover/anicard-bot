"""/timeline logic: bucket COMPLETED anime into eras and label them.

Entries are grouped by year, or by 2-year buckets when the user's
completion history spans more than 4 distinct years (keeps the timeline
readable for long-time AniList users). Each era is labelled after its
most-frequent genre via a fixed genre -> phrase lookup table, falling
back to a plain "{Genre} Era" template. Fully deterministic and free --
no external calls of any kind.
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

    eras = []
    for idx in sorted(buckets):
        items = buckets[idx]
        start_year = base_year + idx * bucket_size
        end_year = min(start_year + bucket_size - 1, years[-1])

        genre_counter = Counter()
        for _, genres, _ in items:
            genre_counter.update(genres)
        top_genre = genre_counter.most_common(1)[0][0] if genre_counter else "Anime"

        seen_titles = []
        for _, _, title in sorted(items, key=lambda x: x[0]):
            if title not in seen_titles:
                seen_titles.append(title)
            if len(seen_titles) == 2:
                break

        eras.append(
            {
                "start_year": start_year,
                "end_year": end_year,
                "label": era_label(top_genre),
                "titles": seen_titles,
                "current": False,
            }
        )

    for i, era in enumerate(eras):
        era["color"] = ERA_COLORS[i % len(ERA_COLORS)]
    eras[-1]["current"] = True

    return eras
