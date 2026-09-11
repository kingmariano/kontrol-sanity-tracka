#!/usr/bin/env python3
"""Push-aware static opcode scan of all unique bytecodes -> opcode_features table.

Linear-sweep disassembly with correct PUSH-operand skipping (numpy fixpoint),
so opcode bytes inside PUSH data are NOT counted. Produces per-bytecode:
  - tracked opcode counts (caller, sstore, sload, delegatecall, callcode, call,
    selfdestruct, tload, tstore, create, create2, keccak, div, eq, mload)
  - campaign class signals (missing-auth, transient-storage, selfdestruct,
    delegate/proxy, div-heavy math)

Hard-won gotchas (do not regress):
  * bytecodes stored as "\\x<hex>" VARCHAR -> decode via SQL from_hex(substring(...,3))
  * con.append() on the main connection invalidates a streaming result set on the
    same connection -> stream reads via con.cursor(), append on main connection
  * executemany with wide rows is VERY slow (~150 rows/s) -> use columnar con.append
"""
import sys
import time
import numpy as np
import pandas as pd
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
BATCH = 20_000

PUSH_LUT = np.zeros(256, dtype=np.int64)
PUSH_LUT[0x60:0x80] = np.arange(1, 33)


def strip_metadata(code: bytes):
    """Remove the solc/vyper metadata trailer before opcode scanning.

    The trailer is `<cbor metadata><2-byte big-endian length>`. Without this,
    metadata bytes (and any PUSH in them) are decoded as code, which is what
    produced phantom `sig_transient` hits on F5-F8 (no real TLOAD/TSTORE).
    Returns (stripped_code, had_metadata).
    """
    n = len(code)
    if n < 4:
        return code, False
    length = int.from_bytes(code[-2:], "big")
    if 1 <= length <= 4096 and length + 2 <= n:
        cand = code[-(length + 2):-2]
        if (b"bzzr" in cand) or (b"ipfs" in cand) or (b"solc" in cand):
            return code[:-(length + 2)], True
    return code, False

TRACK = {
    0x33: "caller", 0x54: "sload", 0x55: "sstore",
    0xf4: "delegatecall", 0xf2: "callcode", 0xf1: "call",
    0xff: "selfdestruct", 0x5c: "tload", 0x5d: "tstore",
    0xf0: "create", 0xf5: "create2", 0x20: "keccak",
    0x04: "div", 0x14: "eq", 0x51: "mload",
}

def operand_mask(arr: np.ndarray) -> np.ndarray:
    """Positions covered as PUSH-operand data (linear-sweep fixpoint)."""
    n = len(arr)
    plen = PUSH_LUT[arr]
    covered = np.zeros(n, dtype=bool)
    for _ in range(40):
        is_push_code = (~covered) & (plen > 0)
        pos = np.flatnonzero(is_push_code)
        lens = plen[pos]
        total = int(lens.sum())
        if total == 0:
            new = np.zeros(n, dtype=bool)
        else:
            csum = np.cumsum(lens)
            starts = np.repeat(pos + 1, lens)
            offs = np.arange(total) - np.repeat(csum - lens, lens)
            tgt = starts + offs
            new = np.zeros(n, dtype=bool)
            new[tgt[tgt < n]] = True
        if np.array_equal(new, covered):
            break
        covered = new
    return covered

def analyze(code: bytes):
    code, had_md = strip_metadata(code)
    arr = np.frombuffer(code, dtype=np.uint8)
    covered = operand_mask(arr)
    ops = arr[~covered]
    cnt = np.bincount(ops, minlength=256)
    n_ops = int(ops.size)
    f = {}
    for oc, name in TRACK.items():
        f[name] = int(cnt[oc])
    f["sig_auth_sstore"] = f["caller"] > 0 and f["sstore"] > 0
    f["sig_sstore_no_caller"] = f["sstore"] > 0 and f["caller"] == 0
    f["sig_transient"] = f["tstore"] > 0 or f["tload"] > 0
    f["sig_transient_caller"] = (f["tstore"] > 0 or f["tload"] > 0) and f["caller"] > 0
    f["sig_selfdestruct"] = f["selfdestruct"] > 0
    f["sig_delegate"] = f["delegatecall"] > 0
    f["sig_proxy_like"] = f["delegatecall"] > 0 and n_ops <= 30
    f["sig_div_heavy"] = f["div"] >= 3
    f["n_ops"] = n_ops
    f["has_metadata"] = had_md
    f["code_size_eff"] = len(code)
    return f

SIGS = ["sig_auth_sstore", "sig_sstore_no_caller", "sig_transient",
        "sig_transient_caller", "sig_selfdestruct", "sig_delegate",
        "sig_proxy_like", "sig_div_heavy", "n_ops", "has_metadata",
        "code_size_eff"]

BOOL_COLS = {"has_metadata"}
BIGINT_COLS = {"n_ops"}

COLS = ([f"c_{n}" for n in TRACK.values()] + SIGS)

def create_table(con):
    con.execute("DROP TABLE IF EXISTS opcode_features")
    def sqltype(c):
        if c.startswith("sig_") or c in BOOL_COLS:
            return "BOOLEAN"
        if c in BIGINT_COLS:
            return "BIGINT"
        return "INTEGER"
    cols_sql = ", ".join(f"{c} {sqltype(c)}" for c in COLS)
    con.execute(f"CREATE TABLE opcode_features (bytecode_hash VARCHAR PRIMARY KEY, {cols_sql})")

def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    con = duckdb.connect(DB)
    con.execute("SET memory_limit='4GB'")
    con.execute("SET threads=4")
    create_table(con)
    t0 = time.time()
    done = 0
    where = "WHERE code_size_bytes > 0"
    if limit:
        where += f" LIMIT {limit}"  # sample mode
    read_con = con.cursor()
    cur = read_con.execute(f"""
        SELECT bytecode_hash, code_size_bytes,
               from_hex(substring(bytecode, 3)) AS code
        FROM bytecodes {where}
    """)
    rows = cur.fetchmany(BATCH)
    while rows:
        recs = {"bytecode_hash": []}
        for name in TRACK.values():
            recs[f"c_{name}"] = []
        for sig in SIGS:
            recs[sig] = []
        for h, size, code in rows:
            f = analyze(code)
            recs["bytecode_hash"].append(h)
            for name in TRACK.values():
                recs[f"c_{name}"].append(f[name])
            for sig in SIGS:
                recs[sig].append(f[sig])
        con.append("opcode_features", pd.DataFrame(recs))
        done += len(rows)
        rate = done / max(time.time() - t0, 1e-9)
        print(f"[{done:,}] {rate:,.0f} rows/s elapsed={time.time()-t0:.0f}s", flush=True)
        rows = cur.fetchmany(BATCH)
    con.execute("CHECKPOINT")
    print(f"DONE: {done:,} bytecodes scanned in {time.time()-t0:.0f}s", flush=True)

if __name__ == "__main__":
    main()
