#!/usr/bin/env bash
# One-time Track A dataset prepare — runs inside a Hugging Face Job.
#
#   hf jobs run --flavor cpu-xl --timeout 4h --secrets HF_TOKEN \
#     -v hf://buckets/Mariano234/kontrol-campaign:/out:rw \
#     --name tracka-prepare python:3.12 \
#     bash -lc "curl -fsSL <raw prepare.sh> -o /tmp/prepare.sh && bash /tmp/prepare.sh"
#
# Uses /tmp (ephemeral, 1000 GB on cpu-xl) for the 23 GB DuckDB + 28 GB CSVs,
# then publishes the compact reusable artifacts to the mounted bucket:
#   features_ext.parquet, the six full <scanner>.parquet target lists,
#   tracka_bytecodes.parquet (hash -> bytecode), and the target JSON samples.
# No dataset fetch is ever needed again for Track A.
set -euo pipefail

REPO="${REPO:-https://github.com/kingmariano/kontrol-sanity-tracka.git}"
TC=/tmp/eth-contracts

command -v git >/dev/null || { apt-get update -qq && apt-get install -y -qq git curl ca-certificates; }
pip install --quiet duckdb pandas pyarrow numpy pycryptodome huggingface_hub

WORK="${WORK:-/tmp/work}"
mkdir -p "$WORK"
cd "$WORK"
rm -rf repo
git clone --depth 1 "$REPO" repo
cd repo/CA

mkdir -p "$TC/stages"
base=https://huggingface.co/datasets/Zellic/all-ethereum-contracts/resolve/main
fetch() {  # url out expected_bytes
  local url="$1" out="$2" want="$3" a
  for a in 1 2 3 4 5 6; do
    curl -fL --retry 3 --retry-delay 5 --retry-all-errors -C - -o "$out" "$url" || true
    [ -f "$out" ] && [ "$(stat -c%s "$out")" = "$want" ] && return 0
    echo "[prepare] download retry $a for $out ($(stat -c%s "$out" 2>/dev/null || echo 0)/$want)"; sleep 10
  done
  return 1
}
echo "[prepare] downloading Zellic zips"
fetch "$base/contracts.zip" "$TC/contracts.zip" 2251610719
fetch "$base/bytecodes.zip" "$TC/bytecodes.zip" 4139739279
df -h "$TC" | tail -1

cp scripts/ingest.py scripts/finalize.py "$TC/"
cd "$TC"
echo "[prepare] building DuckDB (contracts + bytecodes)"
python3 -u ingest.py || echo "[prepare] ingest exited on known hash assert; finalizing"
python3 -u finalize.py
rm -f "$TC"/*.csv
ls -la "$TC/eth_contracts.duckdb"
df -h "$TC" | tail -1

cd "$WORK/repo/CA"
export CA_PARQUET_DIR="$TC/stages"
CORES="${CPU_CORES:-8}"
SHARDS=$(( CORES / 2 )); [ "$SHARDS" -lt 1 ] && SHARDS=1; [ "$SHARDS" -gt 16 ] && SHARDS=16
echo "[prepare] extended features: $SHARDS shards on $CORES cores"
for i in $(seq 0 $((SHARDS - 1))); do
  python3 -u scanners/common.py --build --shards "$SHARDS" --shard "$i" > "$TC/feat$i.log" 2>&1 &
done
wait
for f in "$TC"/feat*.log; do tail -n 1 "$f" || true; done
python3 scanners/common.py --merge "$SHARDS"

echo "[prepare] scanning Track A classes (full match)"
for s in scan_a1_init scan_a2_upgrade scan_a5_multicall scan_a6_fee scan_a7_unchecked scan_a9_unauth_pull; do
  python3 "scanners/$s.py"
done

echo "[prepare] compact matched-bytecodes parquet"
python3 hf/build_bytecodes_parquet.py

echo "[prepare] publishing to /out"
ART="$TC/stages"
[ -f "$ART/features_ext.parquet" ] || ART="$PWD/data/stages"
echo "[prepare] artifacts dir: $ART"
mkdir -p /out
cp "$ART/features_ext.parquet" /out/
for s in a1_init a2_upgrade a5_multicall a6_fee a7_unchecked a9_unauth_pull; do
  cp "$ART/$s.parquet" /out/
done
cp "$ART/tracka_bytecodes.parquet" /out/
cp data/stages/a1_init_targets.json data/stages/a2_upgrade_targets.json \
   data/stages/a5_multicall_targets.json data/stages/a6_fee_targets.json \
   data/stages/a7_unchecked_targets.json data/stages/a9_unauth_pull_targets.json /out/ 2>/dev/null || true
ls -la /out
du -sh /out
echo "[prepare] DONE"