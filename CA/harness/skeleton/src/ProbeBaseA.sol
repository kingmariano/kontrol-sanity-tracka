// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

import {Test} from "forge-std/Test.sol";
import {ConsentToken} from "./ConsentToken.sol";

/// @notice Track A shared harness (v3) — hardened for FN/FP coverage.
///
/// v3 over v2:
///  * **Proxy/impl slot coverage.** v2 watched slots 0..31 only, which MISSES
///    the ERC-1967 implementation slot (0x3608…) and friends — i.e. the A2 class.
///    v3 watches a 64-slot contiguous window PLUS the eight well-known proxy slots:
///      ERC-1967 impl / admin / beacon (+ the un-subtracted impl slot, a real bug),
///      EIP-1822 `PROXIABLE` (UUPS), OZ-zeppelinos impl/admin, Diamond storage.
///  * **Three state models** (`_seed`):
///      M_ZEROED     — all watched slots zero (fast; `P_AUTH_WRITE` valid).
///      M_SEEDED     — each watched slot gets a fresh symbolic value; any write
///                     (even a write of zero) changes the term => catches the
///                     "favourable zero state" FN WITHOUT `setArbitraryStorage`
///                     blowing up the whole storage (the reason v2's symbolic
///                     model OOM'd on 16 GB).
///      M_ARBITRARY  — `setArbitraryStorage` (fully sound, heaviest).
///  * **Token observation** includes the consent token (index 4) so an outflow of
///    the token the A9 controls actually call is caught.
contract ProbeBaseA is Test {
    address internal constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address internal constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address internal constant USDT = 0xdAC17F958D2ee523a2206206994597C13D831ec7;
    address internal constant DAI = 0x6B175474E89094C44Da98b954EedeAC495271d0F;
    address internal constant KONTROL_HEVM = 0x7109709ECfa91a80626fF3989D68f67F5b1DD12D;
    address internal constant KONTROL_CONSOLE = 0x000000000000000000636F6e736F6c652e6c6f67;

    /// Address the A9/A4 value controls hardcode for the consent token.
    address internal constant CONSENT_TOKEN = 0x0000000000000000000000000000000000001111;
    address internal constant ADMIN = address(0xA11CE);

    // ---- watched slot space -------------------------------------------------
    // Kept lean on purpose: every watched slot costs a `vm.store` seed, a
    // `vm.load` snapshot and a compare+assert per test, and that overhead (not
    // the target logic) dominated real-proof time at CONTIG=64. 16 contiguous
    // slots + the 8 well-known proxy slots is the cost/coverage sweet spot.
    uint256 internal constant CONTIG = 16;
    uint256 internal constant NAMED = 8;
    uint256 internal constant NWATCH = CONTIG + NAMED;

    uint8 internal constant M_ZEROED = 0;
    uint8 internal constant M_SEEDED = 1;
    uint8 internal constant M_ARBITRARY = 2;

    // ConsentToken fixed layout.
    uint256 internal constant TK_TRANSFER_COUNT = 2;
    uint256 internal constant TK_LAST_FROM = 3;
    uint256 internal constant TK_LAST_TO = 4;

    address[5] internal TOKENS; // 4 canonical + consent token
    uint256[5] internal tkCount0;
    address[5] internal tkFrom0;
    address[5] internal tkTo0;
    bytes32[NWATCH] internal slot0;
    uint256 internal _bal0;
    uint256 internal _atk0;

    function setUp() public virtual {
        TOKENS = [USDC, WETH, USDT, DAI, CONSENT_TOKEN];
        ConsentToken ct = new ConsentToken();
        bytes memory code = address(ct).code;
        for (uint256 i = 0; i < 5; ++i) {
            vm.etch(TOKENS[i], code);
            vm.store(TOKENS[i], bytes32(TK_TRANSFER_COUNT), bytes32(0));
            vm.store(TOKENS[i], bytes32(TK_LAST_FROM), bytes32(0));
            vm.store(TOKENS[i], bytes32(TK_LAST_TO), bytes32(0));
        }
    }

    /// @dev The k-th watched slot: 0..63 contiguous, then the well-known proxy /
    /// implementation / admin slots. Hardcoded to avoid runtime keccak.
    function _watched(uint256 k) internal pure returns (bytes32) {
        if (k < CONTIG) return bytes32(k);
        if (k == CONTIG + 0) return bytes32(uint256(0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc)); // eip1967 impl
        if (k == CONTIG + 1) return bytes32(uint256(0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103)); // eip1967 admin
        if (k == CONTIG + 2) return bytes32(uint256(0xa3f0ad74e5423aebfd80d3ef4346578335a9a72aeaee59ff6cb3582b35133d50)); // eip1967 beacon
        if (k == CONTIG + 3) return bytes32(uint256(0xc5f16f0fcc639fa48a6947836d9850f504798523bf8c9a3a87d5876cf622bcf7)); // PROXIABLE (UUPS)
        if (k == CONTIG + 4) return bytes32(uint256(0x7050c9e0f4ca769c69bd3a8ef740bc37934f8e2c036e5a723fd8ee048ed3f8c3)); // oz impl
        if (k == CONTIG + 5) return bytes32(uint256(0x10d6a54a4754c8869d6886b5f5d7fbfa5b4522237ea5c60d11bc4e7a1ff9390b)); // oz admin
        if (k == CONTIG + 6) return bytes32(uint256(0xc8fcad8db84d3cc18b4c41d551ea0ee66dd599cde068d998e57d5e09332c131c)); // diamond
        if (k == CONTIG + 7) return bytes32(uint256(0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbd)); // eip1967 impl (unsub)
        revert("watched:oob");
    }

    /// @dev Seed a concrete victim's balance + allowance to `target`.
    function _seedVictim(address victim, address target, uint256 bal, uint256 allow) internal {
        vm.store(CONSENT_TOKEN, keccak256(abi.encode(victim, uint256(0))), bytes32(bal));
        bytes32 inner = keccak256(abi.encode(victim, uint256(1)));
        vm.store(CONSENT_TOKEN, keccak256(abi.encode(target, inner)), bytes32(allow));
    }

    // ---------------------------------------------------------------- attacker
    function _assumeAttacker(address attacker, address target) internal view {
        vm.assume(attacker != address(0));
        vm.assume(uint256(uint160(attacker)) > 0xff);
        vm.assume(attacker != KONTROL_HEVM);
        vm.assume(attacker != KONTROL_CONSOLE);
        vm.assume(attacker != address(this));
        vm.assume(attacker != address(vm));
        vm.assume(attacker != target);
        vm.assume(attacker != ADMIN);
        for (uint256 i = 0; i < 5; ++i) vm.assume(attacker != TOKENS[i]);
    }

    function _assumeAttackerVictim(address attacker, address target, address victim)
        internal
        view
    {
        _assumeAttacker(attacker, target);
        vm.assume(attacker != victim);
        vm.assume(victim != address(0));
    }

    // ------------------------------------------------------------- state models
    function _seedZeroed(address target) internal {
        for (uint256 k = 0; k < NWATCH; ++k) vm.store(target, _watched(k), bytes32(0));
    }

    /// @dev Fresh symbolic value per watched slot. Cheaper than setArbitraryStorage
    /// (which makes *all* storage, incl. keccak arrays, symbolic) while still
    /// closing the zero-state FN for every slot we assert on.
    function _seedSeeded(address target) internal {
        for (uint256 k = 0; k < NWATCH; ++k) {
            vm.store(target, _watched(k), bytes32(vm.randomUint()));
        }
    }

    function _seedArbitrary(address target) internal {
        vm.setArbitraryStorage(target);
    }

    function _seed(address target, uint8 model) internal {
        if (model == M_ZEROED) _seedZeroed(target);
        else if (model == M_SEEDED) _seedSeeded(target);
        else _seedArbitrary(target);
    }

    function _snapshotTarget(address target) internal {
        for (uint256 k = 0; k < NWATCH; ++k) slot0[k] = vm.load(target, _watched(k));
    }

    function _snapshotTokens() internal {
        for (uint256 i = 0; i < 5; ++i) {
            tkCount0[i] = uint256(vm.load(TOKENS[i], bytes32(TK_TRANSFER_COUNT)));
            tkFrom0[i] = address(uint160(uint256(vm.load(TOKENS[i], bytes32(TK_LAST_FROM)))));
            tkTo0[i] = address(uint160(uint256(vm.load(TOKENS[i], bytes32(TK_LAST_TO)))));
        }
    }

    function _markBalances(address target, address attacker) internal {
        _bal0 = target.balance;
        _atk0 = attacker.balance;
    }

    // ------------------------------------------------------------------ checks
    function _checkTarget(address target, address attacker, uint8 model) internal view {
        assertEq(target.balance, _bal0, "P_BALANCE_LOST");
        assertLe(attacker.balance, _atk0, "P_ATTACKER_PROFIT");
        for (uint256 k = 0; k < NWATCH; ++k) {
            bytes32 cur = vm.load(target, _watched(k));
            assertEq(uint256(cur), uint256(slot0[k]), "P_STORAGE_CHANGED");
            if (model == M_ZEROED) {
                assertTrue(cur != bytes32(uint256(uint160(attacker))), "P_AUTH_WRITE");
            }
        }
        _checkTokens(attacker);
    }

    /// @dev Scoped check for value-carrying probes (A5).
    function _checkValue(address target, address attacker) internal view {
        assertGe(target.balance, _bal0, "P_BALANCE_LOST");
        assertLe(attacker.balance, _atk0, "P_ATTACKER_PROFIT");
    }

    /// @dev No token transfer/transferFrom happened and nothing was routed to the
    /// attacker, across the 4 canonical tokens and the consent token.
    function _checkTokens(address attacker) internal view {
        bytes32 atk = bytes32(uint256(uint160(attacker)));
        for (uint256 i = 0; i < 5; ++i) {
            assertEq(
                uint256(vm.load(TOKENS[i], bytes32(TK_TRANSFER_COUNT))),
                tkCount0[i],
                "P_TOKEN_OUTFLOW"
            );
            assertTrue(
                vm.load(TOKENS[i], bytes32(TK_LAST_TO)) != atk,
                "P_TOKEN_TO_ATTACKER"
            );
        }
    }

    /// @dev A9: the concrete victim's tokens must not move.
    function _checkVictim(address victim) internal view {
        bytes32 v = bytes32(uint256(uint160(victim)));
        assertTrue(
            vm.load(CONSENT_TOKEN, bytes32(TK_LAST_FROM)) != v,
            "P_UNAUTH_PULL_FROM"
        );
        assertEq(
            uint256(vm.load(CONSENT_TOKEN, bytes32(TK_TRANSFER_COUNT))),
            tkCount0[4],
            "P_TOKEN_OUTFLOW"
        );
    }
}
