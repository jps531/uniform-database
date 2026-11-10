# Uniform Database

A uniform-tracking archive and website for Mississippi State athletics and
the programs around it. Hand-drawn uniform element PNGs are standardized onto
fixed canvases, then composed on demand into combination graphics.

Replaces two legacy sites:
- **hailstateunisdatabase.com** — PHP/MySQL, game-by-game uniform records
- **hailstateunis.com** — Weebly, narrative uniform history

This file is what an agent must know and obey. The reference detail —
naming grammar, invariants, eras and canvases, nesting, composition, the
history of what was tried — is in `docs/reference.md`; read the section a
task touches before changing it.

## Where this is going

**Phase 0 — asset rescue — is done.** MySQL dump taken (seven schemas across
sports, from a Lightsail RDS MySQL 5.7 instance), Weebly prose crawled,
blog-post seed list extracted, all PNG and PSD sources backed up.

**The asset pipeline is done.** Seven sports standardized and verified, 48
composition templates, every era of every viewpoint rendered and checked by
the golden suite with zero defects. The element model — elements, eras,
tokens with scope, form tokens, numbers, players — has held across all seven
sports without structural change.

**Next, in order:**

1. **Postgres schema** (Drizzle). The element model above is settled enough
   to become tables. Open question carried from earlier design work: patch
   operations, including SUBTRACTIVE variants (`patch.operation`).
2. **Import the MySQL dump.** Its game-by-game appearances are the "worn
   together" data the golden planner currently guesses at from filenames.
   Once imported, `golden/pairings.yaml` should go away and the suite should
   draw its examples from real games.
3. **Upload assets to Cloudflare R2**, with keys decided by the schema.
4. **Next.js front end** joining database and showcase views.
5. **Migrate and retire** both legacy sites, folding in the crawled Weebly
   prose and the blog seed list.

Later: **matchup graphics** from the Marks trees (helmets for 258 football
programs, hats for 41 baseball programs). These need their own templates and
a place in the golden suite.

## Stack

Python for the asset pipeline (`scripts/`), YAML for all pipeline config.
Dependencies via uv (`pyproject.toml`, `uv.lock`): `uv sync`, then
`uv run scripts/…`. ruff lints and formats; every function has a docstring.
pytest unit tests in `tests/test_<script>.py` hold every script at 95%+
line-and-branch coverage (`tests/coverage_gate.py`); they draw synthetic
artwork against the real configs and never touch the real tree.
`tests/test_configs.py` checks invariants across the config files.
CONTRIBUTING.md has the checks CI runs and what must change together.
Site: Next.js, Node, Postgres with Drizzle, Cloudflare R2 for images. Assets
live in iCloud Drive.

**Git holds code and config, plus `golden/fixture/`.** The artwork trees
(`{Sport}/`, `Marks/`, `Venues/`), `temp/`, `surveys/` and the golden suite's
renders are gitignored. `golden/fixture/` is a COPY, at the same relative
paths, of just the artwork the golden suite uses; `golden_fixture.py` builds
it from a full run. A checkout without the iCloud folder — a cloud session,
say — can run `golden_ci.py` on the fixture, but not the pipeline or a full
golden run. Say so rather than guessing at results. Never track the real
tree: a checkout or reset would overwrite or delete artwork.

## Layout

