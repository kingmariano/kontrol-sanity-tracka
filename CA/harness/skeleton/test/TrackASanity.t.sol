// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

import {Test} from "forge-std/Test.sol";
import {
    VulnerableInit,
    SafeInit,
    VulnerableUpgrade,
    SafeUpgrade,
    VulnerableFee,
    SafeFee,
    VulnerableUnchecked,
    SafeUnchecked
} from "../src/TrackAControls.sol";
import {VulnerablePull, SafePull, VulnerableValue, SafeValue} from "../src/TrackAValueControls.sol";
import {ConsentToken} from "../src/ConsentToken.sol";

/// @notice Concrete sanity gate for the Track A controls (v2).
///
/// Purpose: pin the MUST_FAIL / MUST_PASS controls with a *concrete* Foundry run
/// BEFORE the symbolic CI gate. Stages 1-3 never did this, and several control
/// lapses went unnoticed until CI. Every assertion here is on the exact state
/// delta the matching symbolic property checks:
///   MUST_FAIL controls: the class bug moves state/value under a plain attacker.
///   MUST_PASS controls: the role gate makes the same call revert, so nothing moves.
///
/// This runs locally (no docker); Kontrol still runs only in CI.
contract TrackASanity is Test {
    address internal constant ADMIN = address(0xA11CE);
    address internal constant ATTACKER = address(0xB0B);
    address internal constant VICTIM = address(0xCAFE);
    address internal constant TARGET = address(0x1000);
    address internal constant CONSENT_TOKEN = 0x0000000000000000000000000000000000001111;

    uint256 internal constant NSLOTS = 16;

    // ------------------------------------------------------------- helpers
    function _etchZeroed(address t, bytes memory runtime) internal {
        vm.etch(t, runtime);
        for (uint256 i = 0; i < NSLOTS; ++i) vm.store(t, bytes32(i), bytes32(0));
    }

    function _slot(address t, uint256 i) internal view returns (uint256) {
        return uint256(vm.load(t, bytes32(i)));
    }

    // Balances/allowances inside the etched ConsentToken (fixed layout).
    function _setBal(address token, address who, uint256 amt) internal {
        vm.store(token, keccak256(abi.encode(who, uint256(0))), bytes32(amt));
    }

    function _setAllow(address token, address owner, address spender, uint256 amt) internal {
        bytes32 inner = keccak256(abi.encode(owner, uint256(1)));
        vm.store(token, keccak256(abi.encode(spender, inner)), bytes32(amt));
    }

    function _bal(address token, address who) internal view returns (uint256) {
        return uint256(vm.load(token, keccak256(abi.encode(who, uint256(0)))));
    }

    // ================================================== A1 initialize
    function test_concrete_a1_vulnerable() public {
        _etchZeroed(TARGET, address(new VulnerableInit()).code);
        vm.prank(ATTACKER);
        VulnerableInit(TARGET).initialize(ATTACKER); // no guard -> writes slot 0
        assertEq(_slot(TARGET, 0), uint256(uint160(ATTACKER)), "A1 vuln did not write owner");
    }

    function test_concrete_a1_safe() public {
        _etchZeroed(TARGET, address(new SafeInit()).code);
        vm.prank(ATTACKER);
        vm.expectRevert(bytes("auth"));
        SafeInit(TARGET).initialize(ATTACKER);
        assertEq(_slot(TARGET, 0), 0, "A1 safe wrote owner");
    }

    // ================================================== A2 upgrade
    function test_concrete_a2_vulnerable() public {
        _etchZeroed(TARGET, address(new VulnerableUpgrade()).code);
        vm.prank(ATTACKER);
        VulnerableUpgrade(TARGET).upgradeTo(ATTACKER); // no guard -> writes impl slot
        assertEq(_slot(TARGET, 0), uint256(uint160(ATTACKER)), "A2 vuln did not write impl");
    }

    function test_concrete_a2_safe() public {
        _etchZeroed(TARGET, address(new SafeUpgrade()).code);
        vm.prank(ATTACKER);
        vm.expectRevert(bytes("auth"));
        SafeUpgrade(TARGET).upgradeTo(ATTACKER);
        assertEq(_slot(TARGET, 0), 0, "A2 safe wrote impl");
    }

    // ================================================== A6 manipulable accounting
    function test_concrete_a6_vulnerable() public {
        _etchZeroed(TARGET, address(new VulnerableFee()).code);
        vm.store(TARGET, bytes32(0), bytes32(uint256(5))); // reserve (manipulable)
        vm.prank(ATTACKER);
        VulnerableFee(TARGET).sync(); // permissionless: accounted = reserve
        assertEq(_slot(TARGET, 1), 5, "A6 vuln did not advance accounting");
    }

    function test_concrete_a6_safe() public {
        _etchZeroed(TARGET, address(new SafeFee()).code);
        vm.store(TARGET, bytes32(0), bytes32(uint256(5)));
        vm.prank(ATTACKER);
        vm.expectRevert(bytes("auth"));
        SafeFee(TARGET).sync();
        assertEq(_slot(TARGET, 1), 0, "A6 safe advanced accounting");
    }

    // ================================================== A7 unchecked external call
    function test_concrete_a7_vulnerable() public {
        _etchZeroed(TARGET, address(new VulnerableUnchecked()).code);
        vm.deal(TARGET, 1 ether);
        vm.prank(ATTACKER);
        VulnerableUnchecked(TARGET).pay(payable(ATTACKER), 2 ether); // call fails, credited += amt
        assertEq(_slot(TARGET, 0), 2 ether, "A7 vuln did not advance state on failed call");
        assertEq(ATTACKER.balance, 0, "A7 vuln attacker unexpectedly paid");
    }

    function test_concrete_a7_safe() public {
        _etchZeroed(TARGET, address(new SafeUnchecked()).code);
        vm.deal(TARGET, 1 ether);
        vm.prank(ATTACKER);
        vm.expectRevert(bytes("auth"));
        SafeUnchecked(TARGET).pay(payable(ATTACKER), 2 ether);
        assertEq(_slot(TARGET, 0), 0, "A7 safe advanced state");
    }

    // ================================================== A9 unauthenticated pull
    function test_concrete_a9_vulnerable() public {
        _etchZeroed(TARGET, address(new VulnerablePull()).code);
        vm.etch(CONSENT_TOKEN, address(new ConsentToken()).code);
        _setBal(CONSENT_TOKEN, VICTIM, 1_000 ether);
        _setAllow(CONSENT_TOKEN, VICTIM, TARGET, 1_000 ether);
        vm.prank(ATTACKER);
        VulnerablePull(TARGET).pull(VICTIM, 100 ether); // attacker names the victim
        assertEq(_bal(CONSENT_TOKEN, VICTIM), 900 ether, "A9 vuln did not pull victim funds");
        assertEq(_bal(CONSENT_TOKEN, ATTACKER), 100 ether, "A9 vuln attacker did not receive");
    }

    function test_concrete_a9_safe() public {
        _etchZeroed(TARGET, address(new SafePull()).code);
        vm.etch(CONSENT_TOKEN, address(new ConsentToken()).code);
        _setBal(CONSENT_TOKEN, VICTIM, 1_000 ether);
        _setAllow(CONSENT_TOKEN, VICTIM, TARGET, 1_000 ether);
        vm.prank(ATTACKER);
        vm.expectRevert(bytes("consent"));
        SafePull(TARGET).pull(VICTIM, 100 ether);
        assertEq(_bal(CONSENT_TOKEN, VICTIM), 1_000 ether, "A9 safe moved victim funds");
    }

    // ================================================== A5 msg.value reuse
    function test_concrete_a5_vulnerable() public {
        _etchZeroed(TARGET, address(new VulnerableValue()).code);
        vm.deal(TARGET, 3 ether);
        vm.deal(ATTACKER, 1 ether);
        uint256 a0 = ATTACKER.balance;
        vm.prank(ATTACKER);
        VulnerableValue(TARGET).depositAndClaim{value: 1 ether}(); // credits 2x, pays out 2x
        assertEq(ATTACKER.balance, a0 + 1 ether, "A5 vuln attacker did not profit");
    }

    function test_concrete_a5_safe() public {
        _etchZeroed(TARGET, address(new SafeValue()).code);
        vm.deal(TARGET, 3 ether);
        vm.deal(ATTACKER, 1 ether);
        uint256 a0 = ATTACKER.balance;
        vm.prank(ATTACKER);
        SafeValue(TARGET).depositAndClaim{value: 1 ether}(); // credits once, pays once
        assertEq(ATTACKER.balance, a0, "A5 safe attacker profited");
    }
}