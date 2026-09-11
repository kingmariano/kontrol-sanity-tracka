# Live-Gate Re-Check — F4, F5, F6, F7, F8 (2026-09-11)

**Trigger:** the F9 reversal (`FINDING_9_S2-38.md`): a zeroed-storage Kontrol
proof is a *reachability* result, not a *live-exploitability* result. This re-runs
the live test for every multi-instance balance/authority finding by:

1. disassembling each family's runtime bytecode and locating the value-moving path;
2. identifying its guard (a storage slot or a hardcoded/branch address);
3. reading that guard on **every funded instance** via `eth_getStorageAt` and
   confirming code presence via `eth_getCode`;
4. simulating the exploit with `eth_call` where useful.

Tooling: Alchemy `eth_getStorageAt`/`eth_getCode`/`eth_call` (paced, retried).
Artifacts: `poc/test/F8Live.t.sol`, `poc/test/F9Drain.t.sol` (8/8 pass with
`MAINNET_RPC_URL` set).

## Results

| Family | Value path | Guard | Funded instances | Guard state on live | Verdict |
|---|---|---|---|---|---|
| **F4** | proxy `initialize(address,bytes)` 0xd1f57894 → `SSTORE slot0 = impl` | `sload(0) == 0` | 873 (ETH or USDC) | **873/873 `slot0 != 0`** (all initialized) | **NOT exploitable** |
| **F5** | `setSpender(address)` 0x44439209 → `SSTORE` | `CALLER == 0x65b0bf8ee4947edd2a500d74e50a3d757dc79de0` (hardcoded) | 2 dust (~0.011 ETH) | gate is a constant; funds dust | **NOT exploitable** |
| **F6** | `flush()` 0x6b9f96ea + CALL paths | (not reached) | **0** | n/a | **dormant** |
| **F7** | `flush()` 0x6b9f96ea → `CALL(destinationAddress(), BALANCE)` | **none** (permissionless) | **0** | pays constructor-set `slot0` destination, not caller | **dormant / not profitable** |
| **F8** | `init(address)` 0x19ab453c → `SSTORE slot1 = factory`, then factory-gated `recycle(address[])` 0x724c6ddc pays `SELFBALANCE` | `sload(1) == 0` | 9 (8 code + 47 USDC flagship) | **8/8 code-bearing instances `slot1 != 0`; 9th has zero code** | **NOT exploitable; 47 USDC safe** |

## Per-family detail

### F4 — SmartAccountProxy / Gnosis-Safe-style proxy (`0x1cf5a0fe…`, 850 B, 1,352 deploys)
- Dispatcher: `masterCopy()` 0xa619486e (returns `sload(0)`); `initialize` 0xd1f57894;
  fallback → `DELEGATECALL(sload(0))`.
- `initialize` reverts `"Initialized already"` unless `sload(0) == 0`, then writes
  `slot0 = impl` and delegatecalls. This is the Stage-1 P1 "unprotected sstore" hit.
- **Live:** 873/873 funded (103 USDC + 818 ETH-funded) have `slot0 != 0`. No proxy is
  uninitialized → the write is unreachable. (The kore crash was a symbolic
  `ecrecover` inside the *delegate*, not on the proxy's surface.)
- Note: no `CALLER` opcode in the proxy bytecode at all.

### F5 — `setSpender` (`0xa24e966a…`, 737 B, 4,374 deploys)
- `0x44439209` → body at 0x123 begins `CALLER; PUSH20 0x65b0bf8e…; EQ; JUMPI; REVERT`.
  The write is gated to a **hardcoded owner address**, not an arbitrary caller.
- Only 2 funded instances, ~0.011 ETH combined (dust). No live impact.

### F6 (`0x6f83343a…`, 1,776 B, 3,004 deploys) & F7 (`0x3b7d6f59…`, 626 B, 2,116 deploys)
- Both censused **0 ETH, 0 USDC**. F7's `flush()` is genuinely permissionless but
  forwards the balance to `destinationAddress()` (`slot0`, set at construction), so
  it is a sweep-to-owner, not an attacker payout.
- The `sig_transient` detection that put these in the Stage-2 pool is contaminated
  (see §Metadata below).

### F8 — Ownable proxy (`0x1aba7e71…`, 1,930 B, 971 deploys)
- `init(address)` 0x19ab453c requires `sload(1) == 0`; `recycle(address[])`
  0x724c6ddc requires `CALLER == sload(1)` and pays `SELFBALANCE` to caller-chosen
  addresses; `factory()` 0xc45a0155 returns `sload(1)`.
- **Live scan of the 9 funded entries:**
  - 8 carry the full 1,930-byte code and have `slot0=1`, `slot1 = e39c37e7… or
    d50d290a…` (protocol factories) → `init` reverts, `recycle` is factory-only.
  - The flagship `0x3952fe74…` (47 USDC) is one of the 8 → **safe**.
  - The 9th, `0xd1c68218…` (0.01 ETH), has **`eth_getCode == 0x`** — an empty
    account. Its `slot1=0` is meaningless; `eth_call init` "succeeds" only because
    there is no code to revert. The census recorded it as a deployment; on-chain it
    is codeless. **Not exploitable.**
- `poc/test/F8Live.t.sol` asserts all of the above on a mainnet fork (3/3 pass).

## Methodology lessons (add to the ledger)

1. **Reachability ≠ live risk.** Always read the guard slot(s) the proof implicitly
   fixed (F9 `slot5`; F4 `slot0`; F8 `slot1`) on the real funded instances before
   claiming funds at risk.
2. **Check code presence.** A funded address can be codeless (contract self-destructed,
   never deployed, address collision, or census artifact). `eth_getCode` must be part
   of triage — `slot == 0` on a codeless account is not an "uninitialized contract".
3. **`sig_transient` is contaminated by compiler metadata.** F5–F8 each contain
   `0x5c`/`0x5d` bytes inside the solc metadata trailer (`a165627a7a72305820…` /
   `a264697066735822…64736f6c63…`) and inside `PUSH` immediates. The push-aware scan
   still decodes metadata as code, so "TSTORE/TLOAD present" fired on contracts with
   **no transient storage at all**. The Stage-2 "SIR-shape" pool should be re-filtered
   by stripping the metadata trailer before opcode scanning.
4. **Hardcoded-address gates** (F5) are invisible to the P1 "written value == symbolic
   caller" property; the write is safe but the probe still flagged it under the
   two-phase/zeroed model. Classify these as false positives.

## Bottom line

**None of F4, F5, F6, F7, F8 has a live-exploitable permissionless drain on any
funded instance.** The campaign's only "live funds at risk" claims were:
F9 (7.787 ETH) — rejected (`FINDING_9_S2-38.md`);
F4 (2,112 USDC + 5.57 ETH) — rejected (all initialized);
F8 (47 USDC) — rejected (all initialized). F6/F7 are dormant; F5 is dust and gated.
