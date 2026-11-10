# Contributing

How changes are made here. What the project is and how to set it up is in
[README.md](README.md); the full reference for the pipeline (naming,
invariants, eras, composition) is [docs/reference.md](docs/reference.md).
[CLAUDE.md](CLAUDE.md) holds the rules AI agents follow and the command list.

## First: don't lose artwork, and don't misfile it

The archive is hand-drawn work that can't be regenerated. A change that can
destroy a file, or file it under the wrong element, era or year, is a bug
whatever its size:

- Scripts that move artwork dry-run until `--apply` and copy rather than
  move, and never overwrite a different file already at the destination.
  Keep it that way in anything new. `standardize.py pad` is the one
  exception: it writes at once (and exits 1 if any file wasn't written), so for an authored tree pad into a `… STD`
  sibling and check it before replacing the source. A `.generated` tree
  (helmets from Marks) is padded into directly; it can be rebuilt.
- Never run `pad` on standardized output. That destroyed 44 elements once,
  saved only by iCloud's 30-day recovery (docs/reference.md, "Never re-pad
  standardized output").
- When code changes what something does, change what the docs say in the
  same PR: `docs/reference.md`, CLAUDE.md, the script's docstring, the
  rest of `docs/`.

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
  uv run scripts/golden/golden_ci.py
  ```

  When `golden` fails, the job summary lists why, and the run's
  `golden-run` artifact holds the contact sheets and REPORT.md (locally:
  `golden/run-ci/`).

- **CI sees only the fixture.** A PR that touches a template, canvas, era
  profile, or what `compose.py`, `standardize.py` or the golden scripts do
  also needs a full run on the Mac and a refreshed fixture in the same PR:
  [docs/golden_suite.md, section 3](docs/golden_suite.md#3-ci--goldenfixture-and-golden_cipy).

- **A refactor must be shown to change nothing.** Green CI says the result
  didn't change, not that a tie-break didn't. `compose.py`'s candidate
  ranking and `golden_plan.py`'s scoring pick between files that all pass, so
  rewriting one can quietly reorder it — ranking on number alone once chose
  `… Grad NCAA.png` over the plain file. Prove it instead: brute-force the
  key over its inputs, or re-run `golden_plan.py` and diff the manifest.
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

**Shared helpers.** Anything more than one script needs — finding the
root and `--root`, reading config and `tolerance`, sport slugs and
directories, the vocabulary, era matching, measuring artwork, walking PNGs,
`DPI` and `MARKER` — lives in `scripts/pipeline/common.py`, and a new
script must use it rather than write its own. Every one of those once
existed in several copies that disagreed: first-match era lookup in some
scripts and closest in others, three root markers, three hidden-file rules,
colorways replaced instead of merged. A new shared helper goes in
`common.py`, with its tests in `tests/test_common.py`. Every script takes
`--root` (`common.add_root_arg`, `common.root_from`).

**Editors.** `scripts/` is a folder of tools, not a package, and its scripts
import each other by adding the sibling folder to `sys.path` at runtime. An
analyser can't follow that, so point yours at `.venv` and give it the same
folders `pyproject.toml`'s `pythonpath` lists — in VS Code,
`python.defaultInterpreterPath` and `python.analysis.extraPaths`. Editor
settings are gitignored, so this is per-person setup, not a committed file.
Without it every third-party and cross-folder import reads as unresolved.

**Pillow.** Resampling filters go through the enum —
`Image.Resampling.LANCZOS`, not the `Image.LANCZOS` alias. The alias still
works at runtime but isn't in Pillow's type stubs, so an editor marks every
use of it unresolved.

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

**Coverage doesn't prove a combination was tried.** `survey --profile` on a
path that also parses crashed on an unbound `canvas`: the override skips the
branch that sets it, and `if parsed and canvas` reads it anyway. Every line
and branch of `cmd_survey` was covered the whole time — the test passed a
path that doesn't parse, so `and` short-circuited before reaching the unbound
name. Where an option overrides something derived from the path, test it both
ways: on a path that parses and on one that doesn't. `cmd_pad` has the shape
to copy, with every name its branches set initialised to `None` above them.

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
| A view template, a canvas or an era profile | Run the golden suite. If you added or removed a template, update the counts in CLAUDE.md, docs/reference.md and README.md. |
| The canvas of anything a cropped football view is sized from | That view's canvas, which was derived from element extents. Anchors keep everything else still. |
| An outline or stroke in the artwork | Re-measure the profile (`standardize.py survey`): restyling moves the content bounding box. |
| A pairing the golden planner gets wrong | `golden/pairings.yaml`, not `manifest.yaml`, which `golden_plan.py` overwrites. |
| The golden plan (`manifest.yaml`), or any artwork the fixture copies | A refreshed `golden/fixture/`, committed with the change ([docs/golden_suite.md](docs/golden_suite.md), section 3). CI can't tell a stale fixture from a current one. |
| A script, a command or an option | Its module docstring, CLAUDE.md's "Commands", README.md wherever it shows the command, and its tests in `tests/test_<script>.py`, which must keep it at 95% or more. |
| A new script | A `tests/test_<script>.py`; `coverage_gate.py` fails any script under 95%, including one with no tests. It takes `--root` and uses `common.py`'s helpers, not copies of them. |
| A helper in `scripts/pipeline/common.py` | `tests/test_common.py`, and every script that calls it: a change there changes all of them. |
| How the pipeline behaves (resolution, ranking, nesting rules) | The section of docs/reference.md that describes it (and CLAUDE.md if it touches a safety rule), and "Tried and reversed" if it undoes an earlier choice. |
| A token string, scope or colorway in any config | `uv run pytest tests/test_configs.py`: no token at both folder and file level, every colorway global. |
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
