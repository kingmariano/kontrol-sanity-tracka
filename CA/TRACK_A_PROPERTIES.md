# Track A — property specification (light batch)

Companion to `VULN_CLASS_RESEARCH.md`. One subsection per stage: the exact
invariant, the probe template it needs, the mock(s), the must-FAIL / must-PASS
controls, and the known limitations. A stage is only promoted to a full matrix
after its controls hold (chunk 0 sanity).

Shared conventions:
- Every probe inherits `ProbeBase` (slots 0..15 snapshot, ETH, 4 etched tokens).
- `attacker` is symbolic and constrained: `!= 0`, `> 0xff`, `!= HEVM`,
  `!= console`, `!= target` (fixes `CHEATCODE_UNIMPLEMENTED`).
- Verdict rule: must-FAIL control → `PROOF FAILED`; must-PASS → `PROOF PASSED`.
- The proof is the real precision filter; scanners only produce candidates.

---

## A1 — unprotected initialize / reinitialize

- **Invariant:** for a symbolic `bytes4 selector` and symbolic args, an
  unauthenticated attacker call cannot change any tracked slot.
- **Template:** `SINGLE` (reuse — already validated by stage 1).
- **Mock:** none.
- **Property (asserted by ProbeBase, unchanged):**
  `P_STORAGE_CHANGED` (slots 0..15), `P_AUTH_WRITE`, `P_BALANCE_LOST`,
  `P_ATTACKER_PROFIT`, `P_TOKEN_*`.
- **Controls:**
  - `VulnerableInit` — `initialize(address owner)` writes `owner` (slot 0), no guard → must FAIL.
  - `SafeInit` — same body but `require(msg.sender == address(0))` (attacker != 0) → must PASS.
- **Limitation:** admin slots above 15 are not covered; guarded contracts are
  selected by the scanner but PASS the proof.

## A2 — unprotected upgrade / attacker-controlled DELEGATECALL

- **Invariant:** attacker calldata cannot set the implementation/admin slot to a
  value it controls.
- **Template:** `SINGLE` (reuse).
- **Mock:** none.
- **Property:** same suite as A1 (the impl-slot write trips `P_STORAGE_CHANGED`).
- **Controls:**
  - `VulnerableUpgrade` — `upgradeTo(address impl)` writes `impl` (slot 0), no guard → must FAIL.
  - `SafeUpgrade` — `require(msg.sender == address(0))` → must PASS.
- **Limitation:** proves the *slot write*, not that the delegatecall actually
  executes attacker code; the attacker-controlled-target form is a `MULTI`
  extension once a call-target monitor exists.

## A3 — signature / permit replay

- **Status: NOT a light-batch proof stage.** The zeroed-storage, ABI-agnostic
  harness cannot synthesise a valid signature, so a replay effect does not
  manifest (the proof would be vacuous — exactly the stage-3 failure mode).
- **Scanner only:** `scan_a3_replay.py` measures the candidate universe.
- **Promotion path (Track B):** a `SIGNER` template that uses `vm.sign` with a
  known key, builds the contract's EIP-712 digest, calls `permit`/`execute`
  twice, and asserts the second call cannot move more value. Requires the
  domain separator / typehash to be recoverable from bytecode (hard) or from a
  verified ABI.

## A4 — rounding / round-trip value conservation (near-empty vault)

> **Reclassified to Track B (2026-09-12).** The sweep found only 2,460 bytecodes /
> 2,655 deployments, and the *inflation* effect is inherently multi-party
> (front-run + donation + victim deposit) with symbolic-amount multiplication —
> heavy for the mass matrix, and a single-user round-trip test is vacuous (the
> attacker only harms themselves). Implement as a Track B per-target invariant.

- **Invariant:** for a symbolic deposit amount, `deposit` then immediately
  `redeem` cannot increase the caller's underlying-token balance; and a nonzero
  deposit cannot mint zero shares when `totalSupply > 0`.
- **Template:** `ROUNDTRIP` (new) — two sequential calls, token-balance delta.
- **Mock:** `ConsentToken` (real balances + allowances, instrumented slots).
  Setup: mint `victim` balance, `approve` the target, etch token.
- **Property:**
  ```
  uint256 a0 = token.balanceOf(attacker);
  // call deposit(x) then redeem(allShares)
  assertLe(token.balanceOf(attacker), a0, "P_ROUNDTRIP_LOSS");
  ```
  plus the ProbeBase suite.
- **Controls:**
  - `VulnerableVault` — naive first-depositor: shares = assets * supply /
    (balance + assets); a donation inflates the ratio → must FAIL.
  - `SafeVault` — virtual offset (`+1` share, `+1` asset) → must PASS.
- **Limitation:** donation is modeled as a direct `token.transfer(target, d)`
  before the deposit; requires the token mock retained by the target.

## A5 — multicall / batch `msg.value` reuse

- **Invariant:** a single `msg.value` cannot be credited more than once; attacker
  net ETH delta ≤ 0.
- **Template:** `VALUE` (new) — `target.call{value: v}(selector, args)` with
  `vm.deal(attacker, v)`; two subcalls inside.
- **Property:** `assertLe(attacker.balance, atk0)` where `atk0` is taken after
  funding, and `assertGe(target.balance, bal0)`.
- **Controls:**
  - `VulnerableMulticall` — `multicall` reuses `msg.value` for two credits → must FAIL.
  - `SafeMulticall` — credits `msg.value` once, tracks accounted value → must PASS.
- **Limitation:** encoding a real `bytes[]` batch in the ABI-agnostic probe is
  not possible; the control exposes a representative `pay(uint256)` pair. The
  scanner still measures the multicall universe.

## A6 — deflationary / fee-on-transfer / rebasing accounting

- **Invariant:** no accounting state can be advanced from a token balance that a
  third party can change between reads.
- **Template:** `SINGLE` (reuse) + a `FeeToken` mock whose `balanceOf` is backed
  by a settable slot (so donation is representable).
- **Property:** ProbeBase suite (`P_STORAGE_CHANGED` catches the credit write).
- **Controls:**
  - `VulnerableFee` — `sync()` sets `accounted = token.balanceOf(this)` to a
    manipulable value → must FAIL.
  - `SafeFee` — caches the reserve and never re-reads mid-flow → must PASS.
- **Limitation:** the mock must expose `balanceOf` from storage; the current
  `MockERC20` does not (needs `FeeToken`).

## A7 — unchecked external call / calldata-derived call target

- **Invariant:** no storage advance occurs when the external call fails.
- **Template:** `SINGLE` (reuse) — the call itself is the probe call; the control
  performs an unchecked inner call.
- **Property:** ProbeBase suite.
- **Controls:**
  - `VulnerableUnchecked` — `(bool ok,) = to.call(...); credited += amt;` ignores
    `ok` → must FAIL.
  - `SafeUnchecked` — `require(ok, "call")` before `credited += amt` → must PASS.
- **Limitation:** proves the state advance, not the failure semantics directly.

## A8 — hostile callback accounting

> **Reclassified to Track B (2026-09-12).** A symbolic attacker is an EOA and
> cannot execute a reentry; a real callback needs a *concrete, etched* contract
> that the target actually calls during its operation (token hook, flash-loan
> callback). That is a per-target modeled counterparty, not an ABI-agnostic
> sweep, so it belongs in the curated Track B set.

- **Invariant:** during a callback, re-entering the target with an arbitrary
  selector cannot exceed the caller's entitlement.
- **Template:** `REENTRANT` (new) — a mock callback contract re-enters the
  target with a symbolic selector while the target is mid-operation.
- **Mock:** `ReentrantMock` (implements a hook; on invocation calls back).
- **Property:** ProbeBase suite on the target + attacker value delta.
- **Controls:**
  - `VulnerableCallback` — updates `totalAssets` after the callback → must FAIL.
  - `SafeCallback` — updates before the callback (CEI) → must PASS.
- **Limitation:** needs `expectCall` (kontrol-cheatcodes) to force the hook;
  heavier than the reuse stages.

## A9 — unauthenticated pull / attacker-named payer (approval siphoning)

- **Invariant:** a symbolic attacker naming a victim (who has only `approve`d the
  target) as `solver`/`from` cannot move the victim's tokens. Formally: for a
  concrete victim with a concrete allowance to the target, and a symbolic
  attacker caller, `token.balanceOf(victim)` must be unchanged, and the token's
  `lastFrom` must not be the victim.
- **Template:** `UNAUTH_PULL` (new). Setup:
  ```
  vm.etch(TOKEN, CONSENT_TOKEN);
  vm.deal(target, 1 ether);
  // balances[victim] = 1e18 ; allowance[victim][target] = 1e18 (vm.store)
  // attacker is symbolic, victim is concrete
  vm.prank(attacker); target.call(abi.encodeWithSelector(selector, victim, amt));
  ```
- **Property:**
  ```
  assertEq(token.balanceOf(victim), VICTIM_BAL, "P_UNAUTH_PULL");
  assertTrue(lastFrom(token) != victim, "P_UNAUTH_PULL_FROM");
  ```
- **Controls:**
  - `VulnerablePull` — `pull(address solver, uint256 amt)` does
    `token.transferFrom(solver, msg.sender, amt)` with no `solver` consent check
    → must FAIL.
  - `SafePull` — `require(solver == msg.sender, "consent")` → must PASS.
- **Reference:** ExVul 2026-09-11, ether.fi Liquid / Veda `AtomicQueue.solve`
  (`safeTransferFrom(solver, user, amount)` with caller-supplied `solver`).
- **Limitation:** `from == CALLER`-guarded contracts are excluded by the proof,
  not the scanner; `ConsentToken` embedded runtime must be pinned like
  `MockERC20`.

---

## Light-batch batching

| Batch | Stages | Template work | Status |
|---|---|---|---|
| **1** | A1, A2, A6, A7 | none (reuse `SINGLE` + controls) | sanity run queued |
| **2** | A9 | `UNAUTH_PULL` + `ConsentToken` | sanity run queued |
| **3** | A5 | `VALUE` | sanity run queued |
| **—** | A3 | signer template | Track B (not sweepable) |
| **—** | A4 | multi-party inflation, symbolic-amount mul | Track B (round-trip-only is vacuous) |
| **—** | A8 | needs a concrete etched callback counterparty | Track B |

**Track A sweepable set is therefore A1, A2, A5, A6, A7, A9** (six stages);
A3/A4/A8 join the curated Track B queue.

Scanner yield (unique bytecodes / deployments matching, metadata-stripped):
A1 39,130 / 475,534 · A2 18,031 / 1,605,663 · A3 18,990 / 435,167 ·
A4 2,460 / 2,655 · A5 4,260 / 5,482 · A6 73,429 / 95,500 ·
A7 96,800 / 8,629,770 · A8 25,435 / 47,336 · A9 9,828 / 14,621.
