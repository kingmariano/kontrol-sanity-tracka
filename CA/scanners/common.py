#!/usr/bin/env python3
"""Shared push-aware disassembly + feature extraction for the per-stage scanners.

Design (see CA/VULN_CLASS_RESEARCH.md §5):
  * One expensive pass over all unique bytecodes produces an extended feature
    cache (`data/stages/features_ext.parquet`).
  * Each stage owns its own scanner module (`scan_<id>.py`) with its own
    detection predicate and false-positive filters, but reuses this cache so we
    do not rescan 1.54M bytecodes nine times.
  * Every stage writes its full target list (bytecode hash + deployments +
    bounded contract-address sample) under `data/stages/`.

Hard-won gotchas (from opcode_scan.py, do not regress):
  * bytecodes are stored as "\\x<hex>" VARCHAR -> from_hex(substring(..,3))
  * metadata trailer must be stripped before scanning
  * PUSH operand bytes must never be counted as opcodes
"""
import os
import sys
import json
import numpy as np
import pandas as pd
import duckdb

try:
    from Crypto.Hash import keccak as _keccak

    def k4(sig: str) -> str:
        h = _keccak.new(digest_bits=256)
        h.update(sig.encode())
        return h.hexdigest()[:8]
except Exception:  # pragma: no cover
    raise SystemExit("pycryptodome required for selector hashing")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = "/tmp/eth-contracts/eth_contracts.duckdb"
STAGES = os.path.join(ROOT, "data", "stages")
# Big derived parquets (features_ext, per-scanner full matches) default to the
# committed data dir, but are redirected with CA_PARQUET_DIR so a one-off
# full-universe build never fills the small persistent workspace (use /tmp).
PARQ = os.environ.get("CA_PARQUET_DIR", STAGES)
FEAT = os.path.join(PARQ, "features_ext.parquet")
ADDR_CAP = 500
os.makedirs(STAGES, exist_ok=True)
os.makedirs(PARQ, exist_ok=True)

PUSH_LUT = np.zeros(256, dtype=np.int64)
PUSH_LUT[0x60:0x80] = np.arange(1, 33)

# ---------------------------------------------------------------- selector families
# Curated families; stage-2.5 (4byte.directory) will broaden these. Each family is
# a set of 8-char hex selectors, matched against the dispatcher / called selectors.
_FAMILY_SIGS = {
    "initialize": [
        "initialize()", "initialize(address)", "initialize(address,address)",
        "initialize(uint256)", "initialize(uint8,address)", "initialize(address,address,address)",
        "reinitialize()", "reinitialize(address)", "init()", "init(address)",
    ],
    "upgrade": [
        "upgradeTo(address)", "upgradeToAndCall(address,bytes)", "upgrade(address)",
        "setImplementation(address)", "changeAdmin(address)", "updateImplementation(address)",
        "setImplementationAddress(address)", "upgradeToAndCall(address,bytes,bytes)",
    ],
    "permit": [
        "permit(address,address,uint256,uint256,uint8,bytes32,bytes32)",
        "transferWithSig(address,address,uint256,bytes)",
        "execute(address,address,uint256,bytes)",
        "permit(address,address,uint256,bytes)",
    ],
    "vault": [
        "deposit(uint256,address)", "deposit(uint256)", "mint(uint256,address)",
        "withdraw(uint256,address,address)", "withdraw(uint256)", "redeem(uint256,address,address)",
        "convertToShares(uint256)", "convertToAssets(uint256)", "previewDeposit(uint256)",
        "previewMint(uint256)", "previewWithdraw(uint256)", "previewRedeem(uint256)",
        "totalAssets()", "asset()", "exchangeRate()", "getSharesByPooledEth(uint256)",
    ],
    "multicall": [
        "multicall(bytes[])", "multicall(uint256,bytes[])", "tryAggregate(bool,(address,bytes)[])",
        "batch(bytes[])", "executeBatch(bytes[])", "multicall(bytes32[])", "aggregate((address,bytes)[])",
    ],
    "hooks": [
        "onERC1155Received(address,address,uint256,uint256,bytes)",
        "onERC1155BatchReceived(address,address,uint256[],uint256[],bytes)",
        "onERC721Received(address,address,uint256,bytes)",
        "tokensReceived(address,address,address,uint256,bytes,bytes)",
        "onFlashLoan(address,address,uint256,uint256,bytes)",
        "uniswapV2Call(address,uint256,uint256,bytes)",
        "receiveFlashLoan(uint256[],uint256[],uint256[],address,bytes)",
        "executeOperation(address[],uint256[],uint256[],address,bytes)",
    ],
    "pull": [
        "transferFrom(address,address,uint256)",
        "safeTransferFrom(address,address,uint256)",
        "safeTransferFrom(address,address,uint256,bytes)",
        "safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)",
    ],
    "balanceof": ["balanceOf(address)"],
    "skim": ["skim()", "skim(address)", "sync()"],
}
FAMILIES = {k: tuple(sorted({k4(s) for s in v})) for k, v in _FAMILY_SIGS.items()}


