#!/usr/bin/env python3
"""Stage A5 — multicall / batch `msg.value` reuse.

Detection : dispatcher exposes a multicall/batch selector AND the body reads
            CALLVALUE (payable), so a reused `msg.value` can over-credit.
FP filters: size floor. Multicall3 itself should be allowlisted once its code
            hash is pinned; the proof (attacker profit <= 0) is the real filter.
Needs     : the VALUE probe template (calls carrying `msg.value`), which the
            current suite lacks.
"""
import common


def predicate():
    return (
        common.any_family("disp_sel", "multicall")
        + " AND f.c_callvalue > 0"
        + " AND f.code_size_eff >= 50"
    )


if __name__ == "__main__":
    common.run_stage("a5_multicall", predicate(), limit=40,
                     note="Multicall / batch msg.value reuse (Track A P1, needs VALUE template)")
