#!/usr/bin/env python3
"""Stage A8 — hostile callback accounting (hook receivers that touch state).

Detection : implements a callback/hook selector (ERC777/1155/721, flash-loan,
            Uniswap-style) AND makes an external call or writes storage, so a
            callback can observe/act on partially-updated accounting.
FP filters: require state impact (SSTORE or CALL) and a size floor; pure
            receiver hooks with no accounting are excluded.
Needs     : the REENTRANT probe template (the callback mock re-enters the target
            with a symbolic selector during the hook).
"""
import common


def predicate():
    return (
        common.any_family("disp_sel", "hooks")
        + " AND (f.c_sstore > 0 OR f.c_call > 0)"
        + " AND f.code_size_eff >= 50"
    )


if __name__ == "__main__":
    common.run_stage("a8_callback", predicate(), limit=40,
                     note="Hostile callback accounting (Track A P2, needs REENTRANT template)")
