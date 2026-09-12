#!/usr/bin/env bash
# Full pipeline recovery after a Codespace recycle. Every stage is idempotent:
# completed stages are skipped, so re-running is always safe and cheap.
# Usage: bash recover.sh [stage-to-stop-after]   (stages: env zip db scan harness build prove)
set -x
CA=/workspaces/codespaces-blank/CA
TC=/tmp/eth-contracts
HR=/tmp/harness/probe
IMG=runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255
STOP=${1:-scan}

# ---- stage: env ----
bash $CA/scripts/env_setup.sh
[ "$STOP" = "env" ] && exit 0

# ---- stage: zip (download to /tmp if missing; /workspaces is too small for caching) ----
mkdir -p $TC
for z in contracts bytecodes; do
  if [ ! -s $TC/$z.zip ]; then
    curl -sL -o $TC/$z.zip https://huggingface.co/datasets/Zellic/all-ethereum-contracts/resolve/main/$z.zip
  fi
done
# verify expected sizes
[ "$(stat -c%s $TC/contracts.zip)" = "2251610719" ] || { echo "contracts.zip BAD"; exit 1; }
[ "$(stat -c%s $TC/bytecodes.zip)" = "4139739279" ] || { echo "bytecodes.zip BAD"; exit 1; }
ls -la $TC/*.zip
[ "$STOP" = "zip" ] && exit 0

# ---- stage: db (ingest ~7 min; skip if already built) ----
cd $TC
cp $CA/scripts/*.py .
if [ ! -s $TC/eth_contracts.duckdb ]; then
  python3 -u ingest.py > ingest.log 2>&1 || true   # exits on known NULL-hash assert
  python3 -u finalize.py > finalize.log 2>&1
else
  echo "db exists, skipping ingest"
fi
[ "$STOP" = "db" ] && exit 0

# ---- stage: scan (SKIP the 31-min rescan — import from persistent parquet) ----
N=$(python3 -c "
import duckdb
try:
    print(duckdb.connect('$TC/eth_contracts.duckdb', read_only=True)
          .execute('SELECT count(*) FROM opcode_features').fetchone()[0])
except Exception:
    print(0)")
if [ "$N" -lt 1539858 ]; then
  python3 -u $CA/scripts/import_features.py     # 30s: reads data/opcode_features.parquet
fi
echo "opcode_features rows: $N"
[ "$STOP" = "scan" ] && exit 0

# ---- stage: harness (foundry + kontrol project; idempotent) ----
if [ ! -d $HR ]; then
  mkdir -p /tmp/harness && chmod 777 /tmp/harness
  docker run --rm -v /tmp/harness:/work -w /work $IMG \
    bash -c 'forge init probe --no-git && cd probe && kontrol init --skip-forge'
  docker run --rm -u 0 -v /tmp/harness:/work --entrypoint bash $IMG -c 'chmod -R a+rwX /work'
fi
cp $CA/harness/skeleton/src/*.sol $HR/src/
# compile controls + extract runtime bytecode for the generator (needs solc: run in docker)
docker run --rm -v /tmp/harness:/work -w /work/probe $IMG bash -c 'forge build' \
  > $CA/harness/forge_build.log 2>&1 || { tail -5 $CA/harness/forge_build.log; exit 1; }
docker run --rm -u 0 -v /tmp/harness:/work --entrypoint bash $IMG -c 'chmod -R a+rwX /work'
python3 - <<'PYEOF'
import json
for name in ['VulnerableControl', 'SafeControl']:
    d = json.load(open(f'/tmp/harness/probe/out/Controls.sol/{name}.json'))
    bc = d['deployedBytecode']['object']
    if bc.startswith('0x'):
        bc = bc[2:]
    open(f'/tmp/harness/{name}.hex', 'w').write(bc)
    print(name, len(bc) // 2, 'bytes runtime code')
PYEOF
[ "$STOP" = "harness" ] && exit 0

# NOTE: proofs run only in CI (public repos), never locally. recover.sh rebuilds
# the DB + features + harness sources and stops here.
echo "RECOVER_DONE (db + features + harness ready)"
