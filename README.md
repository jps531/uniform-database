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

Code and configuration, plus one copy of artwork for testing. The working
copy lives in iCloud Drive, with the artwork folders inside it alongside the
code, and git ignores them. The exception is `golden/fixture/`, a copy of
just the artwork the golden suite uses, so CI can run it.

| Path | What it is |
|---|---|
| `configs/` | Everything the pipeline knows, as YAML: canvases and era profiles, the 48 view templates, slots and colorways, and each sport's token vocabulary |
| `scripts/` | The Python asset pipeline, in three folders: `pipeline/` (standardize, crop, compose), `migration/` (bringing new artwork and marks in, and checking it), `golden/` (the golden suite) |
| `golden/` | The golden suite's approved plan (`manifest.yaml`, `PLAN.md`), known pairings, and `fixture/`: a copy of the artwork the suite needs, so CI can run it. Renders go to `golden/run/`, which isn't tracked |
| `tests/` | Unit tests for every script (pytest), on synthetic artwork |
| `docs/` | [reference.md](docs/reference.md), the full pipeline reference: naming grammar, invariants, eras and canvases, composition, and the mistakes not to repeat. [golden_suite.md](docs/golden_suite.md), the golden suite and its CI |
| `pyproject.toml`, `uv.lock` | Dependencies, managed with uv, and the ruff config |
| `CLAUDE.md` | The rules AI agents working here must follow, and the full command list. It points into `docs/reference.md` for detail |

Not tracked, but expected in the same folder when you run anything:
`{Sport}/{Team}/…` (uniform elements), `Marks/` (opponent helmets and hats),
`Venues/` (fields and courts), `temp/` (staging) and `surveys/` (one-off
listings).

## Setup

Install [uv](https://docs.astral.sh/uv/). Then, once, from the project
folder (the one holding `configs/` and the artwork):

```
uv sync          # Python 3.13 and every dependency, into .venv
```

Run every command below from that same folder. Every script prints its full
options with `--help`, and CLAUDE.md's "Commands" section lists every script
and option.

## Compose a graphic

`compose.py` builds one graphic from a **sport**, a **view** and one
**element per slot**. An element is the name of its folder:
`{first year worn} {colorway} [{design}]`, e.g. `2025 Black` or
`2012 White Egg Bowl`.

```
uv run scripts/pipeline/compose.py --sport football --view full \
    --team "Mississippi State" \
    --helmet "2025 Black" --jersey "2025 Black" --pants "2025 Black" \
    --number 0 \
    --out out/2025-black.png
```

The output goes to `--out`, or `out/composed.png` by default. `--team`
defaults to Mississippi State, `--sport` to `football` and `--view` to
`full`.

**Views.** These are all 48 templates in `configs/view_templates.yaml`.
Pass the sport as written here (`mens_basketball`, not `Men's Basketball`):

| `--sport` | `--view` | slots it takes |
|---|---|---|
| `football` | `full`, `condensed`, `jersey-full`, `pants-full`, `helmets-3`, `helmets-4`, `icons-horizontal`, `icons-vertical` | `--helmet`, `--jersey`, `--pants` |
| `baseball` | `baseball-full`, `baseball-condensed`, `baseball-tall`, `diamond-jersey`, each also `…-tq` | `--hat`, `--jersey`, `--pants` |
| `softball` | `softball-full`, `softball-condensed`, `softball-tall`, `diamond-pants` | `--jersey`, `--pants` |
| `mens_basketball` | `mbk-full`, `mbk-condensed`, `mbk-tall`, `mbk-tall-condensed`, `mbk-jersey`, `mbk-shorts` | `--jersey`, `--shorts` |
| `womens_basketball` | the same, `wbk-…` | `--jersey`, `--shorts` |
| `soccer` | `soccer-full`, `soccer-condensed`, `soccer-jersey`, each also `…-ls`; `soccer-shorts`; combos `soccer-combo`, `soccer-combo-ls`, `soccer-condensed-combo` | `--jersey`, `--shorts` (+ `2` forms) |
| `volleyball` | `volleyball-jersey`; combos `volleyball-combo`, `volleyball-condensed-combo-{ss\|ls}-{ss\|ls}` | `--jersey` (+ `--jersey2`) |

A view uses only the slots it needs. A single-piece view like `helmets-3`
takes just `--helmet`.

**Pick the view that matches the element's cut.** `-tq` views are for
three-quarter-sleeve baseball jerseys (softball has no three-quarter cut),
`-ls` for long-sleeve
soccer kits, and the volleyball condensed combos name each kit's sleeve
(`ss`/`ls`). The wrong cut clips without an error, so check the output.

**Combos** show two uniforms. The second one takes the `2` form of each
flag. In soccer the second uniform is always the keeper:

```
uv run scripts/pipeline/compose.py --sport soccer --view soccer-combo \
    --jersey "2026 White" --shorts "2026 White" --number 4 \
    --jersey2 "2026 Blue Keeper" --shorts2 "2026 Blue" --number2 0
```

**Choosing among an element's files.** When an element has more than one
file, `compose.py` picks the plainest file with the requested number.
These flags change the pick:

| Flag | Does |
|---|---|
| `--number 03` | the jersey number. It's a string: `03` and `3` are different files. |
| `--with TOKEN` | require a patch, variation or form, e.g. `--with Grad`, `--with Classic`. Repeatable. |
| `--player SURNAME` | pick between files sharing a number (baseball's `18 Girodo` and `18 Heck`) |
| `--with2`, `--player2` | the same, for the second uniform in a combo |
| `--element SLOT=NAME` | any slot without its own flag, e.g. `--element sock="2019 White"` |
| `--helmet-left` | football: add the left-helmet inset, for helmets whose two sides differ |
| `--json PATH` | also write which file filled each placement, and anything missing or clipped |
| `--diff PATH` | compare the result against a hand-made composite |

## Generate helmet Left and Right views from Marks

The football side helmets in `Football/{Team}/Helmets Left|Right` are
**generated**. Their source is the native-scale artwork in
`Marks/Football/{Team}/Helmets Left|Right`. `standardize.py pad` rebuilds
them: it crops each mark, applies its era's scale and pads it onto the
helmet canvas.

One team:

```
uv run scripts/pipeline/standardize.py pad "Marks/Football/Mississippi State/Helmets Left"  "Football/Mississippi State/Helmets Left"
uv run scripts/pipeline/standardize.py pad "Marks/Football/Mississippi State/Helmets Right" "Football/Mississippi State/Helmets Right"
```

Every team with uniform data. Marks for teams without a `Football/` folder
are skipped, because they have no uniforms catalogued:

```
for d in Marks/Football/*/; do
  team=$(basename "$d")
  [ -d "Football/$team" ] || continue
  for side in Left Right; do
    uv run scripts/pipeline/standardize.py pad "Marks/Football/$team/Helmets $side" "Football/$team/Helmets $side"
  done
done
```

Things to know:

- **`pad` writes immediately.** There's no dry run. That's acceptable here
  because the destination is generated and can always be rebuilt from Marks.
  Pad directly into `.generated` trees like these; for an authored tree, pad
  into a `… STD` sibling and check it before replacing the source.
- **Edit the Marks file, never the generated one.** The destination folders
  carry a `.generated` marker, which is why `pad` may overwrite them. It
  refuses an unmarked destination, and `--force` would permanently mark an
  authored folder as rebuildable, so don't use it here.
- **`pad` adds and replaces files but never deletes.** If you rename or
  remove a mark, delete the old generated file by hand.
- **Never point `pad` at standardized output.** Run it on `Marks/` only,
  never with a `Football/` folder as the *source*. It refuses files whose
  content already matches a scaled era, but don't rely on that. A re-pad
  once destroyed 44 elements.
- Run the golden suite afterwards (below).

## Generate the cropped venue views

`Venues/{Sport}/{Team}/Fields Cropped` and `Courts Cropped` are
**generated** from the matching `… Full` folder. Each crop box is configured
per sport in `configs/canvas_definitions.yaml` (`derived_from`).
`derive_crops.py` does a dry run until you pass `--apply`:

```
uv run scripts/pipeline/derive_crops.py                          # dry run, every sport
uv run scripts/pipeline/derive_crops.py --apply                  # write
uv run scripts/pipeline/derive_crops.py --sport football --apply # one sport: football, baseball or basketball
```

It reads only the `… Full` folders, writes the `… Cropped` ones with a
`.generated` marker, and refuses to write if any source is off its canvas.
Basketball is one venue for both programs (`Venues/Basketball`), so its
sport is `basketball`. Edit the Full artwork, never the cropped copy.

## Check everything still composes: the golden suite

```
uv run scripts/golden/golden_plan.py      # plan: golden/PLAN.md, golden/manifest.yaml
uv run scripts/golden/golden_run.py       # render and check: open golden/run/index.html
```

Run it after any change to a template, canvas or era profile, and after
regenerating helmets or crops. The plan caches each element's measurements
in `golden/inventory.json`, so after artwork changes plan with
`uv run scripts/golden/golden_plan.py --rescan`. It renders every template at every era from
real elements and lists every defect in `golden/run/REPORT.md`.
[docs/golden_suite.md](docs/golden_suite.md) explains the plan, what it
checks, and how to fix a bad pairing.

**CI runs it too**, on `golden/fixture/`, a copy of exactly the artwork the
suite uses; refresh and commit that copy after any re-plan or artwork change,
as [docs/golden_suite.md, section 3](docs/golden_suite.md#3-ci--goldenfixture-and-golden_cipy)
describes.

Every script has unit tests in `tests/` (`uv run pytest -n auto`).
[CONTRIBUTING.md](CONTRIBUTING.md) has the checks CI runs, the tools, and
what must change together.

## Before you change artwork

Two rules that have cost artwork when broken
([docs/reference.md](docs/reference.md) explains both):

- **Never re-pad standardized output.** `standardize.py pad` is for authored
  source only; use `recanvas.py` to move standardized files to a new canvas.
- **Generated trees are marked.** `Football/*/Helmets Left|Right` and every
  `Venues/…/… Cropped` folder are rebuilt from a source, and carry a
  `.generated` file. Everything else is authored. Never add a marker to an
  authored folder.

## License

Copyright © 2012–2026 Paul Sullivan. All rights reserved.

The code is public so anyone can read it and see how the archive is built,
but it's source-available, not open source: using, copying or hosting it
needs the author's written permission. The uniform artwork is the author's
original work too: the copies in `golden/fixture/` are there only for the
tests, and nothing here grants any rights to them. See [LICENSE](LICENSE).
