#!/usr/bin/env bash
# One-shot environment setup after a Codespace recycle/rebuild. Idempotent.
set -x

# 1. 16GB swap (Kontrol requirement) — on /tmp (118G volume)
if ! swapon --show | grep -q swapfile; then
  sudo fallocate -l 16G /tmp/swapfile
  sudo chmod 600 /tmp/swapfile
  sudo mkswap /tmp/swapfile >/dev/null
  sudo swapon /tmp/swapfile
fi
free -h | tail -1

# 2. Python deps (usually survive on root FS, but cheap to verify)
python3 -c "import duckdb" 2>/dev/null || pip install --quiet duckdb
python3 -c "import pandas, pyarrow" 2>/dev/null || pip install --quiet pandas pyarrow
python3 -c "import numpy" 2>/dev/null || pip install --quiet numpy

# 3. Docker daemon up + kontrol image present (pulls ~2.1GB compressed if missing)
if ! docker info >/dev/null 2>&1; then
  sudo service docker restart 2>/dev/null || true
  sleep 3
fi
docker images | grep -q kontrol || docker pull runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255

# 4. git safe.directory (root-owned repo edge case)
git config --global --add safe.directory /workspaces/codespaces-blank || true

echo "ENV_SETUP_DONE"
