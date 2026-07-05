"""AniCard: a stateless Discord bot with /taste, /rarest, /timeline.

All three commands take a required AniList `username` and render a PNG
card from live AniList data. No database, no account linking.
"""
import io
import logging
import os
from datetime import date

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

import rarest_logic
import scoring
import timeline_logic
from anilist import AniListError, UserNotFoundError, fetch_user_bundle
from render.renderer import CardRenderer

load_dotenv()

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("anicard")

TOKEN = os.environ.get("DISCORD_BOT_TOKEN")

# Personal-score display units, keyed by AniList's user-level scoreFormat.
SCORE_UNIT = {
    "POINT_100": "/100",
    "POINT_10_DECIMAL": "/10",
    "POINT_10": "/10",
    "POINT_5": "/5",
    "POINT_3": "",
}

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
renderer = CardRenderer()


def extract_title(title_obj: dict) -> str:
    return (title_obj or {}).get("english") or (title_obj or {}).get("romaji") or "Unknown"


def pick_popularity_rank(rankings: list[dict]) -> int | None:
    """Prefer the overall (format-unrestricted) all-time popularity rank;
    fall back to any all-time POPULAR ranking, then any POPULAR ranking."""
    candidates = [r for r in rankings if r.get("type") == "POPULAR" and r.get("allTime")]
    overall = [r for r in candidates if r.get("format") is None]
    chosen = overall[0] if overall else (candidates[0] if candidates else None)
    if chosen is None:
        popular_any = [r for r in rankings if r.get("type") == "POPULAR"]
        chosen = popular_any[0] if popular_any else None
    return chosen["rank"] if chosen else None


def build_score_lookup(data: dict) -> dict[int, int]:
    """media id -> personal score, from the user's full MediaListCollection."""
    lookup = {}
    for lst in data.get("MediaListCollection", {}).get("lists", []):
        for entry in lst.get("entries", []):
            media = entry.get("media") or {}
            mid = media.get("id")
            score = entry.get("score")
            if mid is not None and score:
                lookup[mid] = score
    return lookup


def build_favourites(data: dict, score_lookup: dict[int, int]) -> list[scoring.ScoredFavourite]:
    nodes = data.get("User", {}).get("favourites", {}).get("anime", {}).get("nodes", [])
    favourites = []
    for node in nodes:
        rank = pick_popularity_rank(node.get("rankings") or [])
        favourites.append(
            scoring.ScoredFavourite(
                title=extract_title(node.get("title")),
                rank=rank,
                popularity=node.get("popularity"),
                personal_score=score_lookup.get(node["id"]),
                obscurity=scoring.obscurity_score(rank) if rank else 0.0,
            )
        )
    return favourites


def build_completed_entries(data: dict) -> list[tuple[int, list[str], str]]:
    entries = []
    for lst in data.get("MediaListCollection", {}).get("lists", []):
        for entry in lst.get("entries", []):
            if entry.get("status") != "COMPLETED":
                continue
            year = (entry.get("completedAt") or {}).get("year")
            if not year:
                continue
            media = entry.get("media") or {}
            entries.append((year, media.get("genres") or [], extract_title(media.get("title"))))
    return entries


def format_personal_score(score: int | None, score_format: str) -> str | None:
    if not score:
        return None
    return f"{score}{SCORE_UNIT.get(score_format, '')}"


def user_tag(user_id: int) -> str:
    return f"No. {user_id:09d}"


def issued_date() -> str:
    return date.today().strftime("%d %b %Y").lower()


async def fetch_bundle_or_notify(interaction: discord.Interaction, username: str) -> dict | None:
    try:
        return await fetch_user_bundle(username)
    except UserNotFoundError:
        await interaction.followup.send(
            f"Couldn't find an AniList user named **{username}**. Double-check the spelling.",
            ephemeral=True,
        )
    except AniListError as e:
        await interaction.followup.send(f"AniList API error: {e}", ephemeral=True)
    return None


@bot.event
async def on_ready():
    log.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "?")
    await renderer.start()
    try:
        synced = await bot.tree.sync()
        log.info("Synced %d slash commands", len(synced))
    except Exception:
        log.exception("Failed to sync slash commands")


@bot.tree.command(name="taste", description="Reveal how mainstream or contrarian someone's AniList favourites are.")
@app_commands.describe(username="AniList username")
async def taste(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    data = await fetch_bundle_or_notify(interaction, username)
    if data is None:
        return

    score_lookup = build_score_lookup(data)
    favourites = build_favourites(data, score_lookup)
    try:
        result = scoring.compute_taste(favourites)
    except ValueError:
        await interaction.followup.send(
            f"**{username}** doesn't have enough favourites with popularity data to compute a taste signature.",
            ephemeral=True,
        )
        return

    user = data["User"]
    context = {
        "score": result["score"],
        "archetype": result["archetype"],
        "archetype_blurb": result["archetype_blurb"],
        "driven_by": result["driven_by"],
        "user_tag": user_tag(user["id"]),
        "username": user["name"],
        "issued_date": issued_date(),
    }
    png = await renderer.render("taste.html", context)
    await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="taste.png"))


@bot.tree.command(name="rarest", description="Show someone's single rarest AniList favourite.")
@app_commands.describe(username="AniList username")
async def rarest(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    data = await fetch_bundle_or_notify(interaction, username)
    if data is None:
        return

    user = data["User"]
    score_format = (user.get("mediaListOptions") or {}).get("scoreFormat", "POINT_10")
    score_lookup = build_score_lookup(data)
    favourites = build_favourites(data, score_lookup)
    try:
        result = rarest_logic.compute_rarest(favourites)
    except ValueError:
        await interaction.followup.send(
            f"**{username}** doesn't have any favourites with popularity data.",
            ephemeral=True,
        )
        return

    rare = result["rarest"]
    popular = result["most_popular"]

    description = f"Only ~{rare.popularity:,} users have this on their list — {result['comparison']}."
    personal = format_personal_score(rare.personal_score, score_format)
    if personal:
        description += f" You rated it {personal}."

    context = {
        "user_tag": user_tag(user["id"]),
        "username": user["name"],
        "title": rare.title,
        "rank_text": f"#{rare.rank:,}" if rare.rank else "unranked",
        "description": description,
        "most_popular_title": popular.title,
        "most_popular_rank_text": f"#{popular.rank:,}" if popular.rank else "unranked",
        "issued_date": issued_date(),
    }
    png = await renderer.render("rarest.html", context)
    await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="rarest.png"))


@bot.tree.command(name="timeline", description="Chart someone's AniList completed-anime history into eras.")
@app_commands.describe(username="AniList username")
async def timeline(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    data = await fetch_bundle_or_notify(interaction, username)
    if data is None:
        return

    entries = build_completed_entries(data)
    try:
        eras = timeline_logic.build_eras(entries)
    except ValueError:
        await interaction.followup.send(
            f"**{username}** doesn't have any completed anime with dates on AniList.",
            ephemeral=True,
        )
        return

    user = data["User"]
    context = {
        "username": user["name"],
        "year_range": f"{eras[0]['start_year']} — {eras[-1]['end_year']}",
        "eras": eras,
        "issued_date": issued_date(),
    }
    png = await renderer.render("timeline.html", context)
    await interaction.followup.send(file=discord.File(io.BytesIO(png), filename="timeline.png"))


def main():
    if not TOKEN:
        raise SystemExit("DISCORD_BOT_TOKEN environment variable is not set.")
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
