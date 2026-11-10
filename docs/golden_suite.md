# Golden example suite

One composition per template per era, drawn from real elements, rendered and
checked so every layout is seen working at least once before the site relies
on it.

## The workflow

```
uv run scripts/golden_plan.py       # 1. plan
#    review golden/PLAN.md, edit golden/manifest.yaml
uv run scripts/golden_run.py        # 2. run
#    review golden/run/index.html and golden/run/REPORT.md
```

Two phases on purpose: you approve **what** gets rendered before anything is
rendered.

## 1. Plan — `golden_plan.py`

Measures one file per element per viewpoint (cached in
`golden/inventory.json`; `--rescan` to refresh), resolves each to an era, and
picks the smallest set of examples so that **every era of every viewpoint
each template places appears at least once**.

| Output | What it is |
|---|---|
| `golden/PLAN.md` | every template, its constraint, each example, and the eras it covers |
| `golden/manifest.yaml` | the same examples as data — **the file you edit** |
| `golden/inventory.json` | every element and its measured era per viewpoint |

How examples are chosen:

- **Greedy coverage** — each example covers as many still-uncovered eras as
  possible, so the suite stays small.
- **Same-year preferred** — within a team, elements from the same year are
  chosen together so a combination looks like something actually worn. When
  an era exists only in another year, coverage wins and the example mixes
  years (e.g. a 1950 helmet with a 1975 jersey, to reach helmet era B).
- **Numbered files preferred**, so number resolution is exercised.
- **Single team per example** — compose works one team at a time, so an era
  only one program has (Jones's Nike N2) is covered by that program.
- **Combos use different elements** for the two uniforms, so a mixed pairing
  actually appears.
- **`if_available` placements never rule an element out** — they are covered
  when present.
- **Explicit placements** (the football helmet-left inset) get one extra
  example each.

### Template constraints

Some templates only accept certain eras. The planner enforces these and prints
them above each template in `PLAN.md`:

| Templates | Rule |
|---|---|
| baseball/softball `*-tq` | three-quarter sleeve jerseys only |
| baseball/softball with a `-tq` sibling | no three-quarter jerseys |
| soccer `*-ls` (non-combo) | long-sleeve jerseys only |
| soccer with a `-ls` sibling | no long-sleeve jerseys |
| soccer `*-combo*` | uniform 1 a field kit, uniform 2 a keeper kit |
| soccer `*-combo-ls` | keeper must be long-sleeve |
| soccer `soccer-combo` | keeper must be short-sleeve |
| volleyball `*-combo-{a}-{b}` | uniform 1 cut `a`, uniform 2 cut `b` |

Folded templates (`volleyball-jersey`, `volleyball-combo`,
`soccer-condensed-combo`) take any cut.

### Gaps

Anything that can't be covered is listed under its template as **Not
coverable** — including eras that exist in the inventory but never fit a
template. Those are reported rather than skipped: a silent gap is how the
first draft of this planner missed Jones's N2 jerseys.

### Known pairings — `golden/pairings.yaml`

When the plan pairs elements you know weren't worn together, record the right
pairing here rather than editing the manifest:

```yaml
baseball:
  Mississippi State:
    - jersey: 2015 Natural Wool
      hat: 2015 Maroon Fauxback
      pants: 2015 Natural Wool
```

A pairing beats every heuristic — name, colourway, year. It exists because
filenames can't express it: nothing in "Natural Wool" and "Maroon Fauxback"
connects the two. And it **survives re-planning**, which a manifest edit
doesn't.

### Editing the manifest

```yaml
- id: football--full--05
  approved: true            # false to skip
  sport: football
  view: full
  team: Mississippi State
  uniform1: {helmet: 1950 Maroon, jersey: 1975 Maroon, pants: 1950 Maroon}
  number: '7'
  expect_eras: {1/helmet/front: B, 1/jersey/front: B, ...}
```

Change any element or number, or add entries of your own — but note that
`golden_plan.py` **overwrites the manifest** every time it runs. Anything you
want to keep across re-plans belongs in `pairings.yaml` instead. `expect_eras` is
what the runner checks against — update it if you swap an element for one of
a different era, or delete the key to skip that check.

## 2. Run — `golden_run.py`

```
uv run scripts/golden_run.py                       # everything approved
uv run scripts/golden_run.py --sport soccer
uv run scripts/golden_run.py --only football--full--05
```

`--only` re-renders one example; the report and sheets still cover every
result on disk.

| Output | What it is |
|---|---|
| `golden/run/index.html` | every contact sheet on one page — **start here** |
| `golden/run/REPORT.md` | defects, notes, per-template summary |
| `golden/run/sheets/` | one sheet per template, defects outlined in red |
| `golden/run/{sport}/{view}/` | each composition, plus compose's JSON result |

### Automatic checks

| Check | Means |
|---|---|
| `FAILED` | a required placement couldn't be resolved |
| `CLIPPED` | opaque **artwork** runs past the canvas by more than 2px. Transparent padding overhang is not a defect; 1–2px is reported as a note |
| `WRONG ERA` | the placed file isn't the era planned — e.g. a short sleeve in a `-ls` view |
| `NUMBER` | a number was asked for and a file with it exists, but another was placed |
| `EXTRA TOKEN` | the placed file carries unrequested tokens while a plainer one with the same number exists — a ranking bug |
| `EMPTY` | the output has no opaque pixels |

### What the checks can't see

Anything that **looks** wrong but measures right: an element sitting
awkwardly, z-order where pieces overlap, a scale that fits but looks off, a
rotation that reads badly. That's what the contact sheets are for — review
every sheet regardless of the defect count.