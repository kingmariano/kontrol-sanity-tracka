#!/usr/bin/env bash
# Prove ONE Track A chunk inside a Hugging Face Job (runs the Kontrol image).
#
#   hf jobs run --flavor cpu-upgrade --timeout 2h --secrets HF_TOKEN \
#     -v hf://buckets/Mariano234/kontrol-campaign:/out:rw \
#     -e STAGE=tracka_a7pilot -e CHUNK=1 \
#     runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255 bash /out/prove_shard.sh
#
# Clones the repo, materializes the probe + chunk, `kontrol build` once, then a
# per-test `kontrol prove` loop (1.0.255 has no --match-contract) with an explicit
# verdict line per test. Verdicts are also copied to the mounted bucket (/out).
set -euo pipefail
STAGE="${STAGE:?set STAGE}"
CHUNK="${CHUNK:?set CHUNK}"
WORK="${WORK:-/tmp/work}"
REPO="${REPO:-https://github.com/kingmariano/kontrol-sanity-tracka.git}"

command -v git >/dev/null 2>&1 || {
  apt-get update -qq && apt-get install -y -qq git ca-certificates >/dev/null
}
mkdir -p "$WORK"; cd "$WORK"; rm -rf repo
git clone --depth 1 "$REPO" repo
cd repo

cp -r CA/harness/skeleton probe
mkdir -p probe/test
cp "CA/harness/stages/stage${STAGE}/Stage${STAGE}Chunk_${CHUNK}.sol" probe/test/
TESTS="$WORK/repo/CA/harness/stages/stage${STAGE}/chunk_${CHUNK}.tests"

cd probe
chmod -R a+rwX .
echo "[prove] cores=$(nproc) mem=$(free -g | awk '/Mem:/{print $2}')GB stage=$STAGE chunk=$CHUNK"
echo "[prove] kontrol build"
kontrol build 2>&1 | tail -3
chmod -R a+rwX .

V="$WORK/verdicts_${STAGE}_${CHUNK}.txt"; : > "$V"
PROVE_OPTS="${PROVE_OPTS:---use-booster --no-break-on-calls --no-stack-checks --no-log-rewrites --max-frontier-parallel 2 --max-depth 50000 --max-iterations 100000 --smt-timeout 30000 --smt-retry-limit 2 --workers 3 --step-timeout 600 --auto-abstract-gas}"
while IFS= read -r t; do
  [ -z "$t" ] && continue
  SECONDS=0
  echo "=== $t ===" | tee -a "$V"
  timeout -k 30s "${BUDGET_SECS:-1500}s" kontrol prove --match-test "$t" $PROVE_OPTS \
      > "$WORK/one.log" 2>&1 || true
  if grep -qE 'PROOF (PASSED|FAILED)' "$WORK/one.log"; then
    verdict=$(grep -E 'PROOF (PASSED|FAILED)' "$WORK/one.log" | head -1)
    prop=$(grep -oE 'P_[A-Z_]+' "$WORK/one.log" | sort -u | head -3 | tr '\n' ',')
    echo "=== $t $verdict (prop: $prop) ===" >> "$V"
  elif grep -qE 'Test identifiers not found' "$WORK/one.log"; then
    echo "=== $t BROKEN (test name absent from project) ===" >> "$V"
  else
    echo "=== $t INCOMPLETE (rc; see log) ===" >> "$V"
  fi
  echo "[prove] $t took ${SECONDS}s" | tee -a "$V"
done < "$TESTS"

echo "----- verdicts -----"; cat "$V"
mkdir -p /out/verdicts 2>/dev/null || true
cp "$V" /out/verdicts/ 2>/dev/null || true
tail -40 "$WORK/one.log" > /tmp/last_prove.log 2>/dev/null || true
echo "[prove] DONE"
