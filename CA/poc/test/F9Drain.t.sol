// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

import {Test} from "forge-std/Test.sol";
import {F9} from "../src/F9.sol";

/// @title F9 PoC — the Kontrol counterexample, and the live-state correction
///
/// The Stage-2/campaign ledger recorded F9 (0x8824fcf9...2a971c8a, 376
/// deployments, 194 funded / 7.787 ETH) as a CONFIRMED "full ETH drain
/// via a prime=0 two-call sequence". The Kontrol harness zeroes storage
/// slots 0..7, so it proved the drain for the *generic* (slot5 == 0) state.
///
/// This PoC separates the two questions:
///   A. Does the proven calldata drain an F9 instance whose slot5 == 0?  YES.
///   B. Does it drain any of the 194 funded live instances?              NO —
///      every funded instance has slot5 == 1, so `0x0b5ab3d5` hits an
///      InvalidJump (it jumps to 0x0, which is not a JUMPDEST) and reverts.
///   C. Causality on the real bytecode: force slot5 = 0 on a forked live
///      instance and the same call drains — but to `slot2` (a third party
///      EOA / address(0)), never to the caller.
///
/// Tests B and C require MAINNET_RPC_URL; they self-skip when it is unset.
contract F9DrainTest is Test {
    address internal constant F9_LIVE = 0x3Fe9a9fE7e6016CE82f58373db739B6D6cB3E876; // 0.0120 ETH, slot5=1
    address internal constant F9_LIVE_BIG = 0xB76Af7de9Df3135C3bEf1625853E49bfDB058a0D; // 2.0 ETH, slot5=1

    uint256 internal constant SLOT5 = 5;
    uint256 internal constant SLOT2 = 2;
    uint256 internal constant SLOT0 = 0;

    /// @dev A: deterministic reproduction of the Kontrol counterexample.
    ///      Etch the bytecode, zero slots 0..7 (exactly what the Stage-2
    ///      harness does), fund 1 ETH, then call the sweep selector.
    function test_A_harness_model_drains_when_slot5_zero() public {
        address target = address(uint160(0xF9000000 + 1));
        vm.etch(target, F9.BYTECODE);
        vm.deal(target, 1 ether);

        for (uint256 i = 0; i < 8; i++) {
            vm.store(target, bytes32(i), bytes32(0));
        }
        // give the sweep an observable, non-zero destination
        address recipient = address(uint160(0xF9000000 + 2));
        vm.store(target, bytes32(SLOT2), bytes32(uint256(uint160(recipient))));

        assertEq(uint256(vm.load(target, bytes32(SLOT5))), 0, "precondition: slot5 == 0");

        address attacker = address(uint160(0xF9000000 + 3));
        vm.prank(attacker);
        (bool ok,) = target.call(hex"0b5ab3d5");

        assertTrue(ok, "sweep should execute when slot5 == 0");
        assertEq(target.balance, 0, "target fully drained");
        assertEq(recipient.balance, 1 ether, "full balance went to slot2");
        assertEq(attacker.balance, 0, "attacker received nothing");
    }

    /// @dev A2: same, with slot2 == 0 (the harness' exact model) — balance is
    ///      burned to address(0), not captured by the attacker.
    function test_A2_harness_model_with_zero_recipient_burns_funds() public {
        address target = address(uint160(0xF9000000 + 4));
        vm.etch(target, F9.BYTECODE);
        vm.deal(target, 1 ether);
        for (uint256 i = 0; i < 8; i++) {
            vm.store(target, bytes32(i), bytes32(0));
        }
        address attacker = address(uint160(0xF9000000 + 5));
        vm.prank(attacker);
        (bool ok,) = target.call(hex"0b5ab3d5");
        assertTrue(ok, "sweep executes");
        assertEq(target.balance, 0, "drained (to address(0))");
        assertEq(attacker.balance, 0, "attacker received nothing");
    }

    /// @dev B: live funded instance (slot5 == 1) rejects the sweep.
    function test_B_live_instance_slot5_blocks_public_drain() public {
        string memory rpc = vm.envOr("MAINNET_RPC_URL", string(""));
        if (bytes(rpc).length == 0) {
            vm.skip(true);
            return;
        }
        vm.createSelectFork(rpc);

        address target = F9_LIVE;
        assertEq(
            uint256(vm.load(target, bytes32(SLOT5))) & 0xff,
            1,
            "live instance slot5 low byte is 1"
        );
        uint256 before = target.balance;
        assertGt(before, 0, "live instance is funded");

        address attacker = address(uint160(0xF9000000 + 6));
        vm.prank(attacker);
        (bool ok,) = target.call(hex"0b5ab3d5");

        assertFalse(ok, "sweep reverts on live state (slot5 != 0)");
        assertEq(target.balance, before, "no funds moved");
        assertEq(attacker.balance, 0, "attacker gained nothing");
    }

    /// @dev B2: the largest funded instance (2.0 ETH) is likewise gated.
    function test_B2_live_2eth_instance_gated() public {
        string memory rpc = vm.envOr("MAINNET_RPC_URL", string(""));
        if (bytes(rpc).length == 0) {
            vm.skip(true);
            return;
        }
        vm.createSelectFork(rpc);
        address target = F9_LIVE_BIG;
        assertEq(uint256(vm.load(target, bytes32(SLOT5))) & 0xff, 1, "slot5=1");
        uint256 before = target.balance;
        address attacker = address(uint160(0xF9000000 + 7));
        vm.prank(attacker);
        (bool ok,) = target.call(hex"0b5ab3d5");
        assertFalse(ok, "gated");
        assertEq(target.balance, before, "2 ETH untouched");
    }

    /// @dev C: causality on real bytecode+state. Force slot5 = 0 on the live
    ///      instance; the sweep now runs — but pays slot2, not the caller.
    function test_C_forcing_slot5_zero_drains_to_slot2_not_attacker() public {
        string memory rpc = vm.envOr("MAINNET_RPC_URL", string(""));
        if (bytes(rpc).length == 0) {
            vm.skip(true);
            return;
        }
        vm.createSelectFork(rpc);
        address target = F9_LIVE;

        address slot2 = address(uint160(uint256(vm.load(target, bytes32(SLOT2)))));
        assertTrue(slot2 != address(0), "this instance has a non-zero slot2");
        uint256 before = target.balance;
        uint256 slot2Before = slot2.balance;

        vm.store(target, bytes32(SLOT5), bytes32(0)); // simulate "flag cleared"
        address attacker = address(uint160(0xF9000000 + 8));
        vm.prank(attacker);
        (bool ok,) = target.call(hex"0b5ab3d5");

        assertTrue(ok, "sweep executes once slot5 == 0");
        assertEq(target.balance, 0, "target drained");
        assertEq(slot2.balance, slot2Before + before, "funds went to slot2");
        assertEq(attacker.balance, 0, "attacker received nothing");
    }
}
