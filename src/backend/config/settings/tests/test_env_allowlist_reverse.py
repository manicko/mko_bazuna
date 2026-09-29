"""Reverse-direction env-contract test: consumed env vars must be allowlisted.

This module asserts the direction that ``test_env_allowlist.py`` does **not**:
that every environment variable the Python source *reads* is present in
``ALLOWED_ENV_VARS``. ``test_env_allowlist.py`` compares a template to the
allowlist; this module derives a fact about the source tree and compares it to
the allowlist. Different subjects, different remedies — hence a separate module
(D4).

What the test asserts
---------------------
``consumed ⊆ ALLOWED_ENV_VARS``, over **all** non-test ``src/**/*.py``. The
scan is whole-tree, not settings-only: ``RUN_TRANSLATION_BACKFILL`` is read in
``apps/core/utils/migrate_locked.py``, which a settings-package scan would not
see, and a settings-only scan of the current tree passes vacuously against the
defect this module exists to catch.

The asymmetry this module deliberately does not assert
------------------------------------------------------
Only the forward direction is asserted. The reverse — "every allowlisted name
is read somewhere in Python" — is **false by construction**: 12 of the 49
allowlist entries have no Python read, and every one of them is deliberate.
They are read by shell scripts, by Compose interpolation, or injected by the
test container. ``SCHEDULER_HEALTH_STALE_SECONDS`` is the worked example: it is
read by ``docker/healthcheck-scheduler.sh`` and set by
``docker-compose.prod.yml``, never by Python. Asserting the reverse would be a
second hand-maintained contract, the exact anti-pattern this block removes.

Coverage boundary
-----------------
The scan covers the **Python channel only**: non-test ``src/**/*.py`` read
through django-environ, ``os.getenv``, ``os.environ.get`` and
``os.environ[...]``. It does **not** cover ``docker/*.sh``, the compose files,
the GitHub Actions ``deploy-check`` env block (BLOCK 4's
``test_deploy_check_env_parity.py``), ``.env.test``'s CLI-injected ``PYTEST_*``
variables, or any template. A reader who believes otherwise will trust it for
the wrong thing.

Scope rule and ``test_migrations.py``
-------------------------------------
A file is scanned if and only if it is a ``.py`` file under ``src/`` and no
path component of its path relative to ``src/`` is exactly ``tests``. Filename
patterns play no part: a substring rule (``"test" in path``) would silently drop
a real module such as ``protest_handler.py``, with no failure anywhere.
``config/settings/test_migrations.py`` is consequently **scanned** — correct,
because it is a Django settings module loaded in a subprocess, and a settings
module is exactly where a new ``env()`` read would be added. It contributes zero
names today because it contains no environment read; that is measured, not
assumed. ``src/backend/testing/`` and ``src/backend/conftest.py`` are likewise
in scope by this rule.

A green run is not evidence
---------------------------
A green run is not evidence that this test *would have caught* CFG-008. Only the
red/green demonstration — removing ``RUN_TRANSLATION_BACKFILL`` from
``ALLOWED_ENV_VARS`` and watching this module go red through the full-tree scan
— establishes that. See the BLOCK 6 red/green demonstration.
"""

from __future__ import annotations

import ast
import codecs
from pathlib import Path

import pytest

from config.settings.base import ALLOWED_ENV_VARS

pytestmark = [pytest.mark.unit, pytest.mark.settings]

# Resolve repository root — same _ROOT walk-up used by test_env_allowlist.py,
# test_prod_logging.py, test_csrf_trusted_origins.py and
# test_deploy_check_env_parity.py. Do not invent a second shape.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_SRC_ROOT = _ROOT / "src"

# A path component equal to this value excludes the file. Component equality,
# never a substring test on the full path string (D5).
_EXCLUDED_PATH_COMPONENTS = frozenset({"tests"})

# Per-line escape hatch: a read carrying `# env-contract:` on the same physical
# line is excluded from the scan and recorded. A plain comment, deliberately not
# a noqa-style lint suppression — ruff rejects an unregistered suppression code
# and bandit does not read one.
# There are zero real users today; the mechanism is proven by
# test_env_contract_opt_out_is_honoured below.
_OPT_OUT_MARKER = "env-contract:"

