"""Thin async client for AniList's public GraphQL API.

No auth is required for reading public profiles. A single combined query
fetches everything all three slash commands need in one HTTP round trip:
the user's favourite anime (with popularity rankings) and their full
anime list collection (scores, completion dates, genres).
"""
import json

import aiohttp

ANILIST_URL = "https://graphql.anilist.co"

QUERY = """
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
          rankings {
            rank
            type
            format
            allTime
            context
          }
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


class AniListError(Exception):
    """Raised for any non-"user not found" AniList API failure."""


class UserNotFoundError(AniListError):
    """Raised when the given AniList username doesn't resolve to a profile."""


async def fetch_user_bundle(username: str) -> dict:
    """Fetch the combined User + MediaListCollection payload for a username.

    Returns the raw `data` dict from the GraphQL response (keys: "User",
    "MediaListCollection"). Raises UserNotFoundError / AniListError on failure.
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(
            ANILIST_URL,
            json={"query": QUERY, "variables": {"name": username}},
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
        if status == 404 or "not found" in message.lower():
            raise UserNotFoundError(f"AniList user '{username}' was not found.")
        raise AniListError(message)

    data = payload.get("data") or {}
    if not data.get("User"):
        raise UserNotFoundError(f"AniList user '{username}' was not found.")
    return data