```
Uniform Database/
├── README.md                 orientation and how-to for people
├── CONTRIBUTING.md           PR rules, tools, what must change together
├── CLAUDE.md                 this file: rules for agents
├── LICENSE                   source-available; all rights reserved
├── pyproject.toml, uv.lock   dependencies and ruff config
├── docs/reference.md         the pipeline reference (moved out of this file)
├── docs/golden_suite.md      the golden suite, and the fixture/CI workflow
├── configs/
│   canvas_definitions.yaml   canvases, era profiles, assignments
│   view_templates.yaml       composition layouts (48)
│   slots_global.yaml         slots, viewpoints, 31 colorways
│   slots_hailstateunis.yaml  what a combination picks from, per sport
│   modifiers_{name}.yaml     token vocabularies, chained by `extends`
├── scripts/                  see "Commands" below
│   pipeline/                 standardize, compose, derive_crops
│   migration/                bringing artwork in: fix_dpi, nest_elements,
│                             migrate_marks; recanvas, classify, offsize
│   golden/                   golden_plan, golden_run, golden_fixture, golden_ci
├── tests/                    pytest: test_<script>.py, test_configs.py,
│                             conftest.py, coverage_gate.py
├── {Sport}/{Team}/{Slot} {Viewpoint}/{Element}/{file}.png
├── Marks/Football/{Team}/Helmets {Left|Right}/…   native scale, 258 teams
├── Marks/Baseball/{Team}/Hats Front/…             on canvas, 41 teams
├── Venues/{Sport}/{Team}/{Fields|Courts} {Full|Cropped}/…
├── golden/                   golden suite: manifest, plan, pairings, run/,
│                             fixture/ (tracked copy of the artwork it uses)
├── surveys/                  point-in-time listings; local only, not in git
└── temp/                     staging; cleared after nesting
```

Sport sits ABOVE team because canvases are scoped per sport: one
`football_jersey` serves every football program. Sport directory names are
slugged — apostrophes dropped, spaces to underscores — so `Men's Basketball`
is `mens_basketball` everywhere in config.

Vocabularies: football, baseball, basketball, soccer, volleyball and courts
each `extends: shared`; softball `extends: baseball`; `mens_basketball` and
`womens_basketball` each `extends: basketball`. Every sport slug needs a
file. Add every new colorway to `slots_global.yaml` too
(`docs/reference.md`, "Naming grammar").

Teams with full uniform data: football — Mississippi State, EMCC, Jones,
MGCCC, Mississippi College, Northwest, Ole Miss, Raleigh, Southern Miss,
Taylorsville; baseball — Mississippi State, Southern Miss, Taylorsville;
softball — Mississippi State, Taylorsville; men's and women's basketball,
soccer, volleyball — Mississippi State.

## Safety rules — these have cost artwork

- **Know what is authored and what is generated.** `Football/*/Helmets
  Left|Right` are generated from native-scale `Marks/Football/…`, and each
  `Venues/…/… Cropped` from its `… Full`; everything else is authored.
  Generated directories carry a `.generated` marker; `pad` refuses to write
  into a directory of PNGs without one. Edit the source, never the
  generated copy. Detail: `docs/reference.md`, "Provenance".
- **A marker is provenance, not a switch.** Never add one to an authored
  tree, and never `--force` a pad into one (`--force` writes a marker).
  Pad into a `… STD` sibling for authored trees; pad directly into
  `.generated` trees (helmets from Marks).
- **NEVER re-pad standardized output.** `pad` re-applies an era's scale, or
  matches nothing and writes nothing; this destroyed 44 elements once.
  `standardize.py pad` is for authored source only; `recanvas.py` moves
  standardized files to a new canvas; `classify.py` tells you which a file
  is. Detail: `docs/reference.md`, "Never re-pad standardized output".
- **Never track the real artwork tree in git** (see Stack).
- **Numbers are opaque strings.** `03` ≠ `3`, `00` ≠ `0`. Never `int()` them.
- **No generic fallback.** Every element names its own artwork; a fallback
  branch masks a real gap. Don't reintroduce one.
- **The filename is a key**: element identity is the FOLDER, variants are
  the FILES, and no token appears at both levels. Era comes from content
  size, never from the year. Detail: `docs/reference.md`, "Naming grammar"
  and "Invariants".
- **Don't re-derive what was reversed** — corner-anchored helmets, baked hat
  scale, canvas headroom, a `role` axis, generic artwork:
  `docs/reference.md`, "Tried and reversed".

## Canvases in one paragraph

Profiles are keyed `{sport}-{slot}-{viewpoint}`; eras match on content size
within `tolerance` (5px, below the closest 7px pair: helmet back E 667 vs E2
674; where windows overlap, the closest era wins). A `fills: pad` canvas is
the widest post-scale content plus 1px each side, and exactly the tallest
content high (top-centre anchoring needs no vertical margin); the
exceptions are `football_helmet_profile` (no margin) and
`football_helmet_face` (2px each side). `fills: fill` canvases equal their
content. Detail: `docs/reference.md`, "Eras, canvases and profiles".

