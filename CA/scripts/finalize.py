#!/usr/bin/env python3
"""Final normalization + smoke tests."""
import duckdb

con = duckdb.connect("/tmp/eth-contracts/eth_contracts.duckdb")
con.execute("SET memory_limit='4GB'")

print("contract rows with NULL bytecode_hash:",
      con.execute("SELECT count(*) FROM contracts WHERE bytecode_hash IS NULL").fetchone(),
      flush=True)
print("example:", con.execute(
    "SELECT address, blocknum FROM contracts WHERE bytecode_hash IS NULL LIMIT 3"
).fetchall(), flush=True)

con.execute("UPDATE bytecodes SET bytecode = '', code_size_bytes = 0 WHERE bytecode IS NULL")
con.execute(
    "CREATE OR REPLACE VIEW all_contracts AS "
    "SELECT c.address, c.bytecode_hash, c.blocknum, b.code_size_bytes "
    "FROM contracts c JOIN bytecodes b USING (bytecode_hash)"
)

print("\nSmoke tests:", flush=True)
print(" total contracts:", con.execute("SELECT count(*) FROM all_contracts").fetchone()[0], flush=True)
print(" sample row:", con.execute("SELECT * FROM all_contracts LIMIT 1").fetchone(), flush=True)
print(" avg code size (non-empty):", con.execute(
    "SELECT round(avg(code_size_bytes),1) FROM bytecodes WHERE code_size_bytes>0"
).fetchone(), flush=True)

con.execute("CHECKPOINT")
con.close()
print("DONE", flush=True)
