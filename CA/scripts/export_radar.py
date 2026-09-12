#!/usr/bin/env python3
"""Export opcode_features to persistent workspace (Parquet) + radar summary.

Run AFTER opcode_scan.py completes. Outputs:
  /workspaces/codespaces-blank/CA/data/opcode_features.parquet   (persistent)
  /workspaces/codespaces-blank/CA/data/RADAR.md                  (signal summary)
"""
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
OUT_DIR = "/workspaces/codespaces-blank/CA/data"

con = duckdb.connect(DB, read_only=True)
con.execute("SET memory_limit='6GB'")
con.execute("SET threads=4")

total = con.execute("SELECT count(*) FROM opcode_features").fetchone()[0]
print(f"scanned unique bytecodes: {total:,}", flush=True)

import os
os.makedirs(OUT_DIR, exist_ok=True)
con.execute(f"""
    COPY (SELECT * FROM opcode_features)
    TO '{OUT_DIR}/opcode_features.parquet' (FORMAT parquet, COMPRESSION zstd)
""")
size = os.path.getsize(f"{OUT_DIR}/opcode_features.parquet")
print(f"exported opcode_features.parquet ({size:,} bytes)", flush=True)

sigs = ["sig_sstore_no_caller", "sig_transient", "sig_transient_caller",
        "sig_selfdestruct", "sig_delegate", "sig_proxy_like", "sig_div_heavy"]

lines = []
lines.append("# Opcode Radar — static scan of unique Ethereum bytecodes\n")
lines.append(f"- Unique bytecodes scanned: **{total:,}**")
lines.append("- Source: Zellic/all-ethereum-contracts snapshot, block 21,850,000 (Feb 15, 2025)")
lines.append("- Method: push-aware linear-sweep disassembly, **solc/vyper metadata"
             " trailer stripped** before scanning (PUSH operand data excluded)\n")
lines.append("## Signal prevalence (unique bytecodes)\n")
lines.append("| Signal | Bytecodes | % | Mainnet deployments |")
lines.append("|---|---:|---:|---:|")
for s in sigs:
    (n,) = con.execute(f"SELECT count(*) FROM opcode_features WHERE {s}").fetchone()
    (d,) = con.execute(f"""
        SELECT count(*) FROM contracts c JOIN opcode_features o USING (bytecode_hash)
        WHERE o.{s}
    """).fetchone()
    lines.append(f"| `{s}` | {n:,} | {n/total*100:.2f}% | {d:,} |")

lines.append("\n## Combos of interest\n")
lines.append("| Combo | Bytecodes | Deployments |")
lines.append("|---|---:|---:|")
combos = {
    "transient+CALLER (SIR-like)": "sig_transient AND c_caller>0",
    "selfdestruct+DELEGATECALL": "sig_selfdestruct AND sig_delegate",
    "sstore-no-caller+DELEGATECALL": "sig_sstore_no_caller AND sig_delegate",
    "TSTORE and TLOAD both": "c_tstore>0 AND c_tload>0",
}
for name, cond in combos.items():
    (n,) = con.execute(f"SELECT count(*) FROM opcode_features WHERE {cond}").fetchone()
    (d,) = con.execute(f"""
        SELECT count(*) FROM contracts c JOIN opcode_features o USING (bytecode_hash)
        WHERE {cond}
    """).fetchone()
    lines.append(f"| {name} | {n:,} | {d:,} |")

lines.append("\n## Top redeployed templates per signal\n")
for s in sigs:
    rows = con.execute(f"""
        SELECT o.bytecode_hash, count(*) n, min(o.n_ops) ops
        FROM contracts c JOIN opcode_features o USING (bytecode_hash)
        WHERE o.{s} GROUP BY 1 ORDER BY n DESC LIMIT 3
    """).fetchall()
    lines.append(f"\n**{s}**")
    for h, n, ops in rows:
        lines.append(f"- `{h}` — {n:,} deployments, {ops} ops")

con.close()

with open(f"{OUT_DIR}/RADAR.md", "w") as f:
    f.write("\n".join(lines) + "\n")
print("RADAR.md written", flush=True)
print("EXPORT DONE", flush=True)
