// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

// GROUND-TRUTH CONTROLS for the bytecode probe pipeline.
// VulnerableControl MUST trip P1 (unprotected write) and P2 (reachable selfdestruct).
// SafeControl MUST pass both properties (etched with zeroed storage).

contract VulnerableControl {
    address public owner; // slot 0

    function setOwner(address a) external {
        owner = a; // NO access control -> P1 must fire
    }

    function kill() external {
        selfdestruct(payable(msg.sender)); // NO access control -> P2 must fire
    }

    function constantOne() external pure returns (uint256) {
        return 1;
    }
}

contract SafeControl {
    address public owner; // slot 0

    constructor() {
        owner = msg.sender;
    }

    function setOwner(address a) external {
        require(msg.sender == owner, "auth"); // guarded -> P1 must NOT fire
        owner = a;
    }

    function constantOne() external pure returns (uint256) {
        return 1;
    }
}
