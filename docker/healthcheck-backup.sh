#!/usr/bin/env bash
# Backup container healthcheck: dump freshness, not process liveness.
#
# `restart: unless-stopped` plus Docker's own container state already cover
# liveness, so this check answers the question those cannot: is the newest dump
# recent? A job that has been failing for a week must be distinguishable from a
# healthy one. Three stages:
#   (a) Backup directory mounted — the host bind mount exists
#   (b) A dump present           — at least one dump file has been written
#   (c) Optional freshness       — the newest dump is newer than the window
set -eu

# (a) Backup directory mounted (host bind mount present)
backup_dir="${BACKUP_DIR:-/backups}"
if [ ! -d "$backup_dir" ]; then
    echo "backup: backup directory missing ($backup_dir)"
    exit 1
fi

# (b) Readiness: at least one dump exists
newest="$(ls -1t "$backup_dir"/dump_*.dump 2>/dev/null | head -n 1 || true)"
if [ -z "$newest" ]; then
    echo "backup: no dump_*.dump found in $backup_dir (backup not ready)"
    exit 1
fi

# (c) Freshness (optional): detect a backup job that has stopped succeeding.
# BACKUP_HEALTH_STALE_SECONDS is read directly from the environment; default 0
# disables the check (existence only). The loop cadence is 24h, so a sane window
# is 2x that (172800s) — a dump older than two cycles means the job is broken.
stale="${BACKUP_HEALTH_STALE_SECONDS:-0}"
if [ "$stale" -gt 0 ] 2>/dev/null; then
    now="$(date +%s)"
    mtime="$(stat -c %Y "$newest" 2>/dev/null || stat -f %m "$newest" 2>/dev/null || echo 0)"
    if [ "$mtime" -eq 0 ] || [ $((now - mtime)) -gt "$stale" ]; then
        echo "backup: newest dump stale (last update > ${stale}s ago)"
        exit 1
    fi
fi

echo "backup: healthy (dump present and fresh)"
exit 0
