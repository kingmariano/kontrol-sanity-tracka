#!/usr/bin/env python3
"""Build a compact `tracka_bytecodes.parquet` (hash -> bytecode) for the Track A
matched universe, so chunks can be generated later WITHOUT the 23 GB DuckDB.

Reads the full per-scanner parquets (written by the scanners to CA_PARQUET_DIR)
and joins them against the `bytecodes` table in the CI/HF-built DuckDB.
"""
import os
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
STAGES = os.environ.get("CA_PARQUET_DIR", "/tmp/eth-contracts/stages")
if not os.path.exists(os.path.join(STAGES, "a1_init.parquet")) \
        and os.path.exists("data/stages/a1_init.parquet"):
    STAGES = os.path.abspath("data/stages")
SCANNERS = ["a1_init", "a2_upgrade", "a5_multicall", "a6_fee",
            "a7_unchecked", "a9_unauth_pull"]


def main():
    con = duckdb.connect(DB, read_only=True)
    con.execute("SET threads=4")
    con.execute("CREATE TEMP TABLE sel(bytecode_hash VARCHAR)")
    hashes = set()
    for s in SCANNERS:
        p = os.path.join(STAGES, f"{s}.parquet")
        if not os.path.exists(p):
            print("[bytecodes] missing", p, flush=True)
            continue
        rows = con.execute(
            f"SELECT DISTINCT bytecode_hash FROM read_parquet('{p}')").fetchall()
        for (h,) in rows:
            hashes.add(h)
    print(f"[bytecodes] matched unique bytecodes: {len(hashes):,}", flush=True)
    con.executemany("INSERT INTO sel VALUES (?)", [(h,) for h in hashes])
    out = os.path.join(STAGES, "tracka_bytecodes.parquet")
    con.execute(
        "COPY (SELECT b.bytecode_hash, b.bytecode FROM bytecodes b "
        f"JOIN sel USING (bytecode_hash)) TO '{out}' "
        "(FORMAT parquet, COMPRESSION zstd)")
    print(f"[bytecodes] wrote {out} "
          f"({os.path.getsize(out)/1e6:.1f} MB)", flush=True)


if __name__ == "__main__":
    main()