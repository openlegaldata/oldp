"""sphinx-polyversion configuration.

Builds the docs for the `master` branch and every `vX.Y[.Z...]` release tag
into a single multi-version site under ``docs/_build/html``.

Each revision is built using the *parent* Python environment — no per-revision
venv is created, so the runner must already have ``sphinx``, ``sphinx-rtd-theme``
and ``myst-parser`` installed (see the ``[docs]`` extras in ``pyproject.toml``).
"""

from pathlib import Path

from sphinx_polyversion import apply_overrides
from sphinx_polyversion.driver import DefaultDriver
from sphinx_polyversion.environment import Environment
from sphinx_polyversion.git import Git, file_predicate, refs_by_type
from sphinx_polyversion.sphinx import SphinxBuilder

#: Regex matching branches to build docs for.
BRANCH_REGEX = r"^master$"

#: Regex matching tags to build docs for (matches v0.9.13, v1.0, v1.2.3-rc1, ...).
TAG_REGEX = r"^v\d+\.\d+.*$"

#: Output directory relative to the repo root.
OUTPUT_DIR = "docs/_build/html"

#: Sphinx source directory.
SOURCE_DIR = "docs"

#: Extra arguments for ``sphinx-build``.
SPHINX_ARGS: list[str] = []


def _default(revisions):
    """Landing target: prefer `master`, else the most recently dated tag."""
    branches, tags = refs_by_type(revisions)
    for branch in branches:
        if branch.name == "master":
            return branch
    if tags:
        return max(tags, key=lambda r: r.date)
    if branches:
        return max(branches, key=lambda r: r.date)
    return None


def data(driver, rev, env):
    """Variables exposed to per-version Sphinx templates."""
    revisions = driver.targets
    branches, tags = refs_by_type(revisions)
    return {
        "current": rev,
        "tags": tags,
        "branches": branches,
        "revisions": revisions,
        "latest": _default(revisions) or rev,
    }


def root_data(driver):
    """Variables exposed to the root ``index.html`` template (landing page)."""
    revisions = driver.builds
    return {"revisions": revisions, "latest": _default(revisions)}


# Allow CLI overrides (e.g. `sphinx-polyversion poly.py -o OUTPUT_DIR=...`).
apply_overrides(globals())

root = Git.root(Path(__file__).parent)
src = Path(SOURCE_DIR)

DefaultDriver(
    root,
    OUTPUT_DIR,
    vcs=Git(
        branch_regex=BRANCH_REGEX,
        tag_regex=TAG_REGEX,
        buffer_size=1 * 10**9,
        predicate=file_predicate([src]),
    ),
    builder=SphinxBuilder(src, args=SPHINX_ARGS),
    env=Environment.factory(),
    template_dir=root / "docs" / "templates",
    data_factory=data,
    root_data_factory=root_data,
).run()
