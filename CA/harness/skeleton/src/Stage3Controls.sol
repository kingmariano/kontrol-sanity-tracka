// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

// ============================================================================
// STAGE 3 GROUND-TRUTH CONTROLS — value-extraction / profit oracle (P7)
//
// The Stage-3 property is ABI-agnostic: after a bounded sequence of arbitrary
// calls by a symbolic attacker, the target must not lose ETH and the attacker
// must not gain ETH. These controls certify that the oracle actually fires on
// value extraction and stays silent on correctly-guarded code.
// ============================================================================

// MUST FAIL: anyone can sweep the whole balance to themselves (single call).
contract VulnerableProfit {
    receive() external payable {}

    function drain() external {
        (bool ok, ) = payable(msg.sender).call{value: address(this).balance}("");
        require(ok, "send");
    }
}

// MUST PASS: same payout, but owner-gated. With zeroed storage owner == 0 and
// attacker != 0, so the branch is unreachable.
contract SafeProfit {
    address public owner; // slot 0

    receive() external payable {}

    function drain() external {
        require(msg.sender == owner, "auth");
        (bool ok, ) = payable(msg.sender).call{value: address(this).balance}("");
        require(ok, "send");
    }
}

// MUST FAIL: unprotected credit, then withdraw — two-call value extraction.
// No mappings (avoids symbolic-keccak storage), single uint in slot 0.
contract VulnerableAmplify {
    uint256 public credited; // slot 0

    receive() external payable {}

    function credit(uint256 amt) external {
        credited += amt;
    }

    function withdraw(uint256 amt) external {
        require(credited >= amt, "bal");
        credited -= amt;
        (bool ok, ) = payable(msg.sender).call{value: amt}("");
        require(ok, "send");
    }
}

// MUST PASS: credit is owner-gated, so the two-call sequence is unreachable.
contract SafeAmplify {
    address public owner; // slot 0
    uint256 public credited; // slot 1

    receive() external payable {}

    function credit(uint256 amt) external {
        require(msg.sender == owner, "auth");
        credited += amt;
    }

    function withdraw(uint256 amt) external {
        require(credited >= amt, "bal");
        credited -= amt;
        (bool ok, ) = payable(msg.sender).call{value: amt}("");
        require(ok, "send");
    }
}
