// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

// ============================================================================
// ConsentToken — minimal mapping-backed ERC-20 used by the Track A value probes.
//
// The scan-time MockERC20 only exposes counter slots; A4 (round-trip) and A9
// (unauthorized pull) need *real* balances and allowances so a probe can seed a
// victim (balance + allowance to the target) and observe unauthorized movement.
//
// Fixed storage layout (relied on by the templates):
//   slot 0 : mapping(address => uint256) balanceOf
//   slot 1 : mapping(address => mapping(address => uint256)) allowance
//   slot 2 : uint256 transferCount
//   slot 3 : address lastFrom
//   slot 4 : address lastTo
//   slot 5 : uint256 lastAmount
// ============================================================================

interface IConsentToken {
    function balanceOf(address) external view returns (uint256);
    function allowance(address, address) external view returns (uint256);
    function approve(address, uint256) external returns (bool);
    function transfer(address, uint256) external returns (bool);
    function transferFrom(address, address, uint256) external returns (bool);
}

contract ConsentToken {
    mapping(address => uint256) public balanceOf; // slot 0
    mapping(address => mapping(address => uint256)) public allowance; // slot 1
    uint256 public transferCount; // slot 2
    address public lastFrom; // slot 3
    address public lastTo; // slot 4
    uint256 public lastAmount; // slot 5

    function approve(address spender, uint256 amt) external returns (bool) {
        allowance[msg.sender][spender] = amt;
        return true;
    }

    function transfer(address to, uint256 amt) external returns (bool) {
        return _move(msg.sender, to, amt);
    }

    function transferFrom(address from, address to, uint256 amt) external returns (bool) {
        uint256 a = allowance[from][msg.sender];
        require(a >= amt, "allowance");
        allowance[from][msg.sender] = a - amt;
        return _move(from, to, amt);
    }

    function _move(address from, address to, uint256 amt) internal returns (bool) {
        require(balanceOf[from] >= amt, "balance");
        balanceOf[from] -= amt;
        balanceOf[to] += amt;
        transferCount += 1;
        lastFrom = from;
        lastTo = to;
        lastAmount = amt;
        return true;
    }
}
