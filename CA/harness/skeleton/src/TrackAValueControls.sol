// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

import {IConsentToken} from "./ConsentToken.sol";

// ============================================================================
// TRACK A — VALUE / CONSENT CONTROLS (Batch 2)
//
// Unlike the Batch 1 controls these legitimately move tokens, so they cannot use
// the blanket P_STORAGE_CHANGED suite. Their probes assert scoped invariants:
//   A9 UNAUTH_PULL : a named victim's balance must not move without consent.
//
// TOKEN is the etched ConsentToken address; VICTIM is a concrete victim.
// ============================================================================

address constant CONSENT_TOKEN = 0x0000000000000000000000000000000000001111;

// ---- A9: unauthenticated pull / attacker-named payer -----------------------
// Mirrors Veda AtomicQueue.solve: `solver` is caller-supplied and spent without
// any consent check, so anyone who approved the contract can be named as payer.
contract VulnerablePull {
    function pull(address solver, uint256 amt) external {
        IConsentToken(CONSENT_TOKEN).transferFrom(solver, msg.sender, amt);
    }
}

contract SafePull {
    function pull(address solver, uint256 amt) external {
        require(solver == msg.sender, "consent");
        IConsentToken(CONSENT_TOKEN).transferFrom(solver, msg.sender, amt);
    }
}
