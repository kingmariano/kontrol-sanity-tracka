#!/usr/bin/env python3
"""
Ingest Zellic's all-ethereum-contracts dataset into DuckDB.

Inputs (in /tmp/eth-contracts):
  contracts.zip  -> contracts.csv   (address, bytecode_hash, blocknum)  ~69.8M rows
  bytecodes.zip  -> bytecodes.csv   (bytecode_hash, bytecode)           ~1.54M rows

Outputs:
  /tmp/eth-contracts/eth_contracts.duckdb with tables `contracts` and `bytecodes`,
  plus a pre-joined convenience view and sanity-check report.
"""
import os
import sys
import zipfile
import duckdb

BASE = "/tmp/eth-contracts"
DB_PATH = os.path.join(BASE, "eth_contracts.duckdb")

EXPECTED_CONTRACT_ROWS = 69_788_231
EXPECTED_UNIQUE_BYTECODES = 1_539_859

EMPTY_HASH = "0xc5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"  # keccak256("")


def unzip(name: str) -> str:
    """Extract a dataset zip and return the path of the CSV inside."""
    zpath = os.path.join(BASE, name)
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        print(f"[unzip] {name}: {names}")
        csv_members = [n for n in names if n.endswith(".csv")]
        assert len(csv_members) == 1, f"expected exactly one CSV in {name}, got {names}"
        out = z.extract(csv_members[0], path=BASE)
        print(f"[unzip] extracted -> {out} ({os.path.getsize(out):,} bytes)")
        return out


def main() -> None:
    contracts_csv = unzip("contracts.zip")
    bytecodes_csv = unzip("bytecodes.zip")

    # Remove any stale DB from a previous attempt
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    con = duckdb.connect(DB_PATH)

    # ---------- Load bytecodes ----------
    # bytecode column is hex text, sometimes prefixed with \x, sometimes empty.
    print("[load] bytecodes ...")
    con.execute(f"""
        CREATE TABLE bytecodes AS
        SELECT
            lower(bytecode_hash)                       AS bytecode_hash,
            bytecode                                   AS bytecode,
            length(bytecode) / 2                       AS code_size_bytes
        FROM read_csv('{bytecodes_csv}',
            header = true,
            columns = {{'bytecode_hash': 'VARCHAR', 'bytecode': 'VARCHAR'}},
            quote = '"',
            escape = '"')
    """)

    # ---------- Load contracts ----------
    print("[load] contracts ...")
    con.execute(f"""
        CREATE TABLE contracts AS
        SELECT
            lower(address)                             AS address,
            lower(bytecode_hash)                       AS bytecode_hash,
            CAST(blocknum AS BIGINT)                   AS blocknum
        FROM read_csv('{contracts_csv}',
            header = true,
            columns = {{'address': 'VARCHAR', 'bytecode_hash': 'VARCHAR', 'blocknum': 'BIGINT'}})
    """)

    # ---------- Validation ----------
    print("[validate] running sanity checks ...")
    (n_contracts,) = con.execute("SELECT count(*) FROM contracts").fetchone()
    (n_bytecodes,) = con.execute("SELECT count(*) FROM bytecodes").fetchone()
    (n_distinct_hash,) = con.execute(
        "SELECT count(DISTINCT bytecode_hash) FROM bytecodes"
    ).fetchone()
    (orphan,) = con.execute("""
        SELECT count(*) FROM (
            SELECT DISTINCT bytecode_hash FROM contracts
            EXCEPT
            SELECT bytecode_hash FROM bytecodes
        )
    """).fetchone()
    (empty_bytecode,) = con.execute(
        "SELECT count(*) FROM bytecodes WHERE bytecode = '' OR bytecode IS NULL"
    ).fetchone()
    (min_block, max_block) = con.execute(
        "SELECT min(blocknum), max(blocknum) FROM contracts"
    ).fetchone()
    (n_empty_hash_contracts,) = con.execute(
        f"SELECT count(*) FROM contracts WHERE bytecode_hash = '{EMPTY_HASH}'"
    ).fetchone()

    print(f"""
================ VALIDATION REPORT ================
contracts rows:            {n_contracts:,}   (expected ~{EXPECTED_CONTRACT_ROWS:,})
bytecodes rows:            {n_bytecodes:,}   (expected ~{EXPECTED_UNIQUE_BYTECODES:,})
distinct bytecode hashes:  {n_distinct_hash:,}   (must equal bytecodes rows)
orphan contract hashes:    {orphan:,}   (must be 0)
empty bytecode entries:    {empty_bytecode:,}
contracts w/ empty code:   {n_empty_hash_contracts:,}
blocknum range:            {min_block:,} .. {max_block:,}
====================================================
""")

    assert n_distinct_hash == n_bytecodes, "bytecode_hash is not unique in bytecodes table"
    assert orphan == 0, f"{orphan} contract bytecode_hashes missing from bytecodes table"

    # ---------- Convenience artifacts for the audit campaign ----------
    print("[finalize] creating analysis view + stats ...")
    con.execute("""
        CREATE VIEW all_contracts AS
        SELECT c.address, c.bytecode_hash, c.blocknum, b.code_size_bytes
        FROM contracts c
        JOIN bytecodes b USING (bytecode_hash)
    """)
    # Most-deployed bytecodes = standard templates (proxies, tokens, etc.)
    top_templates = con.execute("""
        SELECT bytecode_hash, count(*) AS n
        FROM contracts GROUP BY 1 ORDER BY n DESC LIMIT 10
    """).fetchall()
    print("Top 10 most-redeployed bytecodes:")
    for h, n in top_templates:
        print(f"  {h}  {n:,} deployments")

    # Persist sorted/optimized copies? Not needed — DuckDB zonemaps handle
    # equality filters well on native tables. Checkpoint and report sizes.
    con.execute("CHECKPOINT")
    con.close()

    for f in ("eth_contracts.duckdb",):
        p = os.path.join(BASE, f)
        print(f"[done] {p}: {os.path.getsize(p):,} bytes")


if __name__ == "__main__":
    sys.exit(main())
