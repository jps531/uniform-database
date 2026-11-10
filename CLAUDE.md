# Uniform Database

A uniform-tracking archive and website for Mississippi State athletics and
the programs around it. Hand-drawn uniform element PNGs are standardized onto
fixed canvases, then composed on demand into combination graphics.

Replaces two legacy sites:
- **hailstateunisdatabase.com** — PHP/MySQL, game-by-game uniform records
- **hailstateunis.com** — Weebly, narrative uniform history

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
├── README.md                 orientation for people; this file is for agents
├── CONTRIBUTING.md           PR rules, tools, what must change together
├── CLAUDE.md
├── LICENSE                   source-available; all rights reserved
├── pyproject.toml, uv.lock   dependencies and ruff config
├── docs/golden_suite.md
├── configs/
│   canvas_definitions.yaml   canvases, era profiles, assignments
│   view_templates.yaml       composition layouts (48)
│   slots_global.yaml         slots, viewpoints, 31 colorways
│   slots_hailstateunis.yaml  what a combination picks from, per sport
│   modifiers_{sport}.yaml    token vocabularies; all `extends: shared`
├── scripts/                  see "Commands" below
│   pipeline/                 standardize, compose, derive_crops
│   migration/                bringing artwork in: fix_dpi, nest_elements,
│                             migrate_marks; recanvas, classify, offsize
│   golden/                   golden_plan, golden_run, golden_fixture, golden_ci
├── tests/                    pytest: test_<script>.py, conftest.py, coverage_gate.py
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

Teams with full uniform data: football — Mississippi State, EMCC, Jones,
MGCCC, Mississippi College, Northwest, Ole Miss, Raleigh, Southern Miss,
Taylorsville; baseball — Mississippi State, Southern Miss, Taylorsville;
softball — Mississippi State, Taylorsville; men's and women's basketball,
soccer, volleyball — Mississippi State.

## Provenance — authored vs generated

Getting this wrong loses artwork.

| Tree | Status |
|---|---|
| `Marks/Football/*/Helmets Left\|Right` | authored, NATIVE scale — the source |
| `Football/*/Helmets Left\|Right` | **generated** from Marks |
| `Venues/*/*/… Cropped` | **generated** from `… Full` by derive_crops.py |
| everything else | authored, standardized in place |

Generated directories carry a `.generated` marker; `pad` refuses to write
into a directory holding PNGs without one.

    find . -name .generated | sort   # 2 per football team (Left, Right),
                                     # plus each Venues "… Cropped"

- **A marker is provenance, not a switch.** Never add one to an authored
  tree. `--force` writes one — so forcing a pad into an authored tree
  permanently mislabels it as rebuildable. To add files to an authored tree,
  pad into a `… STD` sibling, delete its marker, copy the contents across.
- **A Marks tree that feeds a generated tree stays native; a terminal one is
  standardized.** Football helmet marks are rescaled on the way into
  `Football/` and must stay at native size (2238x1904 for a Speedflex).
  Baseball hat marks are consumed directly, so they sit on canvas.
- **Hat marks are for teams you do NOT track.** If a team with marks gains
  uniform data, move its hats into `Baseball/`, don't copy — a team in
  `Marks/` but not in a sport tree signals "uniforms not catalogued."

## Naming grammar

```
Element folder : {first_year_worn} {colorway} [{design modifier}]
File           : {element} [{form}] [{sequence}] [{number}] [{patch…}] [{surname}]
```

**The filename is a KEY, not a description.** It must be unique, stable and
parseable; the database carries the descriptive fields.

Token kinds, in `modifiers_{sport}.yaml`:

| kind / scope | Level | Examples |
|---|---|---|
| `scope: design` | folder | `Egg Bowl`, `Pinstripes`, `Keeper`, `85s` |
| `scope: patch` | file | bowl patches, `NCAA`, `Grad`, `SEC75` |
| `scope: variation` | file | `Teal Belt`, `Empty Shoulders` |
| `kind: finish` | folder | `Matte` |
| form: `shell` / `cut` / `style` | file | `Speedflex`; `Vest`; `Classic`/`Modern` hats |
| `kind: sequence` | either | `A`, `B` — bare disambiguators, no meaning |

- **`token` vs `label`.** Token is the exact filename string, label the
  display name (`SBC` / "Sun Belt Conference"). Colorways match on either
  the key or the label (`Powder` / "Powder Blue").
- **`default: true`** on a form token makes it win unasked: Speedflex for
  football helmets, Modern for baseball hats.
- **Vocabularies `extends: shared`.** Shared holds tokens used by more than
  one sport — conference, postseason, commemorative and university marks.
  They're shared because they're institutional, not because sports
  resemble each other. A token redefined in a sport's file wins. Softball
  uses baseball's vocabulary; courts have their own. Every sport slug needs a
  file — softball's and both basketballs' only `extends`.
- **Add every new colorway to `slots_global.yaml` too.** It drifted seven
  colorways behind the sport files once; cross-sport colour search depends on
  the global list.

## Invariants

**Element identity is the FOLDER; variants are the FILES.**

**Scope is structural.** Folder-level tokens are designs, file-level ones are
patches or variations. No token appears at both levels.

**Era is a property of the element, never the year.** Derive it from content
size. Two designs debuted a season early; 1947 Maroon looks leather-era by
year but is plastic by size, and the file is right.

**Numbers are opaque strings.** `03` ≠ `3`, `00` ≠ `0`. Never `int()` them.

**Numbers are per-viewpoint.** Resolution: the numbered file, else the
unnumbered one, else fail. This needs one invariant: within each full
discriminator set `(element, viewpoint, form, sequence)`, files are ALL
numbered or ALL unnumbered. Check at that granularity — at
`(element, viewpoint)` alone it over-reports badly.

**Full discriminator set:**
`(element, viewpoint, form, sequence, number, player)`.

**No generic fallback.** Every element names its own artwork. Generic pants
were replaced by explicit duplicates because a fallback branch can mask a
real gap. Don't reintroduce one.

**A disambiguator appears only where a name would otherwise be ambiguous.**
One of three long-sleeve soccer keepers carries `Long Sleeve` — the only one
worn alongside a short-sleeve twin. `Classic`/`Modern` appear on 2 of 54
hats. Don't "fix" these by adding the token everywhere; the cut is already
identified by content size.

**`viewpoints` ≠ `symmetric`.** One is what artwork exists; the other is
whether the left view adds information.

**Viewpoints may hold different file counts for one element.** Not a defect.

## Eras, canvases and profiles

Profiles live in `canvas_definitions.yaml`, keyed `{sport}-{slot}-{viewpoint}`.
The sport is required — without it, baseball's 1777px jerseys were matched
against football's eras and everything came back unmatched.

- **Eras match on CONTENT size**, within a 5px tolerance. The closest
  distinct pair is 7px (football helmet back E 667 vs E2 674), so keep
  tolerance below that.
- **Eras are shared across teams and manufacturers.** Football jerseys carry
  A–E (Adidas), N1–N3 (Nike), UA1 (Under Armour) — parallel tracks, not a
  sequence. Women's basketball shorts and volleyball's cuts are parallel too.
- **An era may set `canvas:`** to override the slot canvas — used where one
  cut is far larger than the rest (baseball three-quarter sleeves, soccer and
  volleyball long sleeves).
- **An era may set `scale:`**, baked into the standardized file: football
  jersey era A (21.5/24), helmet face era A (716/935), every helmet profile
  era. These are the only DESTRUCTIVE eras to re-pad.
- **Declare each era explicitly** rather than widening tolerance.
- **Restyling artwork moves its content bbox.** Re-measure the profile after
  any stroke or outline change.

**Canvases are the largest post-scale content plus 1px each side.** Padding
puts every era at one placement, bakes in scale and absorbs drift — it is
NOT headroom. `fills: fill` canvases — football pants and sleeves, icons, fields and
courts — have canvas = content and absorb no drift; fix drift at source
there. Baseball and softball pants are padded.

**Anchors are top-centre everywhere.** Resizing a canvas therefore never moves
artwork — except in views whose own canvas size was derived from element
extents (the cropped football views), which must be recomputed.

## Nesting

`nest_elements.py --sport {sport}` derives the element folder as the filename
minus everything that isn't design:

- **Stripped:** patch and variation tokens; form tokens; the number, wherever
  it sits (`2015 White 85s 19 Grad`); a sequence letter right after a
  stripped token or the number.
- **Kept:** everything else. Keeping is the DEFAULT, so a token of an
  unexpected kind stays in the name rather than vanishing.
- A letter after a number is a variant (`34 A`); after the colorway it's a
  design (`2014 White A` and `B` are different helmets).
- **Surname** is a parsed field: a trailing capitalised word outside the
  design vocabulary (`18 Girodo`). Eyeball the extracted surnames after any
  parse.
- Match the vocabulary by LONGEST MATCH first: `Flying M` and `M over S` end
  in a capital, `DWS100` in digits.

## Composition

`compose.py` takes one optional flag per slot (`--helmet`, `--jersey`,
`--hat`…) plus a `2` form for combo views (`--jersey2`, `--number2`); the
template decides which it needs. `--with TOKEN` requires a token,
`--player SURNAME` picks between same-number files, `--json` writes a
structured result.

**Candidate ranking:** requested number → every `--with` token → requested
player → FEWEST unrequested tokens → `default` form → filename. Ranking on
number alone once picked `… Grad NCAA.png` over the plain file because a space
sorts before a period.

**Templates** (`view_templates.yaml`, 48): football 8, baseball 8, softball 4,
men's and women's basketball 6 each, soccer 10, volleyball 6.

- Placements are `x` = horizontal centre, `y` = top. `uniform: 2` marks the
  second kit in a combo, deliberately smaller as an inset; in soccer it is
  always the keeper.
- Cut variants (`-tq`, `-ls`) exist because those eras sit on different
  canvases. Folded templates (`volleyball-jersey`, `volleyball-combo`,
  `soccer-condensed-combo`) accept any cut.
- **Choosing the wrong cut variant clips silently** — the site must select
  the view from the element's era, e.g. a long-sleeve keeper needs
  `soccer-combo-ls`.
- z-order: shorts under jersey except in condensed views; shorts front over
  back; the uniform-2 inset above uniform 1.

## Venues

Fields and courts are NOT uniform elements. They stay out of combinations
because `field` and `court` appear in `directory_slots` (path parsing) but
NOT in `slots_hailstateunis.yaml` (what a combination picks from). That
separation is the whole mechanism — don't "fix" it.

`Venues/Basketball` is ungendered: both programs share Humphrey Coliseum.
Crop geometry is per sport and measured, never inherited: football's is
centred, baseball's and basketball's trim from the bottom only.

## Icons

Separately drawn 750x750 squares, authored, not derivable from views. One per
element, plus extras only where a number or bowl patch is visible at that
size. Resolution drops shell, number and bowl patch and KEEPS design
modifiers — `2012 White Egg Bowl` is a different element from `2012 White`.
Icons can exist with no matching element and vice versa.

## Golden suite

Every template, every era, from real elements. See `docs/golden_suite.md`.

```
uv run scripts/golden/golden_plan.py     # → golden/PLAN.md + manifest.yaml
uv run scripts/golden/golden_run.py      # → golden/run/index.html + REPORT.md
```

**Run it after ANY change to a template, canvas or profile.** It has caught
a placement corrupted by a text replace, three templates with zero examples,
80 helmet backs whose profile described only 3 of them, and 1–3px clipping
in 16 templates.

- `golden_plan.py` OVERWRITES the manifest. Durable knowledge goes in
  `golden/pairings.yaml` (uniforms known to be worn together).
- **CI** runs `golden_ci.py` on `golden/fixture/`: `golden_run.py --strict`
  (a note fails too, and so does selecting nothing), every fixture Marks
  helmet re-padded and compared pixel for pixel with its generated copy
  (all eras A–F, both sides), and
  every cropped venue re-derived and compared. After any re-plan, or any
  change to artwork the fixture copies, run a full `golden_run.py`, then
  `golden_fixture.py --apply`, and commit the fixture. CI can't see a stale
  fixture.
- Clipping is judged on ARTWORK, not padding. Every era of every placement
  is covered — 90 of 90 archive-wide, 48 of 48 templates.

## NEVER re-pad standardized output

`pad` resolves an era from content size and applies its scale. Run on output
whose correction is already baked in, it applies the scale twice — or
matches no era and silently writes nothing.

