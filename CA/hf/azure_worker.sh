#!/usr/bin/env bash
# azure_worker.sh — one Azure VM's share of a Track A wave.
#
# Required env: HF_TOKEN, VM_INDEX, VM_COUNT
# Optional:     WAVE (default wave1), BUDGET_SECS (per test, default 600),
#               PROVE_OPTS, NO_SHUTDOWN=1 (skip deallocate; for the pilot)
#
# Deterministic static partition: assignment i goes to VM (i % VM_COUNT).
# Each VM: install docker -> fetch wave tarball from the HF bucket -> clone the
# repo -> per stage: copy its chunks, `kontrol build` once inside the pinned
# Kontrol image, then a per-test `kontrol prove` loop writing explicit verdicts
# (incl. the failing property) -> tar + upload verdicts to the bucket.
set -euo pipefail
: "${HF_TOKEN:?set HF_TOKEN}"
: "${VM_INDEX:?set VM_INDEX}"
: "${VM_COUNT:?set VM_COUNT}"
WAVE="${WAVE:-wave1}"
BUDGET_SECS="${BUDGET_SECS:-1800}"
IMG=runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255
BUCKET=hf://buckets/Mariano234/kontrol-campaign
REPO=https://github.com/kingmariano/kontrol-sanity-tracka.git
WORK=/opt/kontrol

export DEBIAN_FRONTEND=noninteractive
mkdir -p "$WORK" && cd "$WORK"
for pkg in docker.io git curl python3-pip; do command -v "${pkg%%-*}" >/dev/null 2>&1 || true; done
apt-get -o DPkg::Lock::Timeout=600 update -qq >/dev/null 2>&1 || true
apt-get -o DPkg::Lock::Timeout=600 install -y -qq docker.io git curl python3-pip >/dev/null 2>&1 || true
systemctl start docker 2>/dev/null || service docker start 2>/dev/null || true
pip3 install --quiet "huggingface_hub[cli]"

echo "[vm$VM_INDEX] pulling kontrol image"
docker pull -q "$IMG"

echo "[vm$VM_INDEX] fetching $WAVE"
rm -rf wave && mkdir -p wave
hf cp "$BUCKET/${WAVE}.tgz" "$WORK/${WAVE}.tgz" >/dev/null
tar -xzf "$WORK/${WAVE}.tgz" -C wave

rm -rf repo && git clone --depth 1 "$REPO" repo

OUT="$WORK/out"; mkdir -p "$OUT"
: > "$OUT/verdicts.txt"
# resume: skip chunks this VM already uploaded (per-chunk markers in the bucket)
DONE_LIST="$WORK/done_chunks.txt"; : > "$DONE_LIST"
hf buckets list Mariano234/kontrol-campaign -R 2>/dev/null \
  | grep -oE "verdicts_vm${VM_INDEX}_[a-z0-9_]+\.txt" | sort -u > "$DONE_LIST" || true
echo "[vm$VM_INDEX] resume markers: $(wc -l < "$DONE_LIST")"
i=0
while read -r stage chunk; do
  [ -z "${stage:-}" ] && continue
  if [ $((i % VM_COUNT)) -ne "$VM_INDEX" ]; then i=$((i+1)); continue; fi
  i=$((i+1))
  MARK="verdicts_vm${VM_INDEX}_${stage}_${chunk}.txt"
  if grep -qx "$MARK" "$DONE_LIST"; then echo "[vm$VM_INDEX] skip $stage c$chunk (already done)"; continue; fi
  echo "[vm$VM_INDEX] assigned $stage c$chunk"
  echo "$stage $chunk" >> "$OUT/assigned.txt"

  PROBE="$WORK/repo/probe"
  rm -rf "$PROBE"; cp -r "$WORK/repo/CA/harness/skeleton" "$PROBE"
  mkdir -p "$PROBE/test"
  cp "$WORK/wave/stage${stage}/Stage${stage}Chunk_${chunk}.sol" "$PROBE/test/"
  TESTS="$WORK/wave/stage${stage}/chunk_${chunk}.tests"

  cat > "$PROBE/run_chunk.sh" <<'INNER'
set -u
OPTS="${PROVE_OPTS:---use-booster --no-break-on-calls --no-stack-checks --no-log-rewrites --max-frontier-parallel 2 --max-depth 50000 --max-iterations 100000 --smt-timeout 30000 --smt-retry-limit 2 --workers 3 --step-timeout 600 --auto-abstract-gas}"
echo "[inner] kontrol build"
kontrol build 2>&1 | tail -2 || true
V=/work/verdicts_chunk.txt; : > "$V"
while IFS= read -r t; do
  [ -z "$t" ] && continue
  SECONDS=0
  echo "=== $t ===" >> "$V"
  timeout -k 30s "${BUDGET_SECS:-600}s" kontrol prove --match-test "$t" $OPTS > /work/one.log 2>&1 || true
  if grep -qE 'PROOF (PASSED|FAILED)' /work/one.log; then
    verdict=$(grep -E 'PROOF (PASSED|FAILED)' /work/one.log | head -1)
    prop=$(grep -oE 'P_[A-Z_]+' /work/one.log | sort -u | head -3 | tr '\n' ',')
    echo "=== $t $verdict (prop: $prop) [${SECONDS}s] ===" >> "$V"
  elif grep -qE 'Test identifiers not found' /work/one.log; then
    echo "=== $t BROKEN (test name absent) ===" >> "$V"
  elif grep -qE 'Traceback|FileNotFoundError|No such file' /work/one.log; then
    echo "=== $t ERROR (harness/setup) [${SECONDS}s] ===" >> "$V"
  else
    echo "=== $t INCOMPLETE [${SECONDS}s] ===" >> "$V"
  fi
done < /work/tests.txt
INNER

  chmod -R a+rwX "$PROBE"
  cp "$TESTS" "$PROBE/tests.txt"

  echo "[vm$VM_INDEX] kontrol build ($stage c$chunk)"
  docker run --rm -v "$PROBE":/work -w /work \
    -e BUDGET_SECS="$BUDGET_SECS" -e PROVE_OPTS="${PROVE_OPTS:-}" \
    "$IMG" bash /work/run_chunk.sh
  echo "----- $stage c$chunk -----" >> "$OUT/verdicts.txt"
  cat "$PROBE/verdicts_chunk.txt" >> "$OUT/verdicts.txt" 2>/dev/null || true
  # Per-chunk upload. Only mark the chunk DONE when no test is INCOMPLETE, so
  # unfinished chunks are retried with a larger budget instead of silently lost.
  cp "$PROBE/verdicts_chunk.txt" "$OUT/v_${stage}_${chunk}.txt" 2>/dev/null || true
  if grep -q "INCOMPLETE" "$PROBE/verdicts_chunk.txt" 2>/dev/null; then
    hf cp "$OUT/v_${stage}_${chunk}.txt" "$BUCKET/verdicts_vm${VM_INDEX}_${stage}_${chunk}.partial.txt" >/dev/null 2>&1 || true
    echo "[vm$VM_INDEX] $stage c$chunk has INCOMPLETE tests -> will retry"
  else
    hf cp "$OUT/v_${stage}_${chunk}.txt" "$BUCKET/${MARK}" >/dev/null 2>&1 || true
    echo "$MARK" >> "$DONE_LIST"
  fi
  # rolling full-verdict snapshot
  tar -czf "$WORK/verdicts_vm${VM_INDEX}.tgz" -C "$OUT" verdicts.txt assigned.txt 2>/dev/null || true
  hf cp "$WORK/verdicts_vm${VM_INDEX}.tgz" "$BUCKET/verdicts_vm${VM_INDEX}.tgz" >/dev/null 2>&1 || true
done < "$WORK/wave/assignments.txt"

BASE="verdicts_vm${VM_INDEX}"
tar -czf "$WORK/${BASE}.tgz" -C "$OUT" verdicts.txt assigned.txt 2>/dev/null || true
echo "[vm$VM_INDEX] uploading verdicts"
hf cp "$WORK/${BASE}.tgz" "$BUCKET/${BASE}.tgz" >/dev/null 2>&1 || true
date -u > "$WORK/done.txt"
hf cp "$WORK/done.txt" "$BUCKET/${BASE}.done" >/dev/null 2>&1 || true
echo "[vm$VM_INDEX] DONE"
if [ "${NO_SHUTDOWN:-}" != "1" ]; then
  shutdown -h +1 "kontrol worker done" || true
fi
