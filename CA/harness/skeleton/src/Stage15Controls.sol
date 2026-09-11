// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

// ============================================================================
// STAGE 1.5 GROUND-TRUTH CONTROLS — deep-auth properties (P4, P3-lite)
// These validate the new property templates BEFORE they touch wild bytecode.
// ============================================================================

// ---------- P4 (SIR-class) controls ----------
// VulnerableTransient: EXACTLY the SIR bug shape — auth via TLOAD of a slot the
// attacker can prime with TSTORE. P4 two-phase MUST fire on this.
contract VulnerableTransient {
    address public owner; // slot 0

    // anyone can prime transient slot 1 with an arbitrary value (the SIR flaw:
    // this value later masquerades as the authorized pool address)
    function uniswapV3SwapCallback(uint256 amount) external {
        assembly {
            tstore(1, amount)
        }
    }

    function privilegedSetOwner(address a) external {
        address authorized;
        assembly {
            authorized := tload(1)
        }
        require(msg.sender == authorized, "auth"); // stale/generic tload check
        owner = a; // privileged write -> P1 detects slot0 == attacker
    }
}

// SafeTransient: clears/never trusts transient state across the boundary.
contract SafeTransient {
    address public owner; // slot 0

    function uniswapV3SwapCallback(uint256 amount) external {
        assembly {
            tstore(1, amount)
        }
    }

    function privilegedSetOwner(address a) external {
        // real authorization: persistent owner (zero here) + sender match
        require(msg.sender == owner, "auth");
        require(tx.origin == msg.sender, "origin"); // extra gate; symbolic attacker fails
        owner = a;
    }
}

// ---------- P3-lite (naive-proxy hijack) controls ----------
// NaiveProxy: delegatecalls to whatever address sits in storage slot 0 — the
// classic uninitialized/naive proxy. With slot0 = canary, ANY call executes
// canary code. P3-lite MUST fire (balance drain via canary selfdestruct).
contract NaiveProxy {
    function forward() external payable {
        address impl;
        assembly {
            impl := sload(0)
        }
        assembly {
            let ptr := mload(0x40)
            calldatacopy(ptr, 0, calldatasize())
            let r := delegatecall(gas(), impl, ptr, calldatasize(), 0, 0)
            let sz := returndatasize()
            returndatacopy(ptr, 0, sz)
            switch r
            case 0 {
                revert(ptr, sz)
            }
            default {
                return(ptr, sz)
            }
        }
    }
}

// SafeProxy: implementation address is immutable (compiled-in constant).
contract SafeProxy {
    address public immutable implementation;

    constructor() {
        implementation = address(this); // constant-ish; not storage-derived
    }

    function noop() external pure returns (bool) {
        return true;
    }
}

// The canary implementation: any delegatecall into it drains the proxy.
contract KillerImpl {
    function drain() external payable {
        selfdestruct(payable(msg.sender));
    }

    fallback() external payable {
        selfdestruct(payable(msg.sender));
    }
}
