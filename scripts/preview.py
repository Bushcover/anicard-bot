"""Render all three AniCard templates for a real AniList username, without
needing Discord at all. Useful for sanity-checking data + design locally.

Usage:
    python scripts/preview.py <anilist_username> [output_dir]
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bot as anicard_bot  # noqa: E402  (path must be set up first)
from anilist import fetch_user_bundle  # noqa: E402
from render.renderer import CardRenderer  # noqa: E402


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    username = sys.argv[1]
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching AniList data for '{username}'...")
    data = await fetch_user_bundle(username)
    user = data["User"]
    score_format = (user.get("mediaListOptions") or {}).get("scoreFormat", "POINT_10")

    renderer = CardRenderer()
    await renderer.start()
    try:
        score_lookup = anicard_bot.build_score_lookup(data)
        favourites = anicard_bot.build_favourites(data, score_lookup)

        taste_ctx = anicard_bot.build_taste_context(data, favourites)
        (out_dir / "taste.png").write_bytes(await renderer.render("taste.html", taste_ctx))
        print("Wrote taste.png:", taste_ctx["score"], taste_ctx["archetype"])

        rarest_ctx = anicard_bot.build_rarest_context(data, favourites, score_format)
        (out_dir / "rarest.png").write_bytes(await renderer.render("rarest.html", rarest_ctx))
        print("Wrote rarest.png:", rarest_ctx["title"])

        entries = anicard_bot.build_completed_entries(data)
        timeline_ctx = anicard_bot.build_timeline_context(data, entries)
        (out_dir / "timeline.png").write_bytes(await renderer.render("timeline.html", timeline_ctx))
        print("Wrote timeline.png:", len(timeline_ctx["eras"]), "eras")
    finally:
        await renderer.stop()


if __name__ == "__main__":
    asyncio.run(main())
