#!/usr/bin/env python3
"""Generate Kontrol symbolic probe tests from the opcode radar.

Emits /tmp/harness/probe/test/ProbeBatch1.sol containing:
  - 2 ground-truth controls (VulnerableControl -> must FAIL proofs,
    SafeControl -> must PASS) — validates the probe itself
  - N candidate bytecodes pulled from the radar signals in DuckDB

Properties per probe (single symbolic call from an arbitrary attacker):
  P2-SELFDESTRUCT: target ETH balance must remain untouched
  P1-HIJACK:       storage slots 0..7 must never come to hold the attacker's address
"""
import sys
import argparse
import duckdb

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
OUT = "/tmp/harness/probe/test/ProbeBatch1.sol"
CONTROLS = {
    "vulnerable_control": "/tmp/harness/VulnerableControl.hex",
    "safe_control": "/tmp/harness/SafeControl.hex",
}

# deployment-weighted triage: biggest blast radius first
CANDIDATE_QUERIES = {
    "sstore_no_caller_delegate": """
        SELECT o.bytecode_hash, o.n_ops, count(*) n
        FROM opcode_features o JOIN contracts c USING (bytecode_hash)
        WHERE o.sig_sstore_no_caller AND o.sig_delegate
        GROUP BY 1, 2 ORDER BY n DESC LIMIT 20""",
    "selfdestruct_delegate": """
        SELECT o.bytecode_hash, o.n_ops, count(*) n
        FROM opcode_features o JOIN contracts c USING (bytecode_hash)
        WHERE o.sig_selfdestruct AND o.sig_delegate
        GROUP BY 1, 2 ORDER BY n DESC LIMIT 20""",
}

TEMPLATE = """
    // {label}: {hash} ({ops} ops)
    function test_probe_{fname}(
        bytes4 selector, uint256 a0, uint256 a1, address attacker
    ) public {{
        vm.assume(attacker != address(0));
        address target = address(uint160(0x1000000 + {idx}));
        vm.etch(target, {code});
        vm.deal(target, 1 ether);
        for (uint256 i = 0; i < 8; i++) {{
            vm.store(target, bytes32(i), bytes32(0));
        }}
        vm.prank(attacker);
        (bool ok, ) = target.call(abi.encodeWithSelector(selector, a0, a1));
        // P2: reachable selfdestruct drains the balance
        assertEq(target.balance, 1 ether, "P2-SELFDESTRUCT-REACHABLE");
        // P1: unprotected write of caller-controlled value (admin/owner slot pattern)
        for (uint256 i = 0; i < 8; i++) {{
            assertTrue(
                vm.load(target, bytes32(i)) != bytes32(uint256(uint160(attacker))),
                "P1-UNPROTECTED-WRITE"
            );
        }}
    }}
"""

def fetch_code(con, h):
    (code,) = con.execute(
        "SELECT substring(bytecode, 3) FROM bytecodes WHERE bytecode_hash = ?", [h]
    ).fetchone()
    return "hex\"" + code + "\""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=-1,
                    help="chunk index; -1 = legacy batch-1 (controls + probes)")
    ap.add_argument("--chunk-size", type=int, default=5)
    args = ap.parse_args()

    con = duckdb.connect(DB, read_only=True)
    idx = 0
    parts = []

    if args.chunk < 0:
        # legacy batch-1: controls + 2 candidates per signal query
        for name, path in CONTROLS.items():
            code = open(path).read().strip()
            if code.startswith("0x"):
                code = code[2:]  # hex"" literals reject the 0x prefix
            parts.append(TEMPLATE.format(
                label=f"CONTROL {'must FAIL' if name.startswith('vuln') else 'must PASS'}",
                hash=name, ops="control", fname=name, idx=idx, code=f"hex\"{code}\""))
            idx += 1
        for label, sql in CANDIDATE_QUERIES.items():
            for h, ops, _n in con.execute(sql).fetchall():
                parts.append(TEMPLATE.format(
                    label=label, hash=h, ops=ops,
                    fname=f"{label}_{idx}", idx=idx, code=fetch_code(con, h)))
                idx += 1
        out_path = OUT
        contract = "ProbeBatch1"
    else:
        # chunked sweep: SIZE-CLASS PARTITIONING
        # A job is only as slow as its slowest member -> a GIANT (>1500 ops)
        # always gets a chunk of its own, MID (601-1500) pairs up, SMALL (<=600)
        # groups in fives. Deployment-weighted interleaving is preserved inside
        # each class so both signal classes stay represented.
        sets = {label: con.execute(sql).fetchall()
                for label, sql in CANDIDATE_QUERIES.items()}
        flat = []
        while any(sets.values()):
            for label in CANDIDATE_QUERIES:
                if sets[label]:
                    flat.append((label, sets[label].pop(0)))

        chunks = []  # list of (class, [(label, hash, ops, n), ...])
        small, mid = [], []
        for label, (h, ops, n) in flat:
            item = (label, h, ops, n)
            if ops > 1500:
                chunks.append(("GIANT", [item]))
            elif ops > 600:
                mid.append(item)
                if len(mid) == 2:
                    chunks.append(("MID", mid)); mid = []
            else:
                small.append(item)
                if len(small) == 5:
                    chunks.append(("SMALL", small)); small = []
        if mid:
            chunks.append(("MID", mid))
        if small:
            chunks.append(("SMALL", small))

        # deterministic manifest for the CI workflow (chunk -> tests + class)
        import json
        manifest = [
            {"chunk": ci, "class": cls,
             "tests": [f"test_probe_c{ci}_{i}" for i in range(len(sel))],
             "targets": [{"hash": h, "ops": ops, "deployments": n}
                         for label, h, ops, n in sel]}
            for ci, (cls, sel) in enumerate(chunks)
        ]
        with open("/tmp/harness/probe/test/chunk_manifest.json", "w") as f:
            json.dump(manifest, f, indent=1)

        cls, sel = chunks[args.chunk]
        for i, (label, h, ops, n) in enumerate(sel):
            parts.append(TEMPLATE.format(
                label=f"{label} [{cls}] ({n:,} deployments)", hash=h, ops=ops,
                fname=f"c{args.chunk}_{i}", idx=idx, code=fetch_code(con, h)))
            idx += 1
        out_path = f"/tmp/harness/probe/test/ProbeChunk_{args.chunk}.sol"
        contract = f"ProbeChunk_{args.chunk}"

    src = f"""// SPDX-License-Identifier: UNLICENSED
// AUTO-GENERATED by gen_probe.py -- chunk {args.chunk}
pragma solidity ^0.8.13;

import {{Test}} from "forge-std/Test.sol";

contract {contract} is Test {{
""" + "\n".join(parts) + "}\n"

    with open(out_path, "w") as f:
        f.write(src)
    print(f"wrote {out_path} with {idx} probes ({len(src):,} bytes)", flush=True)


if __name__ == "__main__":
    main()
