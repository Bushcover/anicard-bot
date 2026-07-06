# AniCard

A Discord bot with three slash commands that pull real AniList data and
render it as designed PNG cards — no database, no account linking,
fully stateless. Every command takes a required `username` (an AniList
username) and looks that profile up live.

- **`/taste [username]`** — a 0–100 "distinctiveness" gauge for how
  mainstream vs. contrarian someone's favourite anime are, with an
  archetype label and the 3 favourites driving the score.
- **`/rarest [username]`** — spotlights the single least-popular anime in
  someone's favourites, with a human-scale comparison and a contrast
  against their most popular favourite.
- **`/timeline [username]`** — buckets someone's completed-anime history
  into genre-labelled "eras" by year.

## How it works

1. `anilist.py` talks to AniList's public API (`https://graphql.anilist.co`,
   no auth needed). One combined query fetches the user's favourites and
   their full anime list (scores, completion dates, genres); a second
   query fetches those favourites' popularity rankings, since AniList's
   `rankings` field reliably returns `null` when queried nested under
   `User.favourites.anime.nodes` and only resolves on a direct
   `Page.media(id_in:)` query (confirmed against the live API). Duplicate
   favourite entries -- AniList can list the same anime more than once in
   a user's favourites connection -- are also collapsed to one each here.
2. `scoring.py`, `rarest_logic.py`, and `timeline_logic.py` turn that raw
   data into each command's specific numbers/labels.
3. `render/renderer.py` feeds the result into a Jinja2 HTML template
   (`render/templates/*.html`) that reproduces the visual design from
   `anicard_command_carousel.html` (Rajdhani/Space Mono/Inter, dark card,
   corner brackets, dot texture), loads it in a headless Chromium tab via
   Playwright, waits for the fonts to finish loading, and screenshots
   just the `.card` element to a transparent PNG.
4. `bot.py` wires all of that into three `discord.py` slash commands and
   sends the PNG back as a file attachment.

Fonts are self-hosted static `.woff2` files under
`render/templates/fonts/` (sourced from the `@fontsource` npm packages,
all SIL Open Font License — see `fonts/LICENSES/`) rather than a Google
Fonts CDN `@import`. This keeps rendering deterministic and working even
in network-restricted environments, and was verified by checking
`document.fonts` in the headless page after render (not just eyeballing
the screenshot) to confirm the real families load rather than silently
falling back to system defaults.

`aiohttp.ClientSession` is created with `trust_env=True` so it honors
`HTTP_PROXY`/`HTTPS_PROXY` from the environment -- aiohttp ignores those
by default, which otherwise silently breaks outbound requests in any
proxied environment (sandboxes, some corporate networks).

AniList's own API documents a 403 "temporarily disabled due to severe
stability issues" response that it returns under heavy load. This is
expected, recurring behavior on their end, not a bug -- `anilist.py`
detects it specifically (`AniListOverloadedError`) and the bot replies
with a friendly "try again in a bit" message instead of a generic error.

Two more things found by testing against real, well-populated profiles
rather than dummy data:

- AniList only computes an **all-time** popularity ranking for
  sufficiently popular titles. A genuinely obscure favourite often only
  has a narrow year/format-scoped ranking snapshot instead (e.g. "10th
  most popular TV anime of 2005"), and showing that bare number next to
  a low raw popularity count read as contradictory ("#10" looks like a
  top-10-all-time hit, not a rare pick). `bot.py`'s
  `select_popularity_ranking`/`describe_ranking_scope` now surface that
  scope explicitly, so `/rarest` shows e.g. "#10 · 2005 TV popularity
  rank" instead of a bare, misleading "#10".
- `/timeline`'s era labels are picked from each era's genre distribution.
  Labelling on a single dominant genre could tie or repeat between eras
  and undercut the point of a timeline (showing an arc of change). An
  early fix avoided the immediately preceding era's genre, but that
  could still collide two eras later (a label ping-ponging back after a
  detour) and could force a technically-distinct but less representative
  runner-up genre even when the true top genre clearly dominated.
  `timeline_logic.py` now labels each era from its own distribution
  alone: a clearly dominant genre (more than `BLEND_GAP_THRESHOLD`
  percentage points ahead of the runner-up) gets a single-genre label as
  before; a close top two blend into one label, e.g. "Comedy & Romance
  Era". This is more honest (it reflects real signal instead of picking
  one genre to look different) and collides far less often in practice,
  since the exact pair -- and which genre led -- has to match. Two eras
  with a genuinely identical distribution (no secondary genre at all)
  are still merged into one rather than repeating a label.
- Confirmed against a third real profile that "unranked · no popularity
  rank on AniList" in `/rarest` is a genuine data gap, not the rankings
  bug above recurring: a direct query showed the title had real `RATED`
  rankings but no `POPULAR`-type ranking at all, so `select_popularity_
  ranking`'s `type == "POPULAR"` filter correctly found nothing.

The "No. 000000002"-style serial number on each card is the AniList
profile's own real, immutable numeric user ID (zero-padded for the
trading-card aesthetic) -- not a render counter. `matchai`, used while
testing, really is AniList's 2nd-ever registered account.

The per-command context-building logic (turning fetched data + scores
into the dict each template renders) lives in `bot.py`'s
`build_taste_context` / `build_rarest_context` / `build_timeline_context`
and is shared between the live bot and `scripts/preview.py`, so the two
can't silently drift out of sync the way a second hand-copied
implementation could.

Testing against a second, much sparser real profile (1 favourite, 1
year of history) surfaced two more honesty gaps, since a small sample
still rendered as confidently as a large one:

- `/rarest` showed a "most popular favorite" contrast row comparing the
  rarest favourite to itself whenever there were fewer than 2 distinct
  favourites (or they all tied on popularity). `rarest_logic.compute_rarest`
  now returns `most_popular: None` in that case, and the card shows "Add
  more favorites for a comparison" instead of a trivial self-contrast.
- `/taste`'s gauge and archetype looked equally confident regardless of
  how many favourites backed them. `scoring.compute_taste` now exposes
  `sample_size`, and the card prints a small "based on N favorite(s)"
  note under the archetype blurb.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

Copy `.env.example` to `.env` and fill in your bot token:

```bash
cp .env.example .env
# edit .env: DISCORD_BOT_TOKEN=...
```

The token is only ever read from the environment (via `python-dotenv`) —
it is never hardcoded anywhere in the source.

Your bot needs the `applications.commands` and `bot` OAuth2 scopes, and
the "Send Messages" + "Attach Files" permissions, when you generate its
invite link in the Discord Developer Portal.

## Running

```bash
python bot.py
```

On startup the bot launches its headless Chromium instance, logs in, and
syncs its three slash commands globally by default (global sync can take
up to an hour to propagate to Discord's client the first time).

For local testing, set `DISCORD_TEST_GUILD_ID` in `.env` to a test
server's guild ID and the bot will sync commands to that server only,
instantly, instead of globally:

```bash
# in .env
DISCORD_TEST_GUILD_ID=123456789012345678
```

(Enable Developer Mode in Discord's settings, then right-click the
server icon and "Copy Server ID" to get this.) Remove or comment out
`DISCORD_TEST_GUILD_ID` to go back to the global-sync default.

## Previewing cards without Discord

`scripts/preview.py` fetches a real AniList profile and renders all three
cards straight to local PNG files, which is handy for checking data and
layout without needing a Discord connection at all:

```bash
python scripts/preview.py <anilist_username> [output_dir]
```

## Tests

`anilist.py`'s error handling (non-JSON/error responses from AniList) is
covered by mocked unit tests that need no network access:

```bash
pip install -r requirements-dev.txt
pytest
```

## Tuning the scoring

- **`scoring.py`**: the `/taste` distinctiveness formula and its
  `RANK_CEILING` constant, plus the 4 archetype tiers, are documented
  and adjustable at the top of the file.
- **`rarest_logic.py`**: the population-comparison phrases
  (`POPULATION_ANCHORS`) can be edited or extended.
- **`timeline_logic.py`**: the genre → era-name lookup (`GENRE_FLAVOR`)
  and era dot colors (`ERA_COLORS`) live at the top of the file.

## Project layout

```
bot.py                    Discord bot + slash command handlers
anilist.py                AniList GraphQL client
scoring.py                /taste distinctiveness scoring + archetypes
rarest_logic.py           /rarest logic + human-scale comparisons
timeline_logic.py         /timeline era bucketing + labeling
render/
  renderer.py             Playwright-driven HTML -> PNG card rendering
  templates/
    _shared.css.jinja      CSS shared by all three card templates
    taste.html
    rarest.html
    timeline.html
scripts/
  preview.py              Local PNG preview without Discord
tests/
  test_anilist.py         Mocked unit tests for AniList error handling
requirements.txt
requirements-dev.txt
.env.example
```

## Out of scope for this pass

No 24/7 hosting or deployment is set up — this is local/sandbox testing
only. Hosting is a deliberate separate step later.
