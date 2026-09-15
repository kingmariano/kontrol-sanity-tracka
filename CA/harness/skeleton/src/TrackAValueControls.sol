// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

import {IConsentToken} from "./ConsentToken.sol";

// ============================================================================
// TRACK A — VALUE / CONSENT CONTROLS (v2)
//
// These legitimately move value, so they use scoped properties instead of the
// blanket P_STORAGE_CHANGED suite:
//   A5 VALUE       : attacker net ETH <= 0 and target ETH >= before.
//   A9 UNAUTH_PULL : a concrete victim's tokens must not move without consent
//                    (observed via ConsentToken's fixed lastFrom/transferCount).
//
// TOKEN is the etched ConsentToken address; VICTIM is a concrete victim.
// ADMIN is the same role constant the harness excludes from the attacker.
// ============================================================================

address constant CONSENT_TOKEN = 0x0000000000000000000000000000000000001111;
address constant VALUE_ADMIN = address(0xA11CE);

// ---- A9: unauthenticated pull / attacker-named payer -----------------------
// Mirrors Veda AtomicQueue.solve: `solver` is caller-supplied and spent without
// any consent check, so anyone who has approved the contract can be named.
contract VulnerablePull {
    function pull(address solver, uint256 amt) external {
        IConsentToken(CONSENT_TOKEN).transferFrom(solver, msg.sender, amt);
    }
}

contract SafePull {
    function pull(address solver, uint256 amt) external {
        require(solver == msg.sender || msg.sender == VALUE_ADMIN, "consent");
        IConsentToken(CONSENT_TOKEN).transferFrom(solver, msg.sender, amt);
    }
}

// ---- A5: multicall / msg.value reuse --------------------------------------
// A payable single call that over-credits msg.value models the reuse a
// batch/multicall performs internally.
contract VulnerableValue {
    uint256 public credit; // slot 0

    function depositAndClaim() external payable {
        credit += msg.value; // counted twice -> reuse
        credit += msg.value;
        uint256 c = credit;
        credit = 0;
        (bool ok, ) = msg.sender.call{value: c}("");
        require(ok, "send");
    }
}

contract SafeValue {
    uint256 public credit; // slot 0

    function depositAndClaim() external payable {
        credit += msg.value; // counted once
        uint256 c = credit;
        credit = 0;
        (bool ok, ) = msg.sender.call{value: c}("");
        require(ok, "send");
    }
}