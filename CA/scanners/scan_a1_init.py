#!/usr/bin/env python3
"""Stage A1 — unprotected initialize / reinitialize (permissionless takeover).

Detection : dispatcher exposes an initializer-family selector AND the body writes
            storage (so a successful call can set an owner/admin/flag slot).
FP filters: drop tiny stubs (<50 effective bytes) and pure proxy shells
            (delegatecall-only, <=40 ops) whose logic lives in the impl.
Residual FP: a properly `initializer`-guarded contract is still selected — the
            symbolic proof is the final precision filter (it PASSES on guards).
"""
import common


def predicate():
    return (
        common.any_family("disp_sel", "initialize")
        + " AND f.c_sstore > 0"
        + " AND f.code_size_eff >= 50"
        + " AND NOT (f.c_delegatecall > 0 AND f.n_ops <= 40)"
    )


if __name__ == "__main__":
    common.run_stage("a1_init", predicate(), limit=200,
                     note="Unprotected initializer/reinitializer takeover (Track A P0)")
