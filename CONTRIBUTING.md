# Contributing

How changes are made here. What the project is and how to set it up is in
[README.md](README.md); the full reference for the pipeline (naming,
invariants, eras, composition) is [CLAUDE.md](CLAUDE.md).

## First: don't lose artwork, and don't misfile it

The archive is hand-drawn work that can't be regenerated. A change that can
destroy a file, or file it under the wrong element, era or year, is a bug
whatever its size:

- Scripts that move artwork dry-run until `--apply` and copy rather than
  move. Keep it that way in anything new. `standardize.py pad` is the one
  exception: it writes at once, so pad into a `… STD` sibling and check it
  before replacing the source.
- Never run `pad` on standardized output. That destroyed 44 elements once,
  saved only by iCloud's 30-day recovery (CLAUDE.md, "NEVER re-pad
  standardized output").
- When code changes what something does, change what the docs say in the
  same PR: CLAUDE.md, the script's docstring, `docs/`.

## Pull requests

- **One topic per PR.** A fix you find along the way that's off topic gets
  its own PR.
- **CI must be green** before merging (`.github/workflows/ci.yml`). Two
  jobs: `checks` (lint, formatting, docstrings, every config file parses,
  the unit tests, and 95% coverage of every script) and `golden` (the golden
  suite on `golden/fixture/`). Run the same locally first:

  ```
  uv run ruff check .
  uv run ruff format --check .
  uv run docstr-coverage scripts tests --skip-magic --skip-init
  uv run pytest -n auto
  uv run python tests/coverage_gate.py
  uv run scripts/golden_ci.py
  ```

  When `golden` fails, the job summary lists why, and the run's
  `golden-run` artifact holds the contact sheets and REPORT.md.

- **CI sees only the fixture.** `golden/fixture/` is a copy of the artwork
  the current plan uses, not the whole archive. A PR that touches a template,
  canvas, era profile, or anything `compose.py`, `standardize.py` or the
  golden scripts do also needs a full run on the Mac. Re-plan if the change
  calls for it, and refresh the fixture in the same PR:

  ```
  uv run scripts/golden_plan.py     # if the plan should change
  uv run scripts/golden_run.py      # full run; then golden/run/REPORT.md
  uv run scripts/golden_fixture.py --apply
  ```

- **Say what a change does to the files on disk** when it does more than
  change code: a re-nest, a re-pad, a re-crop, a folder rename.
- Commit messages say why, not only what.

## Tools

[uv](https://docs.astral.sh/uv/) manages Python and the dependencies, and
[ruff](https://docs.astral.sh/ruff/) lints and formats. `uv sync` installs
everything, dev tools included, into `.venv`; `uv run` runs inside it.

```
uv run ruff check .          # lint
uv run ruff check --fix .    # auto-fix safe issues
uv run ruff format .         # format
```

**Dependencies.** Add one with `uv add NAME` (or `uv add --dev NAME` for a
tool), which updates `pyproject.toml` and `uv.lock` together. Commit both.

**Tests.** `tests/test_<script>.py` holds each script's unit tests, run
with pytest. They never touch the real artwork. The `project` fixture
(`tests/conftest.py`) makes a throwaway project linked to the real
`configs/`, and `art()` draws synthetic PNGs at exact content sizes, so the
tests use the same canvases, profiles and eras as the pipeline.

```
uv run pytest -n auto                  # every test, in parallel, with coverage
uv run pytest tests/test_compose.py    # one script's tests
uv run python tests/coverage_gate.py   # 95% or more for every script
```

Coverage counts lines and branches together, and it includes scripts run
as subprocesses (`golden_ci.py` runs others). coverage.py's own threshold
checks only the total, which would let one untested script hide behind the
rest; `coverage_gate.py` checks each script. For a browsable report, run
`uv run pytest --cov-report=html`, then open `htmlcov/index.html`.

A test asserts what the script does: files written, pixels, messages, exit
codes. It never asserts on behaviour that's a bug. Fix the bug, or leave
the path untested and say so in the PR.

**Docstrings.** Every module and function in `scripts/` and `tests/` has
one, nested helpers included. A script's module docstring is its manual:
what it does, how to run it, and what it refuses to do. A test's docstring
says, in one line, what behaviour it checks. To check (`-v 3` lists
anything missing):

```
uv run docstr-coverage scripts tests --skip-magic --skip-init
```

docstr-coverage doesn't read `pyproject.toml`, so the options go on the
command line.

## Things that must change together

| When you change… | …also change |
|---|---|
| A colorway in any `modifiers_{sport}.yaml` | `configs/slots_global.yaml`. Cross-sport colour search reads the global list, which once drifted seven colorways behind. |
| A token's `scope` or `kind` | Nothing else in config, but re-run `nest_elements.py --sport S` as a dry run: scope decides whether a token names the element or is stripped from it. |
| A view template, a canvas or an era profile | Run the golden suite. If you added or removed a template, update the counts in CLAUDE.md and README.md. |
| The canvas of anything a cropped football view is sized from | That view's canvas, which was derived from element extents. Anchors keep everything else still. |
| An outline or stroke in the artwork | Re-measure the profile (`standardize.py survey`): restyling moves the content bounding box. |
| A pairing the golden planner gets wrong | `golden/pairings.yaml`, not `manifest.yaml`, which `golden_plan.py` overwrites. |
| The golden plan (`manifest.yaml`), or any artwork the fixture copies | A full `golden_run.py`, then `golden_fixture.py --apply`, committed with the change. CI can't tell a stale fixture from a current one. |
| A script, a command or an option | Its module docstring, CLAUDE.md's "Commands", and its tests in `tests/test_<script>.py`, which must keep it at 95% or more. |
| A new script | A `tests/test_<script>.py`; `coverage_gate.py` fails any script under 95%, including one with no tests. |
| How the pipeline behaves (resolution, ranking, nesting rules) | The section of CLAUDE.md that describes it, and "Tried and reversed" if it undoes an earlier choice. |
| A dependency | `pyproject.toml` and `uv.lock`, through `uv add` or `uv lock`. |

## Branches

Trunk-based: `main` is the current state, and every change reaches it
through a pull request from a short-lived branch, merged once CI passes.
Suggested protection for `main` (Settings → Rules → Rulesets, targeting the
default branch):

- **Require a pull request before merging**, with 0 required approvals
  (GitHub doesn't let an author approve their own PR, so for one maintainer
  the checks are the gate).
- **Require status checks to pass**: `checks` and `golden` (CI).
- **Block force pushes** and **restrict deletions**.
- **Allowed merge method: squash**, so `main` reads as one commit per pull
  request.

## Don't

- **Don't commit artwork** except through `golden_fixture.py`. PNGs, PSDs
  and the asset trees are gitignored; iCloud is their home until they move
  to R2. `golden/fixture/` holds copies, never originals: don't edit
  artwork there, and don't point git at the real tree. A checkout or reset
  would then overwrite or delete real artwork.
- **Don't add a `.generated` marker to an authored folder**, or `--force` a
  pad into one. A marker says the folder can be rebuilt; on authored work
  that's a lie that costs artwork later.
- **Don't reintroduce a generic fallback** for missing artwork. Every
  element names its own files, so a gap shows up as a gap.
- **Don't skip or weaken a check to get green.** Fix the cause.