## Golden suite

Every template, every era, from real elements. **Run it after ANY change to
a template, canvas or profile.**

```
uv run scripts/golden/golden_plan.py     # → golden/PLAN.md + manifest.yaml
uv run scripts/golden/golden_run.py      # → golden/run/index.html + REPORT.md
```

`golden_plan.py` OVERWRITES the manifest; durable knowledge goes in
`golden/pairings.yaml`. CI runs the suite on `golden/fixture/`, which must be
refreshed and committed after any re-plan or change to artwork it copies:
`docs/golden_suite.md`, section 3, is the one description of that workflow.

## Commands

Run as `uv run scripts/{folder}/{script}.py …`. Every script prints its
options with `--help`. Most take `--root` (default: found from the current
directory).

```
pipeline/   standardize.py survey PATH [--profile P] [--elements]
            standardize.py pad SRC DEST [--canvas WxH] [--profile P] [--force]
                                        [--dpi 300] [--anchor top-center]
                                        canvas + profile from DEST path
            derive_crops.py [--sport S] [--apply] cropped surfaces from `derived_from`
            compose.py [--sport football] [--view full] [--team "Mississippi State"]
                       --{slot} ELEMENT … [--{slot}2 ELEMENT …]
                       [--element SLOT=NAME] [--number N] [--number2 N]
                       [--with TOKEN] [--with2 TOKEN] [--player S] [--player2 S]
                       [--helmet-left] [--out out/composed.png] [--json PATH]
                       [--diff COMPOSITE]
migration/  fix_dpi.py check PATH                 always first; every file is 300 DPI
            fix_dpi.py set PATH DPI [--apply]     dry run until --apply
            nest_elements.py [--sport football] [--src] [--dest] [--team] [--apply]
            migrate_marks.py --mode flat|nested|flat-noyear [--src] [--dest]
                             [--team] [--slot-dir] [--viewpoint] [--apply]
            recanvas.py SRC DEST [--canvas NAME] [--apply]
            classify.py PATH [--sport S]          provenance and scale state
            offsize.py PATH [--csv FILE]          within tolerance but not exact
golden/     golden_plan.py [--rescan] [--sport S]
            golden_run.py [--sport S] [--only ID] [--strict]
            golden_fixture.py [--apply]           sync golden/fixture/ from the last full run
            golden_ci.py [--keep]                 what CI runs: the suite on the fixture
```

`--sport`, `--only`, `--with`, `--with2` and `--element` repeat. Scripts
outside `pipeline/` import from it by adding the sibling folder to
`sys.path`. Tests get all three folders via `pythonpath` in
`pyproject.toml`.

`nest_elements`, `recanvas`, `derive_crops`, `migrate_marks`,
`golden_fixture` and `fix_dpi set` dry-run until `--apply` and copy rather
than move. **`pad` writes immediately**, into the destination you name — for
an authored tree pad into a `… STD` sibling, check it, then rename over the
source; a `.generated` tree is padded into directly. Paths beginning
`Marks/` or `Venues/` resolve exactly like sport trees.

Before any scan of the iCloud tree, download evicted files:
`find . -name "*.icloud" -exec brctl download {} \;` (more in
`docs/reference.md`, "Gotchas").

## Where to look

Plain paths, deliberately NOT `@` imports — an `@path` here is loaded into
every session. Read them when the task needs them.

- `docs/reference.md` — provenance, naming grammar, invariants, eras and
  canvases, nesting, composition and ranking, venues, icons, the re-pad
  incident, tried and reversed, gotchas, known gaps
- `docs/golden_suite.md` — the golden suite workflow, fixture and CI
- `configs/canvas_definitions.yaml` — canvases, profiles, assignments; its
  inline notes explain each canvas's sizing and history
- `configs/view_templates.yaml` — every composition layout
- `configs/modifiers_{name}.yaml` — token vocabularies
