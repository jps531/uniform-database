# Uniform Database

A uniform-tracking archive for Mississippi State athletics and the programs
around it, and the website that will publish it. Hand-drawn uniform pieces
(helmets, jerseys, pants, hats, shorts) are standardized onto fixed canvases,
then composed on demand into full-uniform graphics.

It will replace two legacy sites: **hailstateunisdatabase.com** (game-by-game
uniform records, PHP/MySQL) and **hailstateunis.com** (narrative uniform
history, Weebly).

## Status

| Stage | State |
|---|---|
| Rescue the legacy sites (MySQL dump, Weebly prose, PNG/PSD sources) | done |
| Asset pipeline: 7 sports standardized, 48 composition templates, golden suite clean | done |
| Postgres schema (Drizzle) | next |
| Import the MySQL game-by-game data | planned |
| Upload assets to Cloudflare R2 | planned |
| Next.js site | planned |
| Migrate and retire both legacy sites | planned |

Sports: football, baseball, softball, men's and women's basketball, soccer,
volleyball. Mississippi State has data in all of them; nine other football
programs and a few baseball and softball programs are tracked too. Helmet
marks for 258 football programs and hat marks for 41 baseball programs are
kept separately, for matchup graphics later.

## What's in the repository

Code and configuration only. The artwork itself lives in iCloud Drive, next
to this checkout, and is gitignored.

| Path | What it is |
|---|---|
| `configs/` | Everything the pipeline knows, as YAML: canvases and era profiles, the 48 view templates, slots and colorways, and each sport's token vocabulary |
| `scripts/` | The Python asset pipeline: DPI fixes, nesting, standardizing, cropping, composing, the golden suite |
| `golden/` | The golden suite's approved plan (`manifest.yaml`, `PLAN.md`) and known pairings; renders go to `golden/run/`, which isn't tracked |
| `docs/` | Longer how-tos ([golden_suite.md](docs/golden_suite.md)) |
| `pyproject.toml`, `uv.lock` | Dependencies, managed with uv, and the ruff config |
| `CLAUDE.md` | The full reference for the pipeline: naming grammar, invariants, eras and canvases, composition, and the mistakes not to repeat. Written for AI agents, and the most complete description of the project for people too |

Not tracked, but expected beside the code when you run anything:
`{Sport}/{Team}/…` (uniform elements), `Marks/` (opponent helmets and hats),
`Venues/` (fields and courts), `temp/` (staging) and `surveys/` (one-off
listings).

## Quick start

Install [uv](https://docs.astral.sh/uv/), then, from the folder that holds
both this checkout and the artwork:

```
uv sync                            # Python 3.13 and every dependency, into .venv

# compose a uniform
uv run scripts/compose.py --sport football --view full \
    --team "Mississippi State" \
    --helmet "2025 Black" --jersey "2025 Black" --pants "2025 Black" --number 0

# check every template still composes correctly
uv run scripts/golden_plan.py
uv run scripts/golden_run.py       # then open golden/run/index.html
```

Run the golden suite after any change to a template, canvas or era profile.
Every script's own docstring explains its options, and CLAUDE.md's
"Commands" section lists them all. [CONTRIBUTING.md](CONTRIBUTING.md) has
the checks CI runs, the tools, and what must change together.

## Before you change artwork

Two rules that have cost artwork when broken (CLAUDE.md explains both):

- **Never re-pad standardized output.** `standardize.py pad` is for authored
  source only; use `recanvas.py` to move standardized files to a new canvas.
- **Generated trees are marked.** `Football/*/Helmets Left|Right` and every
  `Venues/…/… Cropped` folder are rebuilt from a source, and carry a
  `.generated` file. Everything else is authored. Never add a marker to an
  authored folder.