# django-environ helpers whose variable name is NOT in the call arguments.
# env.db() takes no positional argument at all and implicitly reads
# DATABASE_URL — a visitor that inspects only args[0] is green and wrong.
# Consulted BEFORE args[0]. Any OTHER zero-argument env.<attr>() call is
# recorded as unrecognised and fails test_env_read_shapes_are_all_recognised.
_IMPLICIT_VAR_HELPERS: dict[str, str] = {
    "db": "DATABASE_URL",
    "db_url": "DATABASE_URL",
}

# Read shapes this visitor knows. It asserts on its own coverage: a shape it does
# not recognise is a failure, not a smaller number. Each shape is proven
# reachable by _SHAPE_PROBES below, so no branch of the visitor is dead code and
# no declared shape is silently missing a handler.
_ENV_CALLABLE_NAMES = frozenset({"env"})
_ENV_CAST_ATTRS = frozenset(
    {
        "bool",
        "int",
        "str",
        "list",
        "float",
        "dict",
        "tuple",
        "json",
        "url",
        "path",
        "bytes",
    }
)
_RECOGNISED_READ_SHAPES = frozenset(
    {
        "env(...)",
        "env.<cast>(...)",
        "os.getenv(...) / os.environ.get(...)",
        "os.environ[...]",
    }
)

# One synthetic source per declared shape. Each is scanned and must produce the
# named variable under exactly that shape label, so every handler in the visitor
# is exercised even if the tree does not currently contain a given read form.
_SHAPE_PROBES: dict[str, tuple[str, str]] = {
    "env(...)": ('PLAIN = env("PROBE_BARE")\n', "PROBE_BARE"),
    "env.<cast>(...)": ('PLAIN = env.int("PROBE_CAST")\n', "PROBE_CAST"),
    "os.getenv(...) / os.environ.get(...)": (
        'PLAIN = os.getenv("PROBE_GETENV")\n',
        "PROBE_GETENV",
    ),
    "os.environ[...]": (
        'PLAIN = os.environ["PROBE_SUBSCRIPT"]\n',
        "PROBE_SUBSCRIPT",
    ),
}


class _ScanResult:
    """Outcome of scanning one module: reads, opt-outs and unattributed calls."""

    def __init__(self) -> None:
        self.consumed: set[str] = set()
        self.opt_outs: list[str] = []
        self.unrecognised: list[tuple[str, int, str]] = []
        self.shapes: set[str] = set()


class _EnvReadVisitor(ast.NodeVisitor):
    """Collect environment-variable names read by one module.

    A ``NodeVisitor`` subclass, not an ``ast.walk()`` loop: ``ast.walk()`` yields
    ``Iterator[AST]`` and the ``AST`` base class declares no ``.args`` /
    ``.func`` / ``.value``, so a walk-based scan reads attributes the type does
    not declare. Overriding ``visit_Call`` and ``visit_Subscript`` narrows the
    node type before every attribute read, and is also where the
    unrecognised-shape bookkeeping lives.

    Handles all four read shapes and resolves the implicit-helper table before
    looking at positional arguments. Records any env-ish call it cannot
    attribute to a name in ``unrecognised`` so an unrecognised shape fails
    loudly.
    """

    def __init__(self, filename: str, source_lines: list[str]) -> None:
        self._filename = filename
        self._source_lines = source_lines
        self.result = _ScanResult()

    def _line_opted_out(self, lineno: int) -> bool:
        index = lineno - 1
        if 0 <= index < len(self._source_lines):
            return _OPT_OUT_MARKER in self._source_lines[index]
        return False

    def _record(
        self, name: str, lineno: int, shape: str, *, implicit: bool = False
    ) -> None:
        if not implicit and self._line_opted_out(lineno):
            self.result.opt_outs.append(f"{self._filename}:{lineno}")
            return
        self.result.consumed.add(name)
        self.result.shapes.add(shape)

    def _record_unrecognised(self, lineno: int, shape: str) -> None:
        self.result.unrecognised.append((self._filename, lineno, shape))

    def _constant_first_arg(self, node: ast.Call) -> str | None:
        if not node.args:
            return None
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
        return None

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        func = node.func

        # Shape 1: env("NAME", ...)
        if isinstance(func, ast.Name) and func.id in _ENV_CALLABLE_NAMES:
            name = self._constant_first_arg(node)
            if name is not None:
                self._record(name, node.lineno, "env(...)")
            else:
                self._record_unrecognised(node.lineno, "env(...)")
            self.generic_visit(node)
            return

        # Shape 3: os.getenv("NAME", ...) and os.environ.get("NAME", ...)
        if isinstance(func, ast.Attribute):
            value = func.value
            if (
                func.attr == "getenv"
                and isinstance(value, ast.Name)
                and value.id == "os"
            ):
                name = self._constant_first_arg(node)
                if name is not None:
                    self._record(
                        name,
                        node.lineno,
                        "os.getenv(...) / os.environ.get(...)",
                    )
                else:
                    self._record_unrecognised(
                        node.lineno, "os.getenv(...) / os.environ.get(...)"
                    )
                self.generic_visit(node)
                return

            if func.attr == "get" and (
                isinstance(value, ast.Attribute)
                and value.attr == "environ"
                and isinstance(value.value, ast.Name)
                and value.value.id == "os"
            ):
                name = self._constant_first_arg(node)
                if name is not None:
                    self._record(
                        name,
                        node.lineno,
                        "os.getenv(...) / os.environ.get(...)",
                    )
                else:
                    self._record_unrecognised(
                        node.lineno, "os.getenv(...) / os.environ.get(...)"
                    )
                self.generic_visit(node)
                return

            # Shapes 2 and the implicit-helper case: any env.<attr>(...).
            # Match on the receiver being `env` and the attribute being a known
            # cast OR anything else: an unknown attribute is env-ish and must be
            # recorded, never silently skipped. This is what makes a future
            # zero-argument helper (env.cache(), env.json(), ...) a red test.
            if isinstance(value, ast.Name) and value.id in _ENV_CALLABLE_NAMES:
                name = self._constant_first_arg(node)
                if name is not None and func.attr in _ENV_CAST_ATTRS:
                    self._record(name, node.lineno, "env.<cast>(...)")
                    self.generic_visit(node)
                    return
                if name is not None:
                    # A string argument to an unknown env attribute is still a
                    # name read; attribute it structurally.
                    self._record(name, node.lineno, "env.<cast>(...)")
                    self.generic_visit(node)
                    return
                # Zero-argument helper. Consult the implicit table BEFORE args[0].
                implicit = _IMPLICIT_VAR_HELPERS.get(func.attr)
                if implicit is not None:
                    self._record(
                        implicit, node.lineno, "env.<cast>(...)", implicit=True
                    )
                else:
                    self._record_unrecognised(node.lineno, f"env.{func.attr}(...)")
                self.generic_visit(node)
                return

        self.generic_visit(node)

    def visit_Subscript(self, node: ast.Subscript) -> None:  # noqa: N802
        # Shape 4: os.environ["NAME"]
        value = node.value
        if (
            isinstance(value, ast.Attribute)
            and value.attr == "environ"
            and isinstance(value.value, ast.Name)
            and value.value.id == "os"
        ):
            if isinstance(node.slice, ast.Constant) and isinstance(
                node.slice.value, str
            ):
                self._record(node.slice.value, node.lineno, "os.environ[...]")
                return
            self._record_unrecognised(
                node.lineno, "os.environ[...] (non-constant key)"
            )
            return
        self.generic_visit(node)


def _iter_source_files() -> list[Path]:
    """Yield every non-test ``.py`` file under ``src/``.

    Exclusion is by path-component equality against ``tests`` — never a
    filename pattern, never a substring on the full path.
    """
    files: list[Path] = []
    for path in sorted(_SRC_ROOT.rglob("*.py")):
        rel = path.relative_to(_SRC_ROOT)
        if _EXCLUDED_PATH_COMPONENTS & set(rel.parts):
            continue
        files.append(path)
    return files


