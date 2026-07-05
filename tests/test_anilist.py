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

from anilist import AniListError, UserNotFoundError, fetch_user_bundle


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
    def __init__(self, response: FakeResponse):
        self._response = response

    def post(self, *args, **kwargs):
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


def _patched_session(response: FakeResponse):
    return patch("anilist.aiohttp.ClientSession", return_value=FakeSession(response))


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
            "errors": [{"message": "The AniList API has been temporarily disabled", "status": 403}],
            "data": None,
        }
    )
    response = FakeResponse(status=403, body=body)
    with _patched_session(response):
        with pytest.raises(AniListError) as excinfo:
            await fetch_user_bundle("someuser")
    assert "temporarily disabled" in str(excinfo.value)


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
