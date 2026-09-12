#!/usr/bin/env python3
"""Stage A7 — unchecked external call / calldata-derived call target.

Detection : makes an external CALL/DELEGATECALL/STATICCALL, has a
            calldata-derived argument (CALLDATALOAD > 0), and never inspects
            RETURNDATASIZE (so success/failure and target identity are unchecked).
FP filters: require at least one external call AND no RETURNDATASIZE check AND a
            size floor. Low-level safe wrappers that check the call result are
            excluded by the RETURNDATASIZE condition.
Property  : no state advance when an external call is attacker-controlled or fails.
"""
import common


def predicate():
    return (
        "NOT f.returndata_checked"
        + " AND (f.c_call + f.c_delegatecall + f.c_staticcall) > 0"
        + " AND f.c_calldataload > 0"
        + " AND f.code_size_eff >= 50"
    )


if __name__ == "__main__":
    common.run_stage("a7_unchecked", predicate(), limit=40,
                     note="Unchecked external call / calldata-derived call target (Track A P2)")
