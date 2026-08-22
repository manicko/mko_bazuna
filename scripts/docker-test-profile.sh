#!/bin/bash
set -e
# Setup and run profile script for Docker-based test profiling
# This script is executed inside a python:3.14-slim container

# Install uv
pip install uv 2>&1 | tail -5

# Sync dependencies with dev group
cd /app
uv sync --frozen --no-install-project --group dev 2>&1 | tail -10

# Run pytest collect-only with timing
echo "=== COLLECTION ONLY ==="
time uv run pytest --create-db --collect-only -q 2>&1 | tail -20

# Per-marker counts
echo "=== MARKER: seed ==="
uv run pytest --create-db --collect-only -q -m seed 2>&1 | tail -5
echo "=== MARKER: unit ==="
uv run pytest --create-db --collect-only -q -m unit 2>&1 | tail -5
echo "=== MARKER: integration ==="
uv run pytest --create-db --collect-only -q -m integration 2>&1 | tail -5
echo "=== MARKER: settings ==="
uv run pytest --create-db --collect-only -q -m settings 2>&1 | tail -5
echo "=== MARKER: concurrent ==="
uv run pytest --create-db --collect-only -q -m concurrent 2>&1 | tail -5
echo "=== MARKER: slow ==="
uv run pytest --create-db --collect-only -q -m slow 2>&1 | tail -5
