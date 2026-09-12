#!/usr/bin/env python3
"""Stage A9 — unauthenticated pull / attacker-named payer (approval siphoning).

Detection : CALLs `transferFrom`/`safeTransferFrom`/`safeBatchTransferFrom` on an
            external token (selector pushed near an MSTORE before an external
            CALL) with a calldata-derived argument.
FP filters: size floor 100 bytes. LOW PRECISION on purpose — many legitimate
            routers pull from msg.sender; the symbolic consent check (victim
            balance unchanged unless victim is msg.sender) is the real filter,
            and the stage-2.5 4byte selector-DB raises scanner precision.
Reference : ExVul 2026-09-11 ether.fi Liquid / Veda AtomicQueue
            (`solve(...)` spent an attacker-named `solver`'s allowance).
"""
import common

k = common.k4
PULL = [k("transferFrom(address,address,uint256)"),
        k("safeTransferFrom(address,address,uint256)"),
        k("safeTransferFrom(address,address,uint256,bytes)"),
        k("safeBatchTransferFrom(address,address,uint256[],uint256[],bytes)")]


def predicate():
    return (
        common.contains_any("called_sel", PULL)
        + " AND f.c_calldataload > 0"
        + " AND f.code_size_eff >= 100"
    )


if __name__ == "__main__":
    common.run_stage("a9_unauth_pull", predicate(), limit=40,
                     note="Unauthenticated pull / attacker-named payer (Track A P0)")
