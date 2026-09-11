#!/usr/bin/env python3
"""Stage 2 FULL batch — deep-auth sweep (P4 two-phase transient, P3-lite proxy).

Targets: deployment-weighted wilds from the radar pools (transient_caller,
proxy_like) + the 4 certification controls as chunk 0.
Size-class partitioning: a giant never shares a chunk; expensive P4 probes
pair up only when small (<=300 ops); cheap P3 probes group by four.
"""
import duckdb
import json

DB = "/tmp/eth-contracts/eth_contracts.duckdb"
TEST_DIR = "/tmp/harness/probe/test"

P4_WILD = """
    SELECT o.bytecode_hash, o.n_ops, count(*) n
    FROM opcode_features o JOIN contracts c USING (bytecode_hash)
    WHERE o.sig_transient_caller AND o.n_ops BETWEEN 80 AND 1500
    GROUP BY 1, 2 ORDER BY n DESC LIMIT 40"""

P3_WILD = """
    SELECT o.bytecode_hash, o.n_ops, count(*) n
    FROM opcode_features o JOIN contracts c USING (bytecode_hash)
    WHERE o.sig_proxy_like
    GROUP BY 1, 2 ORDER BY n DESC LIMIT 40"""

P4_TEMPLATE = """
    // P4 two-phase (SIR-class): {label}: {hash} ({n:,} deployments)
    function test_p4_{fname}(
        bytes4 selA, uint256 prime, bytes4 selB, uint256 a, uint256 b, address attacker
    ) public {{
        vm.assume(attacker != address(0));
        address target = address(uint160(0x3000000 + {idx}));
        vm.etch(target, {code});
        vm.deal(target, 1 ether);
        for (uint256 i = 0; i < 8; i++) vm.store(target, bytes32(i), bytes32(0));
        vm.prank(attacker);
        target.call(abi.encodeWithSelector(selA, prime));
        vm.prank(attacker);
        target.call(abi.encodeWithSelector(selB, a, b));
        assertEq(target.balance, 1 ether, "P4-SD-AFTER-PRIME");
        for (uint256 i = 0; i < 8; i++) {{
            assertTrue(
                vm.load(target, bytes32(i)) != bytes32(uint256(uint160(attacker))),
                "P4-HIJACK-AFTER-PRIME"
            );
        }}
    }}
"""

P3_TEMPLATE = """
    // P3-lite (naive proxy): {label}: {hash} ({n:,} deployments)
    function test_p3_{fname}(bytes4 selector, uint256 a, address attacker) public {{
        vm.assume(attacker != address(0));
        address canary = address(uint160(0xC0DEC0DE));
        vm.etch(canary, hex"{killer}");
        address target = address(uint160(0x3000000 + {idx}));
        vm.etch(target, {code});
        vm.deal(target, 1 ether);
        vm.store(target, bytes32(0), bytes32(uint256(uint160(canary))));
        vm.prank(attacker);
        target.call(abi.encodeWithSelector(selector, a));
        assertEq(target.balance, 1 ether, "P3-HIJACKED-DELEGATECALL");
    }}
"""


def fetch_code(con, h):
    (code,) = con.execute(
        "SELECT substring(bytecode, 3) FROM bytecodes WHERE bytecode_hash = ?", [h]
    ).fetchone()
    return 'hex"' + code + '"'


def main():
    con = duckdb.connect(DB, read_only=True)
    killer = open("/tmp/harness/KillerImpl.hex").read().strip().removeprefix("0x")
    chunks = []  # (class, [(kind, label, hash, ops, n, fname)])

    # chunk 0: certification controls
    ctrl = []
    for kind, name in [("p4", "VulnerableTransient"), ("p4", "SafeTransient"),
                       ("p3", "NaiveProxy"), ("p3", "SafeProxy")]:
        ctrl.append((kind, "CONTROL " + name, name, 0, 0, "control_" + name))
    chunks.append(("CONTROL", ctrl))

    # P4 wilds: pairs when small (<=300 ops), singles otherwise
    p4 = [("p4", "wild transient_caller", h, ops, n, "w%d" % i)
          for i, (h, ops, n) in enumerate(con.execute(P4_WILD).fetchall())]
    buf = []
    for t in p4:
        if t[3] <= 300:
            buf.append(t)
            if len(buf) == 2:
                chunks.append(("P4-SMALL", buf)); buf = []
        else:
            if buf:
                chunks.append(("P4-SMALL", buf)); buf = []
            chunks.append(("P4-HEAVY", [t]))
    if buf:
        chunks.append(("P4-SMALL", buf))

    # P3 wilds: cheap probes, groups of four
    p3 = [("p3", "wild proxy_like", h, ops, n, "w%d" % i)
          for i, (h, ops, n) in enumerate(con.execute(P3_WILD).fetchall())]
    for i in range(0, len(p3), 4):
        chunks.append(("P3", p3[i:i + 4]))

    manifest = []
    for ci, (cls, sel) in enumerate(chunks):
        parts = []
        idx = 0
        tests = []
        for kind, label, h, ops, n, f in sel:
            tests.append("test_%s_%s" % (kind, f))
            if h.startswith("0x"):
                code_lit = fetch_code(con, h)
            else:  # control: bytecode lives in its .hex file
                code_lit = 'hex"%s"' % open("/tmp/harness/%s.hex" % h).read().strip().removeprefix("0x")
            lbl = "%s [%s] (%s deployments)" % (label, cls, format(n, ","))
            if kind == "p4":
                parts.append(P4_TEMPLATE.format(label=lbl, hash=h, n=n,
                                                idx=idx, code=code_lit, fname=f))
            else:
                parts.append(P3_TEMPLATE.format(label=lbl, hash=h, n=n, idx=idx,
                                                code=code_lit, killer=killer,
                                                fname=f))
            idx += 1
        contract = "Stage2Chunk_%d" % ci
        src = ("// AUTO-GENERATED by gen_stage2.py -- stage 2 deep-auth sweep\n"
               "pragma solidity ^0.8.13;\n\n"
               'import {Test} from "forge-std/Test.sol";\n\n'
               "contract %s is Test {\n" % contract + "\n".join(parts) + "}\n")
        out = "%s/Stage2Chunk_%d.sol" % (TEST_DIR, ci)
        with open(out, "w") as fh:
            fh.write(src)
        manifest.append({"chunk": ci, "class": cls, "tests": tests,
                         "targets": [{"hash": h, "ops": ops, "deployments": n}
                                     for kind, label, h, ops, n, f in sel]})
        print("wrote %s (%d probes, %d bytes)" % (out, len(sel), len(src)),
              flush=True)

    with open(TEST_DIR + "/stage2_manifest.json", "w") as fh:
        json.dump(manifest, fh, indent=1)
    print("total chunks: %d" % len(chunks), flush=True)


if __name__ == "__main__":
    main()

