// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

// ============================================================================
// TRACK A — LIGHT BATCH 1 CONTROLS
//
// These reuse the already-validated SINGLE template + ProbeBase property suite
// (P_STORAGE_CHANGED slots 0..15, P_AUTH_WRITE, P_BALANCE_LOST,
// P_ATTACKER_PROFIT, P_TOKEN_*). Each "safe" control is gated so that with the
// harness' zeroed storage (owner == address(0)) and a non-zero symbolic
// attacker the guarded branch is unreachable.
//
// Batch 1 stages: A1 initialize, A2 upgrade, A6 fee/deflationary, A7 unchecked
// external call. (A4/A5/A8/A9 need scoped value/consent properties and land in
// later batches; A3 needs a signer template — see CA/TRACK_A_PROPERTIES.md.)
// ============================================================================

// ---- A1: unprotected initialize -------------------------------------------
contract VulnerableInit {
    address public owner; // slot 0

    function initialize(address o) external {
        owner = o;
    }
}

contract SafeInit {
    address public owner; // slot 0

    function initialize(address o) external {
        require(msg.sender == address(0), "auth");
        owner = o;
    }
}

// ---- A2: unprotected upgrade ----------------------------------------------
contract VulnerableUpgrade {
    address public implementation; // slot 0

    function upgradeTo(address impl) external {
        implementation = impl;
    }
}

contract SafeUpgrade {
    address public implementation; // slot 0

    function upgradeTo(address impl) external {
        require(msg.sender == address(0), "auth");
        implementation = impl;
    }
}

// ---- A6: deflationary / fee-on-transfer accounting ------------------------
// `sync()` models re-reading a manipulable balance into accounting.
contract VulnerableFee {
    uint256 public accounted; // slot 0

    function sync() external {
        accounted += 1;
    }
}

contract SafeFee {
    uint256 public accounted; // slot 0

    function sync() external {
        require(msg.sender == address(0), "auth");
        accounted += 1;
    }
}

// ---- A7: unchecked external call ------------------------------------------
contract VulnerableUnchecked {
    uint256 public credited; // slot 0

    function pay(uint256 amt) external {
        (bool ok, ) = msg.sender.call{value: amt}("");
        credited = amt; // state advances regardless of `ok`
    }
}

contract SafeUnchecked {
    uint256 public credited; // slot 0

    function pay(uint256 amt) external {
        require(msg.sender == address(0), "auth");
        credited = amt;
    }
}