def family(name):
    return FAMILIES[name]


def contains_any(col, sels):
    """SQL: any of `sels` (8-hex selectors) appears in feature column `col`."""
    return "(" + " OR ".join(f"contains(f.{col},'{s}')" for s in sels) + ")"


def any_family(col, name):
    return contains_any(col, family(name))


def sel_names(sel: str):
    """Reverse map for evidence/debugging (only curated sigs)."""
    out = []
    for fam, sigs in _FAMILY_SIGS.items():
        for s in sigs:
            if k4(s) == sel:
                out.append(f"{fam}:{s}")
    return out


# ---------------------------------------------------------------- disassembly
def strip_metadata(code: bytes):
    n = len(code)
    if n < 4:
        return code, False
    length = int.from_bytes(code[-2:], "big")
    if 1 <= length <= 4096 and length + 2 <= n:
        cand = code[-(length + 2):-2]
        if (b"bzzr" in cand) or (b"ipfs" in cand) or (b"solc" in cand):
            return code[:-(length + 2)], True
    return code, False


def _ops(code: bytes):
    arr = np.frombuffer(code, dtype=np.uint8)
    n = len(arr)
    plen = PUSH_LUT[arr]
    covered = np.zeros(n, dtype=bool)
    for _ in range(40):
        is_push = (~covered) & (plen > 0)
        pos = np.flatnonzero(is_push)
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
    pos = np.flatnonzero(~covered)
    return arr, pos, arr[pos]


def _shift_or(ops: np.ndarray, d: int, targets: set) -> np.ndarray:
    m = np.zeros(len(ops), dtype=bool)
    if d < len(ops):
        tail = np.isin(ops[d:], list(targets))
        m[: len(ops) - d] = tail
    return m


def _within(ops: np.ndarray, lo: int, hi: int, targets: set) -> np.ndarray:
    m = np.zeros(len(ops), dtype=bool)
    for d in range(lo, hi + 1):
        m |= _shift_or(ops, d, targets)
    return m


def extract(code: bytes) -> dict:
    code, had_md = strip_metadata(code)
    arr, pos, ops = _ops(code)
    n = len(ops)
    cn = {name: 0 for name in ("caller", "callvalue", "calldataload", "sstore", "sload",
                               "delegatecall", "callcode", "call", "staticcall",
                               "selfdestruct", "tload", "tstore", "create", "create2",
                               "keccak", "div", "mul", "eq", "mload", "returndatasize")}
    lut = {0x33: "caller", 0x34: "callvalue", 0x35: "calldataload", 0x55: "sstore",
           0x54: "sload", 0xf4: "delegatecall", 0xf2: "callcode", 0xf1: "call",
           0xfa: "staticcall", 0xff: "selfdestruct", 0x5c: "tload", 0x5d: "tstore",
           0xf0: "create", 0xf5: "create2", 0x20: "keccak", 0x04: "div", 0x02: "mul",
           0x14: "eq", 0x51: "mload", 0x3d: "returndatasize"}
    if n:
        bc = np.bincount(ops, minlength=256)
        for oc, name in lut.items():
            cn[name] = int(bc[oc])

    # dispatcher selectors: PUSH4 ; EQ within +1..+2 ; JUMPI within +2..+5
    is63 = ops == 0x63
    disp_mask = is63 & _within(ops, 1, 2, {0x14}) & _within(ops, 2, 5, {0x57})
    # called selectors: PUSH4 ; MSTORE within +1..+8 ; external CALL within +1..+40
    # (window widened for modern solc `PUSH4 sel; PUSH1 0xe0; SHL; ...; MSTORE` encoding)
    called_mask = is63 & _within(ops, 1, 8, {0x52}) & _within(ops, 1, 40, {0xf1, 0xfa, 0xf4})
    disp_sels, called_sels = [], []
    for mask, sink in ((disp_mask, disp_sels), (called_mask, called_sels)):
        for si in np.flatnonzero(mask):
            bp = int(pos[si])
            if bp + 5 <= len(arr):
                sink.append(bytes(arr[bp + 1:bp + 5]).hex())
    disp_sels = sorted(set(disp_sels))
    called_sels = sorted(set(called_sels))

    caller_eq = bool(np.any((ops == 0x33) & _within(ops, 1, 3, {0x14})))
    # precompile-1 (ecrecover) heuristic: a PUSH1 with operand 0x01 exists AND the
    # contract makes a CALL/STATICCALL. Low precision by design; the proof is the filter.
    has_p1 = False
    p1 = np.flatnonzero(ops == 0x60)
    if len(p1):
        vals = arr[np.minimum(pos[p1] + 1, len(arr) - 1)]
        has_p1 = bool(np.any(vals == 1))
    ecrecover = has_p1 and (cn["call"] + cn["staticcall"] > 0)
    returndata_checked = cn["returndatasize"] > 0

    return {
        "bytecode_hash": None,
        "n_ops": n,
        "code_size_eff": len(code),
        "has_metadata": had_md,
        "disp_sel": " ".join(disp_sels),
        "called_sel": " ".join(called_sels),
        **{f"c_{k}": v for k, v in cn.items()},
        "caller_eq": caller_eq,
        "ecrecover_call": ecrecover,
        "returndata_checked": returndata_checked,
    }


FEAT_COLS = ["bytecode_hash", "n_ops", "code_size_eff", "has_metadata", "disp_sel",
             "called_sel"] + [f"c_{k}" for k in ("caller", "callvalue", "calldataload",
             "sstore", "sload", "delegatecall", "callcode", "call", "staticcall",
             "selfdestruct", "tload", "tstore", "create", "create2", "keccak", "div",
             "mul", "eq", "mload", "returndatasize")] + ["caller_eq", "ecrecover_call",
             "returndata_checked"]


# ---------------------------------------------------------------- feature build
def build_features(limit=0, batch=20000, shard=0, shards=1):
    con = duckdb.connect(DB, read_only=True)
    con.execute("SET memory_limit='3GB'")
    con.execute("SET threads=2")
    rcon = con.cursor()
    wheres = ["code_size_bytes > 0"]
    if shards > 1:
        wheres.append(f"hash(bytecode_hash) % {shards} = {shard}")
    where = "WHERE " + " AND ".join(wheres)
    if limit:
        where += f" LIMIT {limit}"
    out = FEAT if shards == 1 else FEAT.replace(".parquet", f".part{shard}.parquet")
    cur = rcon.execute(f"""
        SELECT bytecode_hash, from_hex(substring(bytecode, 3)) AS code
        FROM bytecodes {where}
    """)
    import pyarrow as pa
    import pyarrow.parquet as pq
    writer = None
    tot = 0
    rows = cur.fetchmany(batch)
    while rows:
        recs = {c: [] for c in FEAT_COLS}
        for h, code in rows:
            f = extract(code)
            f["bytecode_hash"] = h
            for c in FEAT_COLS:
                recs[c].append(f[c])
        tbl = pa.table({c: pa.array(recs[c]) for c in FEAT_COLS})
        if writer is None:
            writer = pq.ParquetWriter(out, tbl.schema, compression="zstd")
        writer.write_table(tbl)
        tot += len(rows)
        print(f"[build s{shard}] {tot:,} bytecodes", flush=True)
        rows = cur.fetchmany(batch)
    if writer:
        writer.close()
    print(f"[build s{shard}] wrote {out} rows={tot:,}", flush=True)


