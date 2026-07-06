"""Thin async client for AniList's public GraphQL API.

No auth is required for reading public profiles. Two requests are made
per command: one combined query for the user's favourites + full anime
list collection, and a second query for those favourites' popularity
rankings (see RANKINGS_QUERY for why that's separate).
"""
import json

import aiohttp

ANILIST_URL = "https://graphql.anilist.co"

USER_QUERY = """
query ($name: String) {
  User(name: $name) {
    id
    name
    mediaListOptions {
      scoreFormat
    }
    favourites {
      anime(perPage: 50) {
        nodes {
          id
          title {
            romaji
            english
          }
          popularity
        }
      }
    }
  }
  MediaListCollection(userName: $name, type: ANIME) {
    lists {
      status
      entries {
        status
        score
        completedAt {
          year
          month
          day
        }
        media {
          id
          genres
          title {
            romaji
            english
          }
        }
      }
    }
  }
}
"""

# `rankings` reliably comes back null when queried nested under
# User.favourites.anime.nodes (confirmed against the live API -- an
# AniList resolver quirk/limitation, not something we can fix on our end),
# so favourites' rankings are fetched separately via Page.media(id_in:).
RANKINGS_QUERY = """
query ($ids: [Int]) {
  Page(perPage: 50) {
    media(id_in: $ids, type: ANIME) {
      id
      rankings {
        rank
        type
        format
        allTime
        year
        context
      }
    }
  }
}
"""


class AniListError(Exception):
    """Raised for any non-"user not found" AniList API failure."""


class UserNotFoundError(AniListError):
    """Raised when the given AniList username doesn't resolve to a profile."""


class AniListOverloadedError(AniListError):
    """Raised for AniList's documented 403 "temporarily disabled due to
    severe stability issues" response, which they return during periods of
    heavy load. This is expected, recurring behavior on AniList's end (per
    their own API docs), not an edge case -- callers should show a
    friendly "try again shortly" message rather than a generic error."""


async def _post(query: str, variables: dict) -> dict:
    """POST a GraphQL query and return its `data` dict, raising on errors."""
    # trust_env=True makes aiohttp honor HTTP_PROXY/HTTPS_PROXY from the
    # environment (aiohttp ignores them by default) -- required for
    # outbound requests to succeed in proxied environments/sandboxes.
    async with aiohttp.ClientSession(trust_env=True) as session:
        async with session.post(
            ANILIST_URL,
            json={"query": query, "variables": variables},
            timeout=aiohttp.ClientTimeout(total=20),
        ) as resp:
            status = resp.status
            raw_body = await resp.text()

    # Read the body as text and parse it ourselves rather than resp.json():
    # AniList outages/maintenance pages sometimes serve an error body with a
    # non-JSON content-type header (or no JSON at all), and aiohttp's
    # strict content-type check on .json() would raise an unhandled
    # ContentTypeError in that case instead of a clean AniListError.
    try:
        payload = json.loads(raw_body)
    except ValueError:
        snippet = raw_body.strip()[:200] or "(empty response body)"
        raise AniListError(f"AniList returned a non-JSON response (HTTP {status}): {snippet}")

    errors = payload.get("errors")
    if errors:
        message = errors[0].get("message", "Unknown AniList error")
        if status == 403 and "temporarily disabled" in message.lower():
            raise AniListOverloadedError("AniList's API is briefly overloaded — try again in a bit!")
        if status == 404 or "not found" in message.lower():
            raise UserNotFoundError(message)
        raise AniListError(message)

    return payload.get("data") or {}


async def fetch_user_bundle(username: str) -> dict:
    """Fetch everything all three slash commands need for a username.

    Returns a dict with "User" and "MediaListCollection" keys. Each
    favourite node's "rankings" list is filled in from a second request,
    and duplicate favourite entries -- AniList can return the same media
    id more than once in a user's favourites connection -- are collapsed
    to their first occurrence.

    Raises UserNotFoundError / AniListOverloadedError / AniListError.
    """
    data = await _post(USER_QUERY, {"name": username})
    if not data.get("User"):
        raise UserNotFoundError(f"AniList user '{username}' was not found.")

    nodes = data["User"].get("favourites", {}).get("anime", {}).get("nodes", [])
    deduped = []
    seen_ids = set()
    for node in nodes:
        if node["id"] in seen_ids:
            continue
        seen_ids.add(node["id"])
        node["rankings"] = []
        deduped.append(node)
    data["User"].setdefault("favourites", {}).setdefault("anime", {})["nodes"] = deduped

    if deduped:
        rankings_data = await _post(RANKINGS_QUERY, {"ids": [node["id"] for node in deduped]})
        rankings_by_id = {
            media["id"]: media.get("rankings") or []
            for media in rankings_data.get("Page", {}).get("media", [])
        }
        for node in deduped:
            node["rankings"] = rankings_by_id.get(node["id"], [])

    return data
