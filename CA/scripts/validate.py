#!/usr/bin/env python3
"""Post-ingest validation + analysis artifacts. Run detached: python3 -u validate.py > validate.log"""
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
EMPTY = "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"

con = duckdb.connect(DB)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=4")
print("connected", flush=True)

orphan = con.execute(
    "SELECT count(*) FROM (SELECT DISTINCT bytecode_hash FROM contracts "
    "EXCEPT SELECT bytecode_hash FROM bytecodes)"
).fetchone()[0]
print(f"orphan hashes: {orphan:,}  (must be 0)", flush=True)

empty_entries = con.execute(
    "SELECT count(*) FROM bytecodes WHERE bytecode = '' OR bytecode IS NULL"
).fetchone()[0]
empty_contracts = con.execute(
    f"SELECT count(*) FROM contracts WHERE bytecode_hash='{EMPTY}'"
).fetchone()[0]
mn, mx = con.execute("SELECT min(blocknum), max(blocknum) FROM contracts").fetchone()
print(f"empty bytecode entries: {empty_entries:,}", flush=True)
print(f"contracts with empty code: {empty_contracts:,} ({empty_contracts/69788231*100:.1f}%)", flush=True)
print(f"blocknum range: {mn:,} .. {mx:,}", flush=True)

con.execute(
    "CREATE OR REPLACE VIEW all_contracts AS "
    "SELECT c.address, c.bytecode_hash, c.blocknum, b.code_size_bytes "
    "FROM contracts c JOIN bytecodes b USING (bytecode_hash)"
)
print("view all_contracts created", flush=True)

print("\nTop 10 most-redeployed bytecodes (standard templates):", flush=True)
for h, n, sz in con.execute(
    "SELECT b.bytecode_hash, count(*) n, any_value(b.code_size_bytes) sz "
    "FROM contracts c JOIN bytecodes b USING(bytecode_hash) "
    "GROUP BY 1 ORDER BY n DESC LIMIT 10"
).fetchall():
    print(f"  {h}  {n:>12,} deployments  {sz:>7} bytes", flush=True)

print("\nUnique bytecode code-size distribution:", flush=True)
rows = con.execute(
    "SELECT CASE WHEN code_size_bytes=0 THEN '0 (empty)' "
    "WHEN code_size_bytes<=32 THEN '1-32 B' "
    "WHEN code_size_bytes<=256 THEN '33-256 B' "
    "WHEN code_size_bytes<=2048 THEN '257 B-2 KB' "
    "WHEN code_size_bytes<=8192 THEN '2-8 KB' "
    "WHEN code_size_bytes<=16384 THEN '8-16 KB' "
    "ELSE '>16 KB' END bucket, count(*) n "
    "FROM bytecodes GROUP BY 1 ORDER BY min(code_size_bytes)"
).fetchall()
for b, n in rows:
    print(f"  {b:<12} {n:>10,}", flush=True)

con.execute("CHECKPOINT")
con.close()
print("DONE", flush=True)
