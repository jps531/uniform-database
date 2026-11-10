# Pipeline reference

How the asset pipeline models, names, sizes and composes uniform artwork,
and the mistakes not to repeat. [README.md](../README.md) is orientation and
how-to; [CONTRIBUTING.md](../CONTRIBUTING.md) has the PR rules;
[CLAUDE.md](../CLAUDE.md) is the short list of rules AI agents must follow,
and points here for the detail. The golden suite has its own document,
[golden_suite.md](golden_suite.md).

Contents:

1. [Provenance — authored vs generated](#provenance--authored-vs-generated)
2. [Naming grammar](#naming-grammar)
3. [Invariants](#invariants)
4. [Eras, canvases and profiles](#eras-canvases-and-profiles)
5. [Nesting](#nesting)
6. [Composition](#composition)
7. [Venues](#venues)
8. [Icons](#icons)
9. [Never re-pad standardized output](#never-re-pad-standardized-output)
10. [Tried and reversed — don't re-derive](#tried-and-reversed--dont-re-derive)
11. [Gotchas](#gotchas)
12. [Known gaps](#known-gaps)

## Provenance — authored vs generated

Getting this wrong loses artwork.

| Tree | Status |
|---|---|
| `Marks/Football/*/Helmets Left\|Right` | authored, NATIVE scale — the source |
| `Football/*/Helmets Left\|Right` | **generated** from Marks |
| `Venues/*/*/… Cropped` | **generated** from `… Full` by derive_crops.py |
| everything else | authored, standardized in place |

Generated directories carry a `.generated` marker recording their source.
`pad`, `recanvas` and `derive_crops` all refuse to write into a directory
holding PNGs without one, and write one when they write files; `recanvas`
also refuses a destination equal to its source.

    find . -name .generated | sort   # 2 per football team (Left, Right),
                                     # plus each Venues "… Cropped"

- **A marker is provenance, not a switch.** Never add one to an authored
  tree. `--force` writes one — so forcing a pad into an authored tree
  permanently mislabels it as rebuildable. To add files to an authored tree,
  pad into a `… STD` sibling, delete its marker, copy the contents across.
  A generated tree (helmets from Marks) is padded into directly.
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
- **Vocabularies extend one another.** `modifiers_shared.yaml` holds tokens
  used by more than one sport — conference, postseason, commemorative and
  university marks. They're shared because they're institutional, not
  because sports resemble each other. Football, baseball, basketball,
  soccer, volleyball and courts each `extends: shared`. Softball
  `extends: baseball`, and `mens_basketball` and `womens_basketball` each
  `extends: basketball`, so they reach shared through it. A token redefined
  in a sport's file wins. Courts have their own vocabulary. Every sport slug
  needs a file — softball's and both basketballs' hold only the `extends`
  and `tokens: {}`.
- **Add every new colorway to `slots_global.yaml` too.** It drifted seven
  colorways behind the sport files once; cross-sport colour search depends on
  the global list. `tests/test_configs.py` now checks it.

## Invariants

**Element identity is the FOLDER; variants are the FILES.**

**Scope is structural.** Folder-level tokens are designs, file-level ones are
patches or variations. No token appears at both levels within one sport's
vocabulary (`tests/test_configs.py` checks it; Southern Miss's `Eagle` bumper
became `EagleHead` because `Eagle` is also a design).

**Era is a property of the element, never the year.** Derive it from content
size. Two designs debuted a season early; 1947 Maroon looks leather-era by
year but is plastic by size, and the file is right.

**Numbers are opaque strings.** `03` ≠ `3`, `00` ≠ `0`. Never `int()` them.

**Numbers are per-viewpoint.** Resolution: the numbered file, else the
unnumbered one, else fail — never a file with a different number. With no
number requested, an unnumbered file comes first. This needs one invariant: within each full
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

Profiles live in `configs/canvas_definitions.yaml`, keyed
`{sport}-{slot}-{viewpoint}`. The sport is required — without it, baseball's
1777px jerseys were matched against football's eras and everything came back
unmatched.

- **Eras match on CONTENT size**, within a 5px tolerance. The closest
  distinct pair is 7px (football helmet back E 667 vs E2 674), so keep
  tolerance below that. At 5 the two windows overlap for content 669–672px
  wide; a size there takes the CLOSEST era.
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
- **Softball's profiles are copies of baseball's**, not references: the key
  carries the sport. Change a size in one, change it in the other.
- **Restyling artwork moves its content bbox.** Re-measure the profile after
  any stroke or outline change.

**Canvas size.** A `fills: pad` canvas is the largest post-scale content of
every era assigned to it, plus 1px each side horizontally, and exactly the
tallest content vertically (artwork sits on the top edge, so the anchored
axis needs no margin): width = widest + 2, height = tallest. Measured from
the config, every padded canvas follows that except two:

- `football_helmet_profile` is exactly its content, 940x854, with no margin
  at all (940 wide from era F, 854 tall from era D).
- `football_helmet_face` is 678 wide against 674 of content (era E2), 2px
  each side — it matches the 676 the E2 back entry once recorded.

Padding puts every era at one placement and bakes in scale — it is NOT
headroom. A file that would fall outside its canvas is skipped by `pad`,
which prints the smallest canvas that would fit it. `fills: fill` canvases
— football pants and sleeves, icons, fields and courts — have canvas =
content and absorb no drift; fix drift at source there. Baseball and
softball pants are padded.

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
- Cut variants (`-tq`, baseball only; `-ls`, soccer) exist because those
  eras sit on different canvases. Folded templates (`volleyball-jersey`,
  `volleyball-combo`, `soccer-condensed-combo`) accept any cut.
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

## Never re-pad standardized output

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
| `recanvas.py` | standardized files → a new canvas, scale untouched. Slot canvas only, top-centre: a cut with its own era `canvas:` is reported as too big, not placed |
| `classify.py` | anything you're unsure of: RAW / OLD-STD / NEW-STD, SCALED. On a `fills: fill` canvas it says FILL: canvas size can't tell source from output there |

A standardized tree can't be surveyed for era coverage either — survey the
source, then verify output by checking each file equals its canvas.

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
  standardized in place sit on their padded canvas (the slot's, or an
  era's own) and are skipped, so run it on authored or raw source.
- Inside overlapping tolerance windows (helmet back E/E2, 669–672px — see
  `canvas_definitions.yaml`), `classify` and the golden suite pick the
  CLOSEST era, while `pad`, `offsize` and `migrate_marks` still take the
  first listed. One shared matcher, closest-wins, is planned.
- Exporting from Numbers: CSV cells keep their displayed decimal places, so
  set them before exporting or scales round to integers.

## Known gaps

Near-misses: an early `offsize.py` run listed ~100 football files 1–3px
off their profile — within tolerance, so they standardize fine. 17 are the
Nike/Adidas jersey-back overlap above. That list is stale; re-run
`offsize.py` on the authored source for the current one (see Gotchas).

Squared edges, accepted: until the fix, `pad` pasted each file with itself
as the mask, which squared the alpha of every anti-aliased pixel (128 -> 64).
Every tree standardized in place before then keeps those edges; its
unsquared originals exist only in the Phase 0 backups. Generated helmets
are rebuilt from native Marks, so re-padding them restores theirs.

Coverage, not correctness: Ole Miss `1979 Navy` helmet has no icon; five
Southern Miss pants (1987 Black/Gold/White, 1988 Gold, 1997 White) have an
icon but no Front or Left.

The Southern Miss bumper token was renamed `Eagle` → `EagleHead` in config;
its artwork files are renamed by hand, outside the repository.
