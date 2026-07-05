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
import rarest_logic  # noqa: E402
import scoring  # noqa: E402
import timeline_logic  # noqa: E402


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

        # /taste
        taste_result = scoring.compute_taste(favourites)
        taste_ctx = {
            "score": taste_result["score"],
            "archetype": taste_result["archetype"],
            "archetype_blurb": taste_result["archetype_blurb"],
            "driven_by": taste_result["driven_by"],
            "user_tag": anicard_bot.user_tag(user["id"]),
            "username": user["name"],
            "issued_date": anicard_bot.issued_date(),
        }
        (out_dir / "taste.png").write_bytes(await renderer.render("taste.html", taste_ctx))
        print("Wrote taste.png:", taste_ctx["score"], taste_ctx["archetype"])

        # /rarest
        rarest_result = rarest_logic.compute_rarest(favourites)
        rare = rarest_result["rarest"]
        popular = rarest_result["most_popular"]
        description = f"Only ~{rare.popularity:,} users have this on their list — {rarest_result['comparison']}."
        personal = anicard_bot.format_personal_score(rare.personal_score, score_format)
        if personal:
            description += f" You rated it {personal}."
        rarest_ctx = {
            "user_tag": anicard_bot.user_tag(user["id"]),
            "username": user["name"],
            "title": rare.title,
            "rank_text": f"#{rare.rank:,}" if rare.rank else "unranked",
            "description": description,
            "most_popular_title": popular.title,
            "most_popular_rank_text": f"#{popular.rank:,}" if popular.rank else "unranked",
            "issued_date": anicard_bot.issued_date(),
        }
        (out_dir / "rarest.png").write_bytes(await renderer.render("rarest.html", rarest_ctx))
        print("Wrote rarest.png:", rare.title)

        # /timeline
        entries = anicard_bot.build_completed_entries(data)
        eras = timeline_logic.build_eras(entries)
        timeline_ctx = {
            "username": user["name"],
            "year_range": f"{eras[0]['start_year']} — {eras[-1]['end_year']}",
            "eras": eras,
            "issued_date": anicard_bot.issued_date(),
        }
        (out_dir / "timeline.png").write_bytes(await renderer.render("timeline.html", timeline_ctx))
        print("Wrote timeline.png:", len(eras), "eras")
    finally:
        await renderer.stop()


if __name__ == "__main__":
    asyncio.run(main())
