#!/usr/bin/env python3
"""Stage A2 — unprotected upgrade / attacker-controlled DELEGATECALL.

Detection : dispatcher exposes an upgrade-family selector AND the body performs
            DELEGATECALL (so an attacker-set implementation is actually reached).
FP filters: require DELEGATECALL; size floor. The proof refutes contracts with a
            real `_authorizeUpgrade`/`onlyOwner` gate (they PASS).
"""
import common


def predicate():
    return (
        common.any_family("disp_sel", "upgrade")
        + " AND f.c_delegatecall > 0"
        + " AND f.code_size_eff >= 50"
    )


if __name__ == "__main__":
    common.run_stage("a2_upgrade", predicate(), limit=40,
                     note="Unprotected upgrade / attacker-controlled delegatecall (Track A P0)")