def _scan_source(source: str, filename: str) -> _ScanResult:
    """Scan one source string for env reads. Used for files and synthetic input."""
    lines = source.splitlines()
    visitor = _EnvReadVisitor(filename, lines)
    visitor.visit(ast.parse(source, filename=filename))
    return visitor.result


def _consumed_env_vars() -> dict[str, set[str]]:
    """Map each consumed name to the set of relpaths that read it (whole tree)."""
    consumed: dict[str, set[str]] = {}
    for path in _iter_source_files():
        rel = path.relative_to(_SRC_ROOT).as_posix()
        result = _scan_source(path.read_text(encoding="utf-8"), rel)
        for name in result.consumed:
            consumed.setdefault(name, set()).add(rel)
    return consumed


def _unrecognised_reads() -> list[tuple[str, int, str]]:
    """Every env-ish call the visitor could not attribute, over the whole tree."""
    unrecognised: list[tuple[str, int, str]] = []
    for path in _iter_source_files():
        rel = path.relative_to(_SRC_ROOT).as_posix()
        result = _scan_source(path.read_text(encoding="utf-8"), rel)
        unrecognised.extend(result.unrecognised)
    return unrecognised


def test_consumed_env_vars_are_allowlisted() -> None:
    """Every environment variable read by non-test src/**/*.py is allowlisted.

    The reverse direction of the VAL-004 contract. Full-tree, not settings-only:
    RUN_TRANSLATION_BACKFILL is read in apps/core/utils/migrate_locked.py, which
    a settings-package scan would not see.
    """
    consumed = _consumed_env_vars()
    missing = set(consumed) - ALLOWED_ENV_VARS
    readers = {name: sorted(consumed[name]) for name in sorted(missing)}
    assert not missing, (
        "Environment variables read by src/**/*.py but absent from "
        f"ALLOWED_ENV_VARS: {sorted(missing)} (read by: {readers}). Add each to "
        "the Python-consumed group in config/settings/base.py, or use the "
        "'# env-contract:' opt-out comment on the read if it is not a "
        "deployment variable."
    )


def test_env_read_shapes_are_all_recognised() -> None:
    """The visitor understood every env-ish call it met, and no handler is dead.

    Three hazards this closes, in order of how silently they fail:
      1. env.db() reads DATABASE_URL with NO positional argument.
      2. set(os.environ) is a name-set snapshot, not a read of one variable.
      3. a future zero-argument django-environ helper would be missed entirely.
    """
    unrecognised = _unrecognised_reads()
    assert not unrecognised, (
        "env-ish calls the scanner could not attribute to a variable name "
        f"(file, line, shape): {unrecognised}. Teach _EnvReadVisitor the shape, "
        "or use the '# env-contract:' opt-out comment if it is not a deployment "
        "variable."
    )

    # Every declared shape must have a live handler and a probe. Proven on
    # synthetic sources rather than on the current tree, so the assertion does
    # not go red the day a legitimate read form (e.g. os.environ["..."])
    # briefly disappears from src/.
    assert set(_SHAPE_PROBES) == _RECOGNISED_READ_SHAPES, (
        "the declared shape table and its probes disagree: a declared shape has "
        "no probe (its handler may be dead), or a probe names an undeclared shape"
    )
    for shape, (probe_source, probe_name) in _SHAPE_PROBES.items():
        result = _scan_source(probe_source, "<probe>")
        assert probe_name in result.consumed, (
            f"no handler resolved {probe_name!r} for shape {shape!r}; the shape "
            "is declared but its branch is dead"
        )
        assert shape in result.shapes, (
            f"the branch for shape {shape!r} did not label its result"
        )

    assert "DATABASE_URL" in _consumed_env_vars(), (
        "DATABASE_URL was not resolved through the implicit-helper table "
        "(_IMPLICIT_VAR_HELPERS). env.db() takes no positional argument, so a "
        "first-argument-only visitor is green and wrong."
    )

    # A zero-argument env.<attr>() not in the implicit table must be loud.
    unknown_helper = _scan_source(
        'PLAIN = env.cache()\n', "<probe-unknown-helper>"
    )
    assert unknown_helper.unrecognised, (
        "a zero-argument env.<attr>() outside _IMPLICIT_VAR_HELPERS was not "
        "recorded as unrecognised — a future helper would be missed silently"
    )


