#!/usr/bin/env python3
"""Export deployment addresses for every matched Track A target from the DuckDB.

Output: parquet (bytecode_hash, address, blocknum) capped at ADDR_CAP per target
(most-recent deployments first). Used by the sharded funds scan.
"""
import os
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
STAGES = os.environ.get("STAGES", "/tmp/eth-contracts/stages")
CAP = int(os.environ.get("ADDR_CAP", "50"))
OUT = os.environ.get("OUT", "/tmp/tracka_addresses.parquet")
SCANNERS = ["a1_init", "a2_upgrade", "a5_multicall", "a6_fee", "a7_unchecked",
            "a9_unauth_pull"]


def main():
    con = duckdb.connect(DB, read_only=True)
    con.execute("SET threads=4")
    con.execute("CREATE TEMP TABLE sel(bytecode_hash VARCHAR)")
    hashes = set()
    for s in SCANNERS:
        p = os.path.join(STAGES, f"{s}.parquet")
        if not os.path.exists(p):
            print("[addr] missing", p, flush=True)
            continue
        for (h,) in con.execute(
                f"SELECT DISTINCT bytecode_hash FROM read_parquet('{p}')").fetchall():
            hashes.add(h)
    print(f"[addr] matched targets: {len(hashes):,}", flush=True)
    con.executemany("INSERT INTO sel VALUES (?)", [(h,) for h in hashes])
    con.execute(f"""
        COPY (
          SELECT bytecode_hash, address, blocknum FROM (
            SELECT c.bytecode_hash, c.address, c.blocknum,
                   row_number() OVER (PARTITION BY c.bytecode_hash
                                      ORDER BY c.blocknum DESC) AS rn
            FROM contracts c JOIN sel USING (bytecode_hash)
            WHERE c.bytecode_hash IS NOT NULL AND c.address IS NOT NULL
          ) WHERE rn <= {CAP}
        ) TO '{OUT}' (FORMAT parquet, COMPRESSION zstd)
    """)
    n = con.execute(f"SELECT count(*) FROM read_parquet('{OUT}')").fetchone()[0]
    print(f"[addr] wrote {OUT}: {n:,} addresses (cap {CAP}/target)", flush=True)


if __name__ == "__main__":
    main()
