#!/usr/bin/env bash
# Full pipeline recovery after a Codespace recycle. Every stage is idempotent:
# completed stages are skipped, so re-running is always safe and cheap.
# Usage: bash recover.sh [stage-to-stop-after]   (stages: env zip db scan harness build prove)
set -x
CA=/workspaces/codespaces-blank/CA
TC=/tmp/eth-contracts
HR=/tmp/harness/probe
IMG=runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255
STOP=${1:-prove}

# ---- stage: env ----
bash $CA/scripts/env_setup.sh
[ "$STOP" = "env" ] && exit 0

# ---- stage: zip (restore from persistent cache, else download) ----
mkdir -p $TC $CA/cache
for z in contracts bytecodes; do
  if [ ! -s $TC/$z.zip ]; then
    if [ -s $CA/cache/$z.zip ]; then
      cp $CA/cache/$z.zip $TC/$z.zip
    else
      curl -sL -o $TC/$z.zip https://huggingface.co/datasets/Zellic/all-ethereum-contracts/resolve/main/$z.zip
      cp $TC/$z.zip $CA/cache/$z.zip   # persist for next time
    fi
  fi
done
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

# ---- stage: scan (~31 min; skip if features table populated) ----
N=$(python3 -c "
import duckdb
try:
    print(duckdb.connect('$TC/eth_contracts.duckdb', read_only=True)
          .execute('SELECT count(*) FROM opcode_features').fetchone()[0])
except Exception:
    print(0)")
if [ "$N" -lt 1539858 ]; then
  python3 -u opcode_scan.py > opcode_scan.log 2>&1
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
cp $CA/harness/src/*.sol $HR/src/ 2>/dev/null || true
python3 $CA/scripts/gen_probe.py          # regenerates test/ProbeBatch1.sol
cp $HR/test/ProbeBatch1.sol $CA/harness/generated/ 2>/dev/null || \
  { mkdir -p $CA/harness/generated && cp $HR/test/ProbeBatch1.sol $CA/harness/generated/; }
[ "$STOP" = "harness" ] && exit 0

# ---- stage: build (kontrol build ~4.5 min; digest skips if unchanged) ----
docker run --rm -v /tmp/harness:/work -w /work/probe $IMG kontrol build --rekompile \
  > $CA/harness/kontrol_build.log 2>&1
tail -1 $CA/harness/kontrol_build.log
[ "$STOP" = "build" ] && exit 0

# ---- stage: prove ----
docker run --rm -v /tmp/harness:/work -w /work/probe $IMG kontrol prove \
  --match-test 'ProbeBatch1.test_probe_.*' \
  --auto-abstract-gas --max-depth 1000 --smt-timeout 10000 --workers 2 \
  > $CA/harness/kontrol_prove.log 2>&1
grep -E 'PROOF (PASSED|FAILED)|Time:' $CA/harness/kontrol_prove.log || tail -5 $CA/harness/kontrol_prove.log
echo "RECOVER_DONE"
