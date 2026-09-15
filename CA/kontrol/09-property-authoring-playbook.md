# 09 — Playbook: writing properties that PROVE and that FIND real drains

Goal for a security audit: **no false positives, no false negatives** on *permissionless fund drains*.
A property that proves vacuously, or that silently skips the vulnerable code, is worse than useless.

## 9.1 Four property shapes (use all of them per surface)
1. **Goal / attacker-profit (strongest for drains).**
   For any permissionless entry point, the *caller's* net value cannot increase at the protocol's
   expense:
   ```
   uint256 before = usr.balanceOf(attacker) + token.balanceOf(attacker);
   vm.prank(attacker); target.somePublic(amountMaybe);
   assertLe(usr.balanceOf(attacker)+token.balanceOf(attacker), before, "attacker profited");
   ```
   With a symbolic `attacker = vm.randomAddress()` (constrained `!=` test/vm/known accounts) and
   symbolic amounts. This is the only shape that directly captures "drain".
2. **Conservation / invariant.** Protocol holdings ≥ Σ user entitlements; total supply accounting;
   `totalAssets == token.balanceOf(vault)`. Good for catching desync, but *conservation ≠ no-profit*:
   always pair with (1).
3. **Transition / exactly-once / state-machine.** e.g. a request can complete once, no double-spend,
   no replay of an idempotency key.
4. **Guard / negative.** Access control and input validation (only-Role, paused, stale price,
   zero-amount) — asserted via `vm.expectRevert()`. **Make sure the call actually reaches the guard**
   (a zero-address/artifact revert "passes" for the wrong reason — see 8.2).

## 9.2 Make the property non-vacuous
- The preconditions must be **satisfiable** and must put the system in a **non-degenerate state**
  (funded, roles granted, non-zero balances). A revert on a degenerate state can masquerade as a pass.
- Verify the code path is actually reached: after fixing 8.2, suites that previously reverted on
  `_mint(0)` started *passing* — proof the body is now executed.
- Guard against "returns early": e.g. `if (previewDeposit(x)==0) return;` then asserting — the
  assertion is vacuous on the taken branch. Assert the branch condition explicitly or split.

## 9.3 Modelling the attacker & environment
- Caller: `address attacker = vm.randomAddress();` then
  `vm.assume(attacker != address(this)); vm.assume(attacker != address(vm)); vm.assume(attacker != address(target)); …`
  to kill the 3-way symbolic-address branching (file 08.5) and focus the proof.
- Amounts: symbolic (fuzz arg or `vm.freshUInt(256,"amount")`). **Constrain with `vm.assume`,
  never `bound`.** Include both small and large ranges; avoid only-degenerate domains.
- Time: `vm.warp` to realistic timestamps; use symbolic blocks for time-dependent logic (boost,
  cooldowns, rate resets) rather than one fixed value, unless the property is time-specific.
- Pre-existing storage: `vm.setArbitraryStorage(addr)` (alias `symbolicStorage`) when the code reads
  state you don't otherwise set up; then constrain what's realistic.

## 9.4 Multi-step / stateful drains
- A single-function proof cannot see a drain that needs a sequence (approve→call, deposit→donate→
  withdraw, wrap→unwrap, request→complete). Options:
  - **BMC**: `--bmc-depth n` to unroll a bounded action sequence.
  - **Explicit sequence in one test**: perform the setup + attack in the same `test_*` and assert the
    end-state goal. This is usually the most effective for audit properties.
  - **Per-function properties + a global invariant property** that re-checks the invariant after each
    op.
- For reentrancy, use a malicious token/callback mock that re-enters the target and assert no gain.

## 9.5 Avoid known false negatives
- **Mocks ≠ real code.** Free-mint mocks hide real role gating (8.6). For a token-critical property,
  model the real token (or fork) or explicitly state the trust assumption.
- **Only asserting reverts** for negative properties can pass for the wrong reason; also assert the
  post-state (no value moved).
- **Under-specified attacker**: if the attacker is a fixed address or has no tokens, the proof is
  vacuous.
- **Uncovered surfaces**: enumerate the full permissionless entry-point list first, then write one
  goal-property per entry point. If an entry point has no property, it is a *documented gap*, not a pass.
- **Mocked externals (endpoints, oracles, treasury)**: if the mock no-ops authenticity (e.g. a
  LayerZero endpoint mock that accepts any `lzReceive`), the proof says nothing about spoofing. Mark
  it and, if it matters, write a separate property over the real interface/assumption.

## 9.6 Practical hygiene
- One property per test function; small and focused.
- Name symbolic variables (`vm.freshUInt(256, "amount")`) so counterexamples are readable.
- Snapshot `before` balances immediately before the action; assert deltas, not absolutes.
- Use `assertLe(a, b, "message")` style; the message shows in the failure reason.
- Prefer `uint256` non-degenerate domains; if the contract legitimately reverts for tiny inputs,
  encode the contract's real minimum in the `vm.assume` (and note it) — but first confirm the revert
  is the contract's and not an artifact (8.2/8.4).
- After a fix, **re-run CI**; do not trust local `forge test` alone (it uses different initial-state
  semantics, which is exactly why 8.2 was invisible locally).

## 9.7 Per-entry-point checklist (for a protocol like Resolv)
For every *permissionless* function (no role required), ask:
1. Can it mint (new supply) or unlock/burn-from someone else?
2. Can it move value to an attacker-chosen address?
3. Can it change a share/exchange rate in the attacker's favour (donation, rounding, first-depositor)?
4. Can it replay (idempotency key, signature, nonce)?
5. Can it re-enter (malicious token/callback)?
6. Can it grief (block withdrawal/claim, force revert) — DoS, still a finding if funds lock.
7. Can it bypass blacklist/pause/limits/cooldown?
8. Can it desync accounting (totalAssets/totalSupply/effective balances/reward indexes)?
9. Cross-contract: can calling A make B send value (allowance/coordinator paths)?
10. Initialization/upgrade: can a third party initialize or re-initialize a proxy/impl?
Then write shape-(1) goal properties for each "yes".
