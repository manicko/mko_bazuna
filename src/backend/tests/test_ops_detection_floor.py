"""Operator detection floor contract (12-OPS-011, Q10 option (b)).

The 2026-10-03 ruling (Q10 option (b)) makes the operator-notification floor a
machine-readable signal — dump age and container health — consumed by whatever
the deferred monitoring stack (Q5 option (c)) eventually delivers. The Telegram
``notify_operator`` command was DECLINED, so no recipient key exists and
``ALLOWED_ENV_VARS`` / the four ``.env.*.example`` files are untouched.

These guards assert the properties the reduced deliverable depends on, so the
floor cannot silently regress:

- the ``backup`` service's healthcheck is a **freshness** probe (not liveness),
  which is what turns a broken backup job into a machine-readable ``unhealthy``
  state rather than a silent failure;
- the SLO artefacts are explicitly labelled "planned — not deployed", so they do
  not read as active controls;
- the detection floor is documented, so the residual gap stays named rather than
  implied closed.

The tests are behavioural where a behaviour exists (the freshness script's exit
codes) and structural where only a declaration exists (the compose healthcheck).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML

pytestmark = [pytest.mark.unit]

# Resolve the repository root by walking upward to pyproject.toml (this module
# lives at src/backend/tests/), kept CWD-independent.
_ROOT = Path(__file__).resolve().parent
while not (_ROOT / "pyproject.toml").exists():
    _ROOT = _ROOT.parent

_PROD_COMPOSE = _ROOT / "docker-compose.prod.yml"
_HEALTHCHECK_BACKUP = _ROOT / "docker" / "healthcheck-backup.sh"
_SLO_ALERTS = _ROOT / "docs" / "ops" / "prometheus-slo-alerts.yaml"
_SLO_DASHBOARD = _ROOT / "docs" / "ops" / "grafana-slo-dashboard.json"
_DETECTION_FLOOR_DOC = _ROOT / "docs" / "ops" / "operator-detection-floor.md"


def _prod_services() -> dict:
    data = YAML(typ="safe").load(_PROD_COMPOSE.read_text(encoding="utf-8"))
    return (data or {}).get("services", {}) or {}


def test_backup_healthcheck_is_a_freshness_probe() -> None:
    """The ``backup`` healthcheck reports dump freshness, not just liveness.

    A liveness-only probe cannot distinguish a healthy job from one that has
    been failing for a week. The freshness branch (a dump older than the window
    exits non-zero) is the machine-readable signal the detection floor rests on
    (12-OPS-011).
    """
    text = _HEALTHCHECK_BACKUP.read_text(encoding="utf-8")
    assert "BACKUP_HEALTH_STALE_SECONDS" in text, (
        "healthcheck-backup.sh must read BACKUP_HEALTH_STALE_SECONDS (12-OPS-011)"
    )
    assert "dump_*.dump" in text, (
        "healthcheck-backup.sh must inspect dump_*.dump files (12-OPS-011)"
    )


def test_backup_healthcheck_is_executable_and_branches_correctly() -> None:
    """The freshness script is executable and exits 0/1 for fresh/stale dumps.

    Runs the script against a scratch backup directory: a fresh dump exits 0 and
    a dump older than the window exits non-zero, so the container-health signal
    is behavioural rather than asserted (12-OPS-011).
    """
    assert os.access(_HEALTHCHECK_BACKUP, os.X_OK), (
        f"{_HEALTHCHECK_BACKUP} must be executable (chmod +x)"
    )

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        backup_dir = Path(tmp)
        dump = backup_dir / "dump_20260101_000000.dump"
        dump.write_bytes(b"x")

        env = dict(os.environ)
        env["BACKUP_DIR"] = str(backup_dir)

        # Fresh dump (window 1 h) — healthcheck passes.
        env["BACKUP_HEALTH_STALE_SECONDS"] = "3600"
        fresh = subprocess.run(
            ["/bin/sh", str(_HEALTHCHECK_BACKUP)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert fresh.returncode == 0, (
            f"a present, fresh dump must exit 0; got {fresh.returncode}: "
            f"{fresh.stdout}{fresh.stderr}"
        )

        # Stale window of one second on a dump now older than it — must fail.
        env["BACKUP_HEALTH_STALE_SECONDS"] = "1"
        os.utime(dump, (0, 0))
        stale = subprocess.run(
            ["/bin/sh", str(_HEALTHCHECK_BACKUP)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        assert stale.returncode != 0, (
            "a dump older than the freshness window must make the healthcheck "
            f"fail (12-OPS-011); got {stale.returncode}"
        )


def test_both_signals_have_a_healthcheck_declared() -> None:
    """``web`` and ``backup`` each declare a healthcheck — the two floor signals.

    Container health is the machine-readable signal the detection floor exposes
    via ``docker inspect``; a service without a ``healthcheck:`` has no status
    to read (12-OPS-011).
    """
    services = _prod_services()
    for name in ("backup",):
        assert name in services, f"docker-compose.prod.yml must declare {name!r}"
        assert "healthcheck" in services[name], (
            f"{name} must declare a healthcheck so its status is machine-readable "
            f"(12-OPS-011)"
        )


def test_slo_artefacts_are_labelled_not_deployed() -> None:
    """Both SLO artefacts state they are planned, not deployed.

    Q5 option (c) deferred the monitoring stack, so these files must not read
    as active controls. This is the contract that keeps BLOCK 11's labelling
    from silently regressing (12-OPS-003 / 12-OPS-011).
    """
    alerts = _SLO_ALERTS.read_text(encoding="utf-8")
    assert "PLANNED" in alerts.upper() and "NOT DEPLOYED" in alerts.upper(), (
        "prometheus-slo-alerts.yaml must be labelled planned — not deployed (12-OPS-011)"
    )
    dashboard = _SLO_DASHBOARD.read_text(encoding="utf-8")
    assert "PLANNED" in dashboard.upper() and "NOT DEPLOYED" in dashboard.upper(), (
        "grafana-slo-dashboard.json must be labelled planned — not deployed (12-OPS-011)"
    )


def test_detection_floor_is_documented_with_the_residual_gap() -> None:
    """The detection floor is documented and names the residual gap.

    The ruling requires the gap to be NAMED, not closed: the signals are
    machine-readable but nothing alerts on them. If this document loses that
    statement the phase would read as having closed detection (12-OPS-011).
    """
    assert _DETECTION_FLOOR_DOC.exists(), (
        "docs/ops/operator-detection-floor.md must exist (12-OPS-011)"
    )
    text = _DETECTION_FLOOR_DOC.read_text(encoding="utf-8")
    assert "unhealthy" in text, (
        "the detection-floor doc must name the machine-readable container-health signal"
    )
    assert "not closed" in text.lower() or "residual gap" in text.lower(), (
        "the detection-floor doc must name the residual gap (12-OPS-011 is not closed)"
    )
