// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.13;

import {Test} from "forge-std/Test.sol";
import {ConsentToken} from "./ConsentToken.sol";

/// @notice Track A shared harness (v2).
///
/// Deliberate fixes over the stage1/2/3 `ProbeBase` (see CA/kontrol):
///  * **Token observation is keccak-free.** We etch `ConsentToken` at the four
///    canonical token addresses and watch its *fixed* slots (transferCount,
///    lastFrom, lastTo) instead of `balanceOf` mappings. Symbolic-keccak reads
///    are what blew up the old suites; fixed slots keep the proofs small while
///    still detecting any transfer/transferFrom the target performs.
///  * **Selectable state model.** `_seedZeroed` (fast, comparable with stages
///    1-3) or `_seedSymbolic` (`setArbitraryStorage`). The symbolic model closes
///    the "favourable zero state" false negative: a write that stores zero, or a
///    guard that only holds because a slot is zero, no longer hides the path.
///  * **Attacker assumptions are centralised** (`_assumeAttacker`) so every probe
///    kills the 3-way symbolic-address branching (file 08.5) identically.
///  * **Goal shape.** `P_ATTACKER_PROFIT` (ETH) and `P_BALANCE_LOST` (target ETH)
///    are asserted in every probe, not just slot diffs.
///  * **Honesty.** `P_AUTH_WRITE` is only asserted under the ZEROED model: under
///    symbolic storage an untouched slot is an unconstrained word, so
///    `slot != attacker` would be satisfiable for the wrong reason (a false
///    positive). `P_STORAGE_CHANGED` is sound in both models because it compares
///    the same term before/after.
contract ProbeBaseA is Test {
    address internal constant USDC = 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48;
    address internal constant WETH = 0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2;
    address internal constant USDT = 0xdAC17F958D2ee523a2206206994597C13D831ec7;
    address internal constant DAI = 0x6B175474E89094C44Da98b954EedeAC495271d0F;
    address internal constant KONTROL_HEVM = 0x7109709ECfa91a80626fF3989D68f67F5b1DD12D;
    address internal constant KONTROL_CONSOLE = 0x000000000000000000636F6e736F6c652e6c6f67;

    /// The address the A9/A4 value controls hardcode for the consent token. The
    /// harness etches `ConsentToken` here in `setUp` so pre-built controls and the
    /// ABI-agnostic probes observe the same instrument.
    address internal constant CONSENT_TOKEN = 0x0000000000000000000000000000000000001111;

    /// Role used by the MUST_PASS controls. The attacker domain excludes it, so
    /// a correctly role-guarded contract can never be driven by the attacker.
    address internal constant ADMIN = address(0xA11CE);

    /// Slots 0..NSLOTS-1 are snapshotted/compared. 32 covers the common
    /// admin/implementation/accounting slots (stage 1-3 stopped at 15).
    uint256 internal constant NSLOTS = 32;

    // ConsentToken fixed layout (src/ConsentToken.sol).
    uint256 internal constant TK_TRANSFER_COUNT = 2;
    uint256 internal constant TK_LAST_FROM = 3;
    uint256 internal constant TK_LAST_TO = 4;

    address[4] internal TOKENS;

    // Per-token "before" snapshot of the three fixed slots. Index 4 is CONSENT_TOKEN.
    uint256[5] internal tkCount0;
    address[5] internal tkFrom0;
    address[5] internal tkTo0;

    // Per-target slot snapshot.
    bytes32[NSLOTS] internal slot0;

    function setUp() public virtual {
        TOKENS = [USDC, WETH, USDT, DAI];
        ConsentToken ct = new ConsentToken();
        bytes memory code = address(ct).code;
        for (uint256 i = 0; i < 4; ++i) {
            vm.etch(TOKENS[i], code);
            vm.store(TOKENS[i], bytes32(TK_TRANSFER_COUNT), bytes32(0));
            vm.store(TOKENS[i], bytes32(TK_LAST_FROM), bytes32(0));
            vm.store(TOKENS[i], bytes32(TK_LAST_TO), bytes32(0));
        }
        vm.etch(CONSENT_TOKEN, code);
        vm.store(CONSENT_TOKEN, bytes32(TK_TRANSFER_COUNT), bytes32(0));
        vm.store(CONSENT_TOKEN, bytes32(TK_LAST_FROM), bytes32(0));
        vm.store(CONSENT_TOKEN, bytes32(TK_LAST_TO), bytes32(0));
    }

    /// @dev Seed a concrete victim's balance and its allowance to `target` inside
    /// the etched `ConsentToken` (fixed layout: slot 0 balanceOf, slot 1 allowance).
    function _seedVictim(address victim, address target, uint256 bal, uint256 allow) internal {
        vm.store(CONSENT_TOKEN, keccak256(abi.encode(victim, uint256(0))), bytes32(bal));
        bytes32 inner = keccak256(abi.encode(victim, uint256(1)));
        vm.store(CONSENT_TOKEN, keccak256(abi.encode(target, inner)), bytes32(allow));
    }

    // ---------------------------------------------------------------- attacker
    /// @dev Kill the 3-way symbolic-address branching and the cheatcode FPs.
    /// `extra` lets a probe exclude extra addresses (victim, deployed mocks).
    function _assumeAttacker(address attacker, address target) internal view {
        vm.assume(attacker != address(0));
        vm.assume(uint256(uint160(attacker)) > 0xff);
        vm.assume(attacker != KONTROL_HEVM);
        vm.assume(attacker != KONTROL_CONSOLE);
        vm.assume(attacker != address(this));
        vm.assume(attacker != address(vm));
        vm.assume(attacker != target);
        vm.assume(attacker != ADMIN);
        for (uint256 i = 0; i < 4; ++i) vm.assume(attacker != TOKENS[i]);
    }

    /// @dev Variant that also excludes a concrete victim (A9).
    function _assumeAttackerVictim(address attacker, address target, address victim)
        internal
        view
    {
        _assumeAttacker(attacker, target);
        vm.assume(attacker != victim);
        vm.assume(victim != address(0));
    }

    // ------------------------------------------------------------- state model
    /// @dev Fast model, comparable with stages 1-3. `P_AUTH_WRITE` is valid here.
    function _seedZeroed(address target) internal {
        for (uint256 i = 0; i < NSLOTS; ++i) vm.store(target, bytes32(i), bytes32(0));
    }

    /// @dev Sound model: every untouched slot is symbolic, so any write (even a
    /// write of zero) changes the term and trips `P_STORAGE_CHANGED`. Under this
    /// model we do NOT assert `P_AUTH_WRITE` (see contract docs).
    function _seedSymbolic(address target) internal {
        vm.setArbitraryStorage(target);
    }

    function _snapshotTarget(address target) internal {
        for (uint256 i = 0; i < NSLOTS; ++i) slot0[i] = vm.load(target, bytes32(i));
    }

    function _snapshotTokens() internal {
        for (uint256 i = 0; i < 4; ++i) {
            tkCount0[i] = uint256(vm.load(TOKENS[i], bytes32(TK_TRANSFER_COUNT)));
            tkFrom0[i] = address(uint160(uint256(vm.load(TOKENS[i], bytes32(TK_LAST_FROM)))));
            tkTo0[i] = address(uint160(uint256(vm.load(TOKENS[i], bytes32(TK_LAST_TO)))));
        }
        tkCount0[4] = uint256(vm.load(CONSENT_TOKEN, bytes32(TK_TRANSFER_COUNT)));
        tkFrom0[4] = address(uint160(uint256(vm.load(CONSENT_TOKEN, bytes32(TK_LAST_FROM)))));
        tkTo0[4] = address(uint160(uint256(vm.load(CONSENT_TOKEN, bytes32(TK_LAST_TO)))));
    }

    // ------------------------------------------------------------------ checks
    /// @dev The real storage check, parameterised by target.
    function _checkTarget(address target, address attacker, bool zeroedModel) internal view {
        assertEq(target.balance, _bal0, "P_BALANCE_LOST");
        assertLe(attacker.balance, _atk0, "P_ATTACKER_PROFIT");
        for (uint256 i = 0; i < NSLOTS; ++i) {
            bytes32 cur = vm.load(target, bytes32(i));
            assertEq(uint256(cur), uint256(slot0[i]), "P_STORAGE_CHANGED");
            if (zeroedModel) {
                assertTrue(cur != bytes32(uint256(uint160(attacker))), "P_AUTH_WRITE");
            }
        }
        _checkTokens(attacker);
    }

    /// @dev Scoped check for value-carrying probes (A5): the target may
    /// legitimately write accounting, so only ETH conservation is asserted.
    function _checkValue(address target, address attacker) internal view {
        assertGe(target.balance, _bal0, "P_BALANCE_LOST");
        assertLe(attacker.balance, _atk0, "P_ATTACKER_PROFIT");
    }

    /// @dev No token transfer/transferFrom happened, and nothing was routed to
    /// the attacker. Keccak-free (fixed slots only).
    function _checkTokens(address attacker) internal view {
        bytes32 atk = bytes32(uint256(uint160(attacker)));
        for (uint256 i = 0; i < 4; ++i) {
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

    /// @dev A9: a concrete victim's tokens must not move (no transfer initiated
    /// from the victim) and the victim must never become the consent token's
    /// `lastFrom`. Observed on CONSENT_TOKEN itself (fixed slots, keccak-free).
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

    // ------------------------------------------------------------- bookkeeping
    uint256 internal _bal0;
    uint256 internal _atk0;

    function _markBalances(address target, address attacker) internal {
        _bal0 = target.balance;
        _atk0 = attacker.balance;
    }
}