def test_env_scan_covers_more_than_the_settings_package() -> None:
    """The scan is whole-tree, so a settings-only regression cannot pass silently."""
    files = _iter_source_files()
    assert files, "no source files were scanned — the walk is broken"
    outside_settings = [
        p for p in files if "settings" not in p.relative_to(_SRC_ROOT).parts
    ]
    assert outside_settings, (
        "the scan saw nothing outside config/settings; it must cover all of src/"
    )
    settings_files = [
        p for p in files if "settings" in p.relative_to(_SRC_ROOT).parts
    ]
    assert len(files) > len(settings_files)


def test_env_contract_opt_out_is_honoured() -> None:
    """A read carrying the opt-out marker is excluded and recorded.

    Proven on a synthetic source string, not on a real module: the marker has
    zero users in the tree today and the mechanism must not be shipped untested.
    """
    source = (
        "import os\n"
        "PLAIN = os.getenv('SOME_PLAIN_NAME')\n"
        "HIDDEN = os.getenv('NOT_A_DEPLOYMENT_VAR')  # env-contract: fixture only\n"
    )
    result = _scan_source(source, "<synthetic>")
    assert "SOME_PLAIN_NAME" in result.consumed
    assert "NOT_A_DEPLOYMENT_VAR" not in result.consumed
    assert result.opt_outs == ["<synthetic>:3"]


def test_env_example_points_at_the_tier_templates() -> None:
    """.env.example no longer claims to be comprehensive and points at the tiers.

    Asserts on prose, not on a variable set: an incomplete stub is the *intent*
    after CFG-009, so any assertion of the form "template keys == consumed names"
    would be asserting the defect back into existence.
    """
    raw = (_ROOT / ".env.example").read_bytes()
    assert not raw.startswith(codecs.BOM_UTF8), (
        ".env.example must not carry a UTF-8 BOM"
    )
    text = raw.decode("utf-8")
    title = text.splitlines()[0]
    assert "comprehensive" not in title.lower(), (
        f"the title still claims completeness: {title!r}"
    )
    for tier in (".env.dev.example", ".env.prod.example", ".env.test.example"):
        assert tier in text, f".env.example must point at {tier}"
    assert "cp .env." in text, (
        "the copy-one-of-the-three instructions must survive"
    )


def test_env_prod_example_documents_translation_backfill() -> None:
    """.env.prod.example documents RUN_TRANSLATION_BACKFILL for the migrate one-shot."""
    text = (_ROOT / ".env.prod.example").read_text(
        encoding="utf-8", errors="replace"
    )
    assert "RUN_TRANSLATION_BACKFILL" in text


def test_env_contract_opt_out_users_are_reported_visible() -> None:
    """Docstring-adjacent guard: an unexpected real opt-out is loud in review.

    Not an assertion that there are zero opt-outs (that would force a second edit
    on the first legitimate use). Instead it fails on any opt-out whose line does
    not carry a reason after the marker — so a real use must be visibly justified.
    """
    offenders: list[str] = []
    for path in _iter_source_files():
        rel = path.relative_to(_SRC_ROOT).as_posix()
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            marker = line.find(_OPT_OUT_MARKER)
            if marker == -1:
                continue
            reason = line[marker + len(_OPT_OUT_MARKER):].strip()
            if not reason:
                offenders.append(f"{rel}:{lineno}")
    assert not offenders, (
        "env-contract opt-out(s) without a reason: "
        f"{offenders}. Write '# env-contract: <why>' so the exemption is visible."
    )
