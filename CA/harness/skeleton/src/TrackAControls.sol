// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

// ============================================================================
// TRACK A — GROUND-TRUTH CONTROLS (v2)
//
// Every stage ships a MUST_FAIL / MUST_PASS pair with the SAME shape, so the
// only difference is the class bug (not a generic guard). The Safe variant is
// role-gated on `ADMIN = address(0xA11CE)`, which the harness excludes from the
// attacker domain — the realistic "only-role" fix, not the old
// `require(msg.sender == address(0))` trick.
//
// These are compiled to runtime bytecode and etched in the probes; the property
// suite under test is ProbeBaseA's (P_STORAGE_CHANGED, P_BALANCE_LOST,
// P_ATTACKER_PROFIT, P_TOKEN_*). They are ALSO exercised concretely by
// test/TrackASanity.t.sol, which pins the vulnerable branch before CI proves it.
// ============================================================================

address constant ADMIN = address(0xA11CE);

// ---- A1: unprotected initialize -------------------------------------------
contract VulnerableInit {
    address public owner; // slot 0

    function initialize(address o) external {
        owner = o; // no guard -> attacker-controlled slot 0 write
    }
}

contract SafeInit {
    address public owner; // slot 0

    function initialize(address o) external {
        require(msg.sender == ADMIN, "auth"); // attacker != ADMIN -> unreachable
        owner = o;
    }
}

// ---- A2: unprotected upgrade / implementation takeover ---------------------
contract VulnerableUpgrade {
    address public implementation; // slot 0

    function upgradeTo(address impl) external {
        implementation = impl; // no guard
    }
}

contract SafeUpgrade {
    address public implementation; // slot 0

    function upgradeTo(address impl) external {
        require(msg.sender == ADMIN, "auth");
        implementation = impl;
    }
}

// ---- A6: accounting advanced from a manipulable reserve --------------------
// `reserve` is a stand-in for a token balance a third party can change; the bug
// is that permissionless `sync()` folds it into accounting.
contract VulnerableFee {
    uint256 public reserve; // slot 0 (manipulable)
    uint256 public accounted; // slot 1

    function donate(uint256 x) external {
        reserve += x; // anyone can move the reserve
    }

    function sync() external {
        accounted = reserve; // permissionless accounting write
    }
}

contract SafeFee {
    uint256 public reserve; // slot 0
    uint256 public accounted; // slot 1

    function donate(uint256 x) external {
        reserve += x;
    }

    function sync() external {
        require(msg.sender == ADMIN, "auth");
        accounted = reserve;
    }
}

// ---- A7: unchecked external call still advances state ----------------------
contract VulnerableUnchecked {
    uint256 public credited; // slot 0

    function pay(address to, uint256 amt) external {
        (bool ok, ) = to.call{value: amt}(""); // unchecked
        credited += amt; // state advances even when the call fails
    }
}

contract SafeUnchecked {
    uint256 public credited; // slot 0

    function pay(address to, uint256 amt) external {
        require(msg.sender == ADMIN, "auth");
        (bool ok, ) = to.call{value: amt}("");
        require(ok, "call");
        credited += amt;
    }
}