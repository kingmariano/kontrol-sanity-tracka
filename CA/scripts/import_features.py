#!/usr/bin/env python3
"""Import opcode_features from the persistent parquet into the (rebuilt) DuckDB.
30-second replacement for the 31-minute rescan after a Codespace recycle."""
import os
import sys
import time
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PQ = os.path.join(ROOT, "data", "opcode_features.parquet")

con = duckdb.connect(DB)
con.execute("SET memory_limit='4GB'")
con.execute("DROP TABLE IF EXISTS opcode_features")
con.execute(f"CREATE TABLE opcode_features AS SELECT * FROM read_parquet('{PQ}')")
(n,) = con.execute("SELECT count(*) FROM opcode_features").fetchone()
con.close()
print(f"imported {n:,} opcode_features rows in {time.time()-t0 if 't0' in dir() else 0:.0f}s")
assert n == 1539858, f"expected 1,539,858 rows, got {n}"
print("IMPORT_OK")
