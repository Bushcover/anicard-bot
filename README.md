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

1. `anilist.py` sends one combined GraphQL query to AniList's public API
   (`https://graphql.anilist.co`, no auth needed) per command, fetching
   both the user's favourites (with popularity rankings) and their full
   anime list (scores, completion dates, genres).
2. `scoring.py`, `rarest_logic.py`, and `timeline_logic.py` turn that raw
   data into each command's specific numbers/labels.
3. `render/renderer.py` feeds the result into a Jinja2 HTML template
   (`render/templates/*.html`) that reproduces the visual design from
   `anicard_command_carousel.html` (Rajdhani/Space Mono/Inter, dark card,
   corner brackets, dot texture), loads it in a headless Chromium tab via
   Playwright, waits for the Google Fonts to finish loading, and
   screenshots just the `.card` element to a transparent PNG.
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
syncs its three slash commands globally (global sync can take up to an
hour to propagate to Discord's client the first time — invite the bot to
a test server and it usually shows up much sooner).

## Previewing cards without Discord

`scripts/preview.py` fetches a real AniList profile and renders all three
cards straight to local PNG files, which is handy for checking data and
layout without needing a Discord connection at all:

```bash
python scripts/preview.py <anilist_username> [output_dir]
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
requirements.txt
.env.example
```

## Out of scope for this pass

No 24/7 hosting or deployment is set up — this is local/sandbox testing
only. Hosting is a deliberate separate step later.