**This destroyed 36 jersey and 8 helmet elements** (football era A, recovered
from iCloud's 30-day window). A re-pad measured 1604x1862 against a profile
listing 1790x2078, wrote nothing, and `rm -rf` of the source did the rest. The
old guard only compared canvas size, and the same pass had changed the
canvas. It now refuses any file whose content matches what an era's scale
PRODUCES, and skips any file already sitting on the slot canvas or on any
era's own `canvas:`, whatever order the files come in. `fills: fill`
canvases are exempt from that canvas check: source cropped to its content
already IS the canvas there, and the post-correction check still catches
scaled output. Fully transparent files count as neither source nor output,
and a pad that writes nothing leaves no destination and no marker.

| Tool | Use on |
|---|---|
| `standardize.py pad` | authored source only |
| `recanvas.py` | standardized files → a new canvas, scale untouched |
| `classify.py` | anything you're unsure of: RAW / OLD-STD / NEW-STD, SCALED |

A standardized tree can't be surveyed for era coverage either — survey the
source, then verify output by checking each file equals its canvas.

## Commands

Run as `uv run scripts/{folder}/{script}.py …`.

```
pipeline/   standardize.py survey PATH [--elements]
            standardize.py pad SRC DEST           canvas + profile from DEST path
            derive_crops.py [--sport S] [--apply] cropped surfaces from `derived_from`
            compose.py --sport S --view V --{slot} ELEMENT …
migration/  fix_dpi.py check|set PATH [300]       always first; every file is 300 DPI
            nest_elements.py --sport S [--src] [--dest] [--apply]
            migrate_marks.py --mode flat|nested|flat-noyear
            recanvas.py SRC DEST [--apply]
            classify.py PATH [--sport S]          provenance and scale state
            offsize.py PATH                       within tolerance but not exact
golden/     golden_plan.py / golden_run.py [--strict]
            golden_fixture.py [--apply]           sync golden/fixture/ from the last full run
            golden_ci.py [--keep]                 what CI runs: the suite on the fixture
```

Scripts import each other across folders by adding the sibling folder to
`sys.path` (`offsize`, `migrate_marks`, `golden_fixture` and `golden_ci`
use `pipeline/`). Tests get all three via `pythonpath` in `pyproject.toml`.

`nest_elements`, `recanvas`, `derive_crops` and `migrate_marks` dry-run
until `--apply` and copy rather than move. **`pad` writes immediately**, into
the destination you name — pad into a `… STD` sibling, check it, then rename
over the source. Paths beginning `Marks/` or `Venues/` resolve exactly like
sport trees.

## Tried and reversed — don't re-derive

- **Corner-anchored helmet profiles.** Kept shells aligned across eras, but
  nobody overlays eras, and a facemask-less leather helmet showed 265px of
  empty space. Content balance beats shell alignment.
- **Baking the hat scale to fix stroke weight.** Hats compose at 19% and their
  outline rendered ~1px against the jersey's 6px. Baking the scale shrinks
  the outline too, so the rendered stroke is identical and only resolution is
  lost. The fix was an artwork change: thicken the source stroke by 1/scale.
  Master scale and stroke weight are separate problems.
- **Canvas headroom.** ~7–12% margins cost football_jersey 21% of its area.
  Replaced by the 1px rule.
- **A `role` axis** (soccer field/keeper, volleyball libero). Keepers are
  distinct designs (`Keeper` token); a libero wears an existing jersey. Roles
  exist at the appearance level, not the asset level.
- **Generic fallback artwork.** See Invariants. The one-off
  `expand_generics.py` that replaced it was applied and then deleted; it's in
  git history if ever needed.

## Gotchas

- iCloud evicts files to `.name.png.icloud`. Run
  `find . -name "*.icloud" -exec brctl download {} \;` before any scan.
- Finder "rotate" writes an EXIF tag rather than rotating pixels. Scripts
  apply `exif_transpose`, but on a SQUARE image a wrong orientation is
  invisible to every size check — 37 pants icons composed sideways once.
- DPI has arrived as 300, 150, 144, 72 and untagged. Photoshop places by
  physical size, so mixed DPI makes transform percentages meaningless.
- Jersey backs can't distinguish Nike early (1414x2042) from Adidas D
  (1414x2039) — inside tolerance, ~17 files carry the wrong label. Harmless
  (both scale 1.0). If manufacturer matters, it needs a filename token.
- "Shares a canvas" and "shares dimensions" are different claims — football
  jersey fronts and backs differed by 19px in eras B and C.
- `offsize.py` says "exact" only when it checked at least one file. A path
  matching no profile is listed under `!! skipped`. It used to build profile
  keys without the sport, miss every lookup and still report "exact". Files
  standardized in place sit on their padded canvas and are skipped, so run
  it on authored or raw source.
- Exporting from Numbers: CSV cells keep their displayed decimal places, so
  set them before exporting or scales round to integers.

## Known gaps

Near-misses: an early `offsize.py` run listed ~100 football files 1–3px
off their profile — within tolerance, so they standardize fine. 17 are the
Nike/Adidas jersey-back overlap above. That list is stale; re-run
`offsize.py` on the authored source for the current one (see Gotchas).

Coverage, not correctness: Ole Miss `1979 Navy` helmet has no icon; five
Southern Miss pants (1987 Black/Gold/White, 1988 Gold, 1997 White) have an
icon but no Front or Left.

## Where to look

Plain paths, deliberately NOT `@` imports — an `@path` here is loaded into
every session, and these four come to ~1,500 lines. Read them when the task
needs them.

- `configs/canvas_definitions.yaml` — canvases, profiles, assignments; its
  inline notes explain each canvas's sizing and history
- `configs/view_templates.yaml` — every composition layout
- `configs/modifiers_{sport}.yaml` — token vocabularies
- `docs/golden_suite.md` — the golden suite workflow