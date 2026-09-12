#!/usr/bin/env python3
"""Stage A4 — rounding / round-trip value conservation (near-empty vault).

Detection : exposes BOTH a deposit-side and a withdrawal-side entry point AND a
            share<->asset conversion view, with integer division in the body.
FP filters: require the full selector triangle (deposit-like AND withdraw-like
            AND convert/preview-like) so unrelated `deposit()` functions are not
            selected; size floor 200 bytes.
Property  : deposit->redeem (and mint->withdraw) cannot increase caller value;
            shares > 0 whenever assets > 0. This is the sweepable form of the
            near-empty-market / ERC-4626 inflation class (OWASP SC07).
"""
import common

k = common.k4
DEPOSIT = [k("deposit(uint256,address)"), k("deposit(uint256)"), k("mint(uint256,address)")]
WITHDRAW = [k("withdraw(uint256,address,address)"), k("withdraw(uint256)"),
            k("redeem(uint256,address,address)")]
CONVERT = [k("convertToShares(uint256)"), k("convertToAssets(uint256)"),
           k("previewDeposit(uint256)"), k("previewMint(uint256)"),
           k("previewWithdraw(uint256)"), k("previewRedeem(uint256)"),
           k("totalAssets()"), k("getSharesByPooledEth(uint256)")]


def predicate():
    return (
        common.contains_any("disp_sel", DEPOSIT)
        + " AND " + common.contains_any("disp_sel", WITHDRAW)
        + " AND " + common.contains_any("disp_sel", CONVERT)
        + " AND f.c_div > 0 AND f.code_size_eff >= 200"
    )


if __name__ == "__main__":
    common.run_stage("a4_roundtrip", predicate(), limit=40,
                     note="Rounding / round-trip value conservation, near-empty vault (Track A P1)")
