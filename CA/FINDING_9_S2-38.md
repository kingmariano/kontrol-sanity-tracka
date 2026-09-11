# Finding #9 (S2-38) — F9 family: proof vs. live reality ⚠️ CORRECTED

**Date:** 2026-09-11 (correction by next agent) · **Status:** property violation
CONFIRMED in the zeroed-storage model · **live exploitability: REJECTED**

- **Bytecode:** `0x8824fcf9d1571b0d30d734c29b728e282437ef12747696a848581c112a971c8a`
- **Family:** wild `transient_caller` radar pool — **376 deployments**
- **Original ledger claim:** "CONFIRMED full ETH drain, 194/376 funded, 7.787 ETH
  (~$36.6K), prime=0 trivial two-call sequence" — top of the escalation queue.

This document records why that claim does **not** survive contact with live state,
with machine-checked evidence in `CA/poc/`.

---

## 1. What the Kontrol proof actually proved

The Stage-2 chunk 38 test (`harness/generated2/Stage2Chunk_38.sol`,
`test_p4_w39`) etched the runtime bytecode, **zeroed storage slots 0..7**,
dealt 1 ETH, then made two calls from the attacker:

```
Phase A: 0x05b34410(prime=0)   // the slot-1 getter — a no-op
Phase B: 0x0b5ab3d5            // the sweep
assert target.balance == 1 ether   -> FAILED (balance became 0)
```

The `P4-SD-AFTER-PRIME` assertion fired. That is a genuine counterexample **for
the harness state** (slots zeroed). It is not a two-phase/transient bug at all —
Phase A is the read-only getter `sload(1)`, and the drain is a single call.

## 2. Disassembly (1142-byte runtime, selector → slot map)

| Selector | Auth | Effect |
|---|---|---|
| `0x05b34410` | none | returns `sload(1)` (getter) |
| `0x0b5ab3d5` | **none** | `if (sload(5) & 0xff == 0) call(sload(2), selfbalance)`; then selfdestruct(0xdead) |
| `0x13af4035` | owner (`sload(0)==caller`) | writes `slot2` and `slot3` (recipient fields) |
| `0x2b20e397` | none | returns `sload(0)` (owner) |
| `0x3fa4f245` | none | returns `sload(4)` |
| `0x674f220f` | none | returns `sload(3)` |
| `0x8da5cb5b` | none | returns `sload(2)` (recipient) |
| `0xbbe42771` | owner | requires `slot5 != 0`; clears `slot5` low byte; payout |
| `0xfaab9d39` | owner | transferOwnership (`slot0 = arg`) |
| `0xfb1669ca` | owner | requires `slot5 != 0`, `arg < slot4`; sets `slot4`; payout |

The **only** value-moving path reachable without the owner is `0x0b5ab3d5`, and it
is gated by **`slot5 & 0xff == 0`**. When `slot5 != 0` the code executes
`PUSH2 0x0000; JUMP` — a jump to offset `0x0`, which is **not a JUMPDEST** →
`InvalidJump` revert. There is no instruction anywhere in the runtime that writes
`slot5 = 1`; it must be set by the (unavailable) constructor init-code. Only the
owner-gated `0xbbe42771` clears it.

## 3. Live-state scan (all 376 instances, Alchemy `eth_getStorageAt`)

| `slot5 & 0xff` | Instances | ETH-funded |
|---|---:|---:|
| `0` | 182 | **0** |
| `1` | 194 | **194** |

Perfect inverse correlation: **every funded instance has `slot5 = 1`; every
`slot5 = 0` instance is empty.** The proven precondition (`slot5 == 0`) is
therefore unreachable on any live funded instance.

`eth_call` of `0x0b5ab3d5` against funded instances:

```
0xbce51130…02b5 (0.2 ETH, slot5=1) -> EVM error: InvalidJump
0x4d7abff0…079f (0.1 ETH, slot5=1) -> EVM error: InvalidJump
0x3fe9a9fe…e876 (0.012 ETH, slot5=1) -> EVM error: InvalidJump
```

Causality (`eth_call` with a `slot5=0` state override on the same instance):
**succeeds**. So the bytecode is exactly as disassembled — the gate is the only
obstacle, and it is set on every funded instance.

## 4. Even if the gate were cleared, the attacker is not the payee

`0x0b5ab3d5` pays `sload(2)`, not `msg.sender`. Distinct `slot2` across funded
instances:

```
0x5fc8a61e097c118ce43d200b3c4dcf726cf783a9  (182 instances)  EOA, nonce 456
0x4811e6996291cd78b9f9272ead30da18774db174  (7)               EOA, nonce 1105
0x0000000000000000000000000000000000000000  (4)               burns
0x5c19cf6b507c0efaa2680d1273d2529cc0bda1e6  (1)               EOA, 7.6 ETH, nonce 22
```

`slot2` is set only by the owner-gated `0x13af4035`. The owner (`slot0` =
`0x012233b3c8177f0778d910ed88170b82de3bfe57`, a 8342-byte contract, nonce 377)
is a fixed protocol contract unrelated to the attacker. So even a hypothetical
`slot5=0` sweep would route principal to a third party, not the caller.

## 5. Machine-checked PoC — `CA/poc/`

`poc/test/F9Drain.t.sol` (forge 1.8.1), all 5 tests pass:

| Test | Meaning | Result |
|---|---|---|
| `test_A_harness_model_drains_when_slot5_zero` | etch + zero slots (the Kontrol state) → 1 ETH drains to `slot2` | PASS |
| `test_A2_harness_model_with_zero_recipient_burns_funds` | same with `slot2=0` → burns to `address(0)`, attacker gets 0 | PASS |
| `test_B_live_instance_slot5_blocks_public_drain` | mainnet fork, `0x3fe9a9fe…` → sweep reverts, balance unchanged | PASS |
| `test_B2_live_2eth_instance_gated` | mainnet fork, `0xb76af7de…` (2 ETH) → gated | PASS |
| `test_C_forcing_slot5_zero_drains_to_slot2_not_attacker` | fork + force `slot5=0` → drains to `slot2` EOA, attacker gets 0 | PASS |

Run:
```bash
cd CA/poc
forge test                                   # A/A2 only (fork tests self-skip)
MAINNET_RPC_URL=<url> forge test             # all 5
```

## 6. Verdict

- **Property violation:** yes, mechanically — the generic (slot5=0) model drains.
- **Permissionless zero-day:** **no.** No funded instance is in the required
  state, the attacker cannot move any instance into it (all writers of `slot5`
  are owner-gated / constructor), and the payout address is a third party.
- **Corrected disposition:** F9 moves off the top of the escalation queue;
  reclassify from "CONFIRMED, full ETH drain, ~$36.6K" to
  **"property violation under favourable state; live-gated; not attacker-profitable."**
- **Methodology lesson (add to the ledger):** a zeroed-storage Kontrol proof is a
  *reachability* result, not a *live-exploitability* result. Before any "live
  funds at risk" claim, read the guard slot(s) on the real instances (here:
  `slot5`) and confirm the attacker can reach the proving state. Apply this to
  every balance-drain finding (F4/F6/F7/F8).
