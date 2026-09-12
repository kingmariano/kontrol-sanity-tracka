#!/usr/bin/env python3
"""Stage A6 — deflationary / fee-on-transfer / rebasing accounting.

Detection : the contract CALLs `balanceOf(address)` on a token (i.e. reads a
            manipulable balance) AND either writes accounting storage or exposes
            an AMM `skim()`/`sync()` entry point.
FP filters: size floor 100 bytes; require a balance read AND an accounting/AMM
            sink, so plain balance-only views are excluded.
Property  : no accounting advance based on a third-party-manipulable balance.
"""
import common

BAL = common.k4("balanceOf(address)")


def predicate():
    return (
        f"contains(f.called_sel,'{BAL}')"
        + " AND (f.c_sstore > 0 OR " + common.any_family("disp_sel", "skim") + ")"
        + " AND f.code_size_eff >= 100"
    )


if __name__ == "__main__":
    common.run_stage("a6_fee", predicate(), limit=40,
                     note="Deflationary / fee-on-transfer / rebasing accounting (Track A P1)")
