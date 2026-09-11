// SPDX-License-Identifier: MIT
pragma solidity ^0.8.13;

import {Test} from "forge-std/Test.sol";

/// @title F8 live-gate verification (bytecode 0x1aba7e71..., 1930 B)
///
/// F8 = Ownable-style proxy:
///   init(address factory)  0x19ab453c, gated by slot1 == 0
///   recycle(address[])     0x724c6ddc, gated by msg.sender == slot1, pays SELFBALANCE
///   factory()              0xc45a0155 (slot1 getter)
///
/// Result of the live scan: **none of the funded instances is exploitable.**
/// Every address in the F8 census that actually carries code has slot0=1 and
/// slot1 = a protocol factory. The one 0.01-ETH "uninitialized" entry
/// (0xd1c68218) has **zero code** — an empty account, not a contract.
contract F8LiveTest is Test {
    address internal constant FLAGSHIP = 0x3952fe747D6967b3Cf53A84593a95114E7De3201; // 47 USDC
    address internal constant CODELESS = 0xd1C68218D10253A104371d5D99388c31b768Ef53;   // 0.01 ETH, no code

    // all F8 census addresses that are funded AND carry code (from live scan)
    address[8] internal FUNDED = [
        0x09Abcb496FBBcd3F43eBF05e7256114e71Feb7E3,
        0x1918F166BBd9CfF6a0ce01306c912A565B91324B,
        0x22a646eF282b62af0391EbA132C53dc208928182,
        0x41D2fad7f82CdF46b8F441274bede4ba22ccB98e,
        0x4F22DC2122DF85D40646d525474A49901616d46F,
        0xa73d486e4e4C9a3A102393de2883EDE1FBEF97A5,
        0xbF8f64B62025FC89120F6ce457aF8E073B170671,
        FLAGSHIP
    ];

    uint256 internal constant SLOT1 = 1;

    function _fork() internal returns (bool) {
        string memory rpc = vm.envOr("MAINNET_RPC_URL", string(""));
        if (bytes(rpc).length == 0) {
            vm.skip(true);
            return false;
        }
        vm.createSelectFork(rpc);
        return true;
    }

    /// Every code-bearing funded F8 instance is initialized (slot1 = factory).
    function test_F8_all_real_instances_initialized() public {
        if (!_fork()) return;
        for (uint256 i = 0; i < FUNDED.length; i++) {
            address a = FUNDED[i];
            assertGt(a.code.length, 0, "instance carries F8 code");
            uint256 factory = uint256(vm.load(a, bytes32(SLOT1))) & ((1 << 160) - 1);
            assertTrue(factory != 0, "slot1 (factory) is set");
        }
    }

    /// init() is blocked on every code-bearing instance.
    function test_F8_init_blocked_on_all_real_instances() public {
        if (!_fork()) return;
        address attacker = address(uint160(0xF8000001));
        for (uint256 i = 0; i < FUNDED.length; i++) {
            vm.prank(attacker);
            (bool ok,) = FUNDED[i].call(abi.encodeWithSelector(0x19ab453c, attacker));
            assertFalse(ok, "init reverts (already initialized)");
            assertTrue(
                uint256(vm.load(FUNDED[i], bytes32(SLOT1))) != uint256(uint160(attacker)),
                "factory unchanged"
            );
        }
    }

    /// The sole "uninitialized" funded entry is not a contract at all.
    function test_F8_apparent_uninitialized_entry_is_codeless() public {
        if (!_fork()) return;
        assertEq(CODELESS.code.length, 0, "no code: empty account, not exploitable");
        assertGt(CODELESS.balance, 0, "but it does hold ETH (sent to an empty address)");
    }
}
