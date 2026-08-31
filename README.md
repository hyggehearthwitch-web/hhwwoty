# Witch's Wheel of the Year — live calendar snapshot

This folder contains a self-contained `index.html` plus the scripts that keep it in sync with the public Google Calendar.

## What's here

- `index.html` — the final, single-file calendar. HTML, CSS, JS, and the event snapshot are all inside.
- `src/index.template.html` — a build template (no event data, no live-sync code).
- `scripts/build_calendar.py` — fetches the public `.ics` feed, expands recurring events, classifies them, and injects the snapshot into the template.
- `scripts/make_template.py` — one-time helper that turns the standalone `index_v4.html` into `src/index.template.html`.
- `.github/workflows/sync-calendar.yml` — GitHub Actions workflow that rebuilds `index.html` every hour.

## How it stays live

GitHub Actions runs `scripts/build_calendar.py` on a schedule. The script pulls the latest public `.ics` feed from Google Calendar, expands `YEARLY` and `WEEKLY` recurrences, classifies events into the same eight categories, and writes a fresh `index.html`. If the calendar changes, the workflow commits the updated file automatically.

No API key, no OAuth, and no secret is stored in the repository, so GitHub's secret scanning will not flag it.

## Setup in your repo

1. Copy the contents of this folder into your `hyggehearthwitch-web/hhwwoty` repository root.
2. Make sure `index.html` is at the repo root (GitHub Pages serves it at `https://hyggehearthwitch-web.github.io/hhwwoty/`).
3. Push to the branch configured for GitHub Pages (usually `main`).
4. Go to **Actions → Sync calendar snapshot** and click **Run workflow** to test it.
5. The workflow will run automatically every hour thereafter.

## Categories

Sabbats, Moon phases, Retrogrades, Zodiac, Lunar aspects, Daily correspondence, Feasts, and Other.

## Fallback

If the GitHub Actions workflow ever fails or is disabled, the existing `index.html` still works as a standalone snapshot.
