#!/usr/bin/env python3
"""Follow-up: investigate orphan/empty entries, finish template + size analysis."""
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
con = duckdb.connect(DB)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=4")

print("The single orphan contract (hash not present in bytecodes table):", flush=True)
for row in con.execute(
    "SELECT c.address, c.bytecode_hash, c.blocknum FROM contracts c "
    "WHERE bytecode_hash NOT IN (SELECT bytecode_hash FROM bytecodes)"
).fetchall():
    print(f"  {row}", flush=True)

print("\nRows with NULL bytecode in bytecodes table:", flush=True)
for row in con.execute(
    "SELECT bytecode_hash, code_size_bytes FROM bytecodes "
    "WHERE bytecode IS NULL"
).fetchall():
    print(f"  {row}", flush=True)

print("\nTop 10 most-redeployed bytecodes (standard templates):", flush=True)
for h, n, sz in con.execute(
    "SELECT b.bytecode_hash, count(*) n, coalesce(any_value(b.code_size_bytes), -1) sz "
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

print("\nLargest 5 unique bytecodes:", flush=True)
for h, sz in con.execute(
    "SELECT bytecode_hash, code_size_bytes FROM bytecodes "
    "ORDER BY code_size_bytes DESC LIMIT 5"
).fetchall():
    print(f"  {h}  {sz:,} bytes", flush=True)

con.close()
print("DONE", flush=True)
