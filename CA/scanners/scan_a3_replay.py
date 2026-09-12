#!/usr/bin/env python3
"""Stage A3 — signature / permit replay (missing nonce or consumption record).

Detection : dispatcher exposes a permit/sig-family selector AND the body calls
            `ecrecover` (precompile 0x01) AND writes storage.
FP filters: size floor. Residual FP is high because the zeroed-storage,
            ABI-agnostic harness cannot synthesise a *valid* signature, so the
            replay effect will not manifest in a plain SINGLE probe.
NOTE      : this scanner measures the candidate universe. The definitive replay
            proof needs a modeled signer (vm.sign + domain separator) — i.e. a
            Track B harness. Kept as a scanner now so the stage is measured; do
            NOT promote to a mass proof stage until the signer template exists.
"""
import common


def predicate():
    return (
        common.any_family("disp_sel", "permit")
        + " AND f.ecrecover_call"
        + " AND f.c_sstore > 0"
        + " AND f.code_size_eff >= 50"
    )


if __name__ == "__main__":
    common.run_stage("a3_replay", predicate(), limit=40,
                     note="Permit/signature replay candidates (needs signer template before mass proof)")
