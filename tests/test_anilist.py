"""Tests for anilist.py's HTTP error handling.

No real network calls are made -- aiohttp.ClientSession is replaced with a
fake that returns a scripted response. These specifically cover the case
that broke against the real (currently-outaged) AniList API: an error
response whose body isn't decodable as JSON, which previously crashed with
an unhandled aiohttp.ContentTypeError instead of a clean AniListError.
"""
import json
from unittest.mock import patch

import pytest

from anilist import AniListError, AniListOverloadedError, UserNotFoundError, fetch_user_bundle


class FakeResponse:
    def __init__(self, status: int, body: str):
        self.status = status
        self._body = body

    async def text(self):
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    """Returns scripted FakeResponses in order, one per session.post() call
    (fetch_user_bundle makes a second request for rankings when a user has
    favourites, so tests exercising that path pass a list of responses)."""

    def __init__(self, responses):
        self._responses = list(responses)

    def post(self, *args, **kwargs):
        return self._responses.pop(0)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _patched_session(*responses: FakeResponse):
    return patch("anilist.aiohttp.ClientSession", return_value=FakeSession(responses))


@pytest.mark.asyncio
async def test_non_json_body_raises_anilist_error_instead_of_crashing():
    response = FakeResponse(
        status=403,
        body="The AniList API has been temporarily disabled due to severe stability issues.",
    )
    with _patched_session(response):
        with pytest.raises(AniListError):
            await fetch_user_bundle("someuser")


@pytest.mark.asyncio
async def test_json_body_served_with_wrong_content_type_still_parses():
    """Reproduces exactly what the real API did: a valid JSON error body,
    but served in a way that trips aiohttp's strict resp.json() content-type
    check. Our client reads the body as text and parses it manually, so
    this must still surface as a normal AniListError, not a crash."""
    body = json.dumps(
        {
            "errors": [{"message": "Internal Server Error", "status": 500}],
            "data": None,
        }
    )
    response = FakeResponse(status=500, body=body)
    with _patched_session(response):
        with pytest.raises(AniListError) as excinfo:
            await fetch_user_bundle("someuser")
    assert "Internal Server Error" in str(excinfo.value)


@pytest.mark.asyncio
async def test_overload_403_raises_dedicated_error_with_friendly_message():
    """AniList's documented "temporarily disabled due to severe stability
    issues" 403 is expected, recurring behavior under heavy load, not a
    generic failure -- it must raise AniListOverloadedError specifically,
    carrying a friendly user-facing message rather than the raw AniList
    error text."""
    body = json.dumps(
        {
            "errors": [
                {
                    "message": (
                        "The AniList API has been temporarily disabled due to severe "
                        "stability issues. Please check the announcements channel in "
                        "the official AniList Discord for more information."
                    ),
                    "status": 403,
                }
            ],
            "data": None,
        }
    )
    response = FakeResponse(status=403, body=body)
    with _patched_session(response):
        with pytest.raises(AniListOverloadedError) as excinfo:
            await fetch_user_bundle("someuser")
    assert "try again" in str(excinfo.value).lower()


@pytest.mark.asyncio
async def test_user_not_found_error():
    body = json.dumps({"errors": [{"message": "User not found"}], "data": None})
    response = FakeResponse(status=404, body=body)
    with _patched_session(response):
        with pytest.raises(UserNotFoundError):
            await fetch_user_bundle("ghost_user_that_does_not_exist")


@pytest.mark.asyncio
async def test_successful_response_returns_data():
    body = json.dumps(
        {
            "data": {
                "User": {"id": 1, "name": "example"},
                "MediaListCollection": {"lists": []},
            }
        }
    )
    response = FakeResponse(status=200, body=body)
    with _patched_session(response):
        data = await fetch_user_bundle("example")
    assert data["User"]["name"] == "example"


@pytest.mark.asyncio
async def test_duplicate_favourites_deduped_and_rankings_merged_in():
    """Regression test: against real data, AniList returned the same media
    id multiple times in one user's favourites connection, and `rankings`
    always came back null when nested under favourites (it only resolves
    on a direct Page.media(id_in:) query). fetch_user_bundle must collapse
    the duplicates to one entry each and merge in rankings from the
    second request."""
    user_body = json.dumps(
        {
            "data": {
                "User": {
                    "id": 2,
                    "name": "example",
                    "mediaListOptions": {"scoreFormat": "POINT_10"},
                    "favourites": {
                        "anime": {
                            "nodes": [
                                {"id": 79, "title": {"romaji": "SHUFFLE!", "english": None}, "popularity": 46797},
                                {"id": 79, "title": {"romaji": "SHUFFLE!", "english": None}, "popularity": 46797},
                                {"id": 10087, "title": {"romaji": "Fate/Zero", "english": "Fate/Zero"}, "popularity": 340927},
                            ]
                        }
                    },
                },
                "MediaListCollection": {"lists": []},
            }
        }
    )
    rankings_body = json.dumps(
        {
            "data": {
                "Page": {
                    "media": [
                        {"id": 79, "rankings": [{"rank": 1, "type": "POPULAR", "format": "TV", "allTime": False, "context": "most popular"}]},
                        {"id": 10087, "rankings": [{"rank": 102, "type": "POPULAR", "format": "TV", "allTime": True, "context": "most popular all time"}]},
                    ]
                }
            }
        }
    )
    with _patched_session(FakeResponse(200, user_body), FakeResponse(200, rankings_body)):
        data = await fetch_user_bundle("example")

    nodes = data["User"]["favourites"]["anime"]["nodes"]
    assert [n["id"] for n in nodes] == [79, 10087]
    assert nodes[0]["rankings"][0]["rank"] == 1
    assert nodes[1]["rankings"][0]["rank"] == 102