def merge_shards(shards):
    import pyarrow.parquet as pq
    import pyarrow as pa
    tbls = [pq.read_table(FEAT.replace(".parquet", f".part{i}.parquet")) for i in range(shards)]
    tbl = pa.concat_tables(tbls)
    pq.write_table(tbl, FEAT, compression="zstd")
    for i in range(shards):
        os.remove(FEAT.replace(".parquet", f".part{i}.parquet"))
    print(f"[merge] {FEAT} rows={tbl.num_rows:,}")


def ensure_features():
    if not os.path.exists(FEAT):
        raise SystemExit(f"missing {FEAT}; run: python3 scanners/common.py --build")
    return pd.read_parquet(FEAT)


# ---------------------------------------------------------------- stage output
def _dep_table(con):
    return ("(SELECT bytecode_hash, count(*) AS deploys FROM contracts "
            "GROUP BY bytecode_hash)")


def run_stage(stage_id, predicate, limit=200, note=""):
    """predicate: SQL over table alias `f` (features) e.g.
       "f.c_sstore>0 AND contains(f.disp_sel,'8129fc1c')".

    Writes:
      data/stages/<id>.parquet        -- the FULL match (the authoritative source
                                         the CI generator consumes; no contract is
                                         left out)
      data/stages/<id>_targets.json   -- a bounded, deployment-ranked SAMPLE (the
                                         `limit` top targets) with address samples,
                                         for offline triage only

    The full parquet is the ground truth for the sweep; the JSON sample must never
    be treated as the target universe.
    """
    con = duckdb.connect(DB, read_only=True)
    con.execute("SET memory_limit='6GB'")
    con.execute("SET threads=4")
    q = f"""
        SELECT f.*, coalesce(d.deploys,0) AS deploys
        FROM read_parquet('{FEAT}') f
        LEFT JOIN {_dep_table(con)} d USING (bytecode_hash)
        WHERE {predicate}
    """
    df = con.execute(q).fetchdf()
    out = os.path.join(PARQ, f"{stage_id}.parquet")
    df.to_parquet(out, index=False)
    # top-N targets by deployments, with a bounded address sample each
    top = df.sort_values("deploys", ascending=False).head(limit)
    targets = []
    for _, r in top.iterrows():
        addrs = [a for (a,) in con.execute(
            "SELECT address FROM contracts WHERE bytecode_hash=? ORDER BY blocknum DESC LIMIT ?",
            [r["bytecode_hash"], ADDR_CAP]).fetchall()]
        targets.append({"hash": r["bytecode_hash"], "deploys": int(r["deploys"]),
                        "n_ops": int(r["n_ops"]), "code_size_eff": int(r["code_size_eff"]),
                        "disp_sel": r["disp_sel"], "called_sel": r["called_sel"],
                        "addresses": addrs})
    man = {"stage": stage_id, "note": note,
           "matched_bytecodes": int(len(df)),
           "matched_deployments": int(df["deploys"].sum()),
           "json_sample_limit": int(limit),
           "targets": targets}
    with open(os.path.join(STAGES, f"{stage_id}_targets.json"), "w") as f:
        json.dump(man, f, indent=1)
    print(f"[{stage_id}] matched bytecodes={len(df):,} "
          f"deployments={int(df['deploys'].sum()):,} -> {out}")
    print(f"[{stage_id}] top target: deploys={targets[0]['deploys']:,}" if targets else
          f"[{stage_id}] no targets")
    return man


if __name__ == "__main__":
    def arg(flag, default=None):
        return sys.argv[sys.argv.index(flag) + 1] if flag in sys.argv else default
    if "--build" in sys.argv:
        build_features(limit=int(arg("--limit", 0)),
                       shard=int(arg("--shard", 0)),
                       shards=int(arg("--shards", 1)))
    elif "--merge" in sys.argv:
        merge_shards(int(arg("--merge", 1)))
    else:
        print("usage: python3 scanners/common.py --build [--limit N] [--shard i --shards N] | --merge N")
