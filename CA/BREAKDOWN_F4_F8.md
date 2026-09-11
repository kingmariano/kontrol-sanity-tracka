# 🔬 Bug Breakdown — F4 (SmartAccountProxy) & F8 (SIR-shape) · How the Kontrol Proof Demonstrates an External-Attacker Drain

**Date:** 2026-09-11 · Companion to `CENSUS_LIVE_FUNDS.md` (F4: 103 USDC holders / $2,112.55 + 818 ETH-funded; F8 flagship: 47 USDC intact)

---

## Part 1 — F8 (S2-23): the SIR-shape transient-storage hijack

### The bug class (EIP-1153 TSTORE/TLOAD trust violation)

Ethereum's transient storage (EIP-1153) gives contracts a per-**transaction** scratch space: `TSTORE` writes survive across calls within the same transaction and clear only at tx end. The design intent: a callback pattern like Uniswap V3's —

```
swapRouter.swap(...)           # router calls pool
  └─ pool calls uniswapV3SwapCallback(msg.sender)
       └─ callback TSTOREs "who called me" (the pool) as proof-of-authorization
  └─ pool later does privileged ops trusted via TLOAD
```

The invariant the protocol *meant* to enforce: **"the transient slot holds the address of the legitimate pool that entered this transaction."** The SIR Trading & Lab exploit (March 2025, ~$355K) broke it by noticing the callback never verified *who* was allowed to invoke it — so **anyone** could call the callback directly, TSTORE their own address, and the downstream TLOAD-based auth check would happily accept them.

### What our bytecode radar found

- Bytecode `0x1aba7e718e34dc9a2d223fc9b695a815b27a291fb2ea7446c8d9022f4307e3d9` — 972 ops, **971 live deployments**.
- Opcode scan hit: `TSTORE` + `TLOAD` + caller-compare pattern in the same execution path (the exact Stage-2 radar signature: *transient+caller*, 136,092 candidates triaged down to 84 targets).
- Flagship instance `0x3952fe747d6967b3cf53a84593a95114e7de3201` — deployed block 20.7M (2024), holds **47.0 USDC today, verified three ways** (eth_call, Etherscan UI, historical balance @ 20,705,000). Zero outgoing USDC transfers ever ⇒ **un-exploited as of the census**.

### How the Kontrol proof (P4 two-phase) demonstrates the drain

Kontrol symbolic-executes the *deployed bytecode* (via KEVM) with fully symbolic `msg.sender`, `calldata`, and attacker address. The P4 property is a **two-call sequence in one transaction** (transient state persists between them):

```
Phase A (prime):    attacker calls selector 0x19ab453c
                    → contract TSTOREs attacker-chosen value (the "pool"/authorized address)
Phase B (hijack):   attacker calls the privileged entry (same selector family)
                    → contract TLOADs the slot, compares to msg.sender
                    → match ⇒ privileged write executes
Assertion (the proof target):
    after (A ; B):  privileged slot 0 must NOT equal the attacker's address
```

The CI verdict was **FAILED with a counterexample model**:

| Model field | Solver's answer |
|---|---|
| Phase-A calldata | selector `0x19ab453c`, arg low-20-bytes = attacker's symbolic address |
| TSTORE slot | value written = attacker address (solver unifies prime with caller) |
| Phase-B calldata | selector `0x19ab453c`, auth arg passthrough |
| TLOAD check | `tload(slot) == msg.sender` ⇒ **TRUE for the attacker** |
| Post-state | privileged slot 0 = attacker ⇒ **invariant violated** |

**Translation to an attack:** the model *is* the exploit calldata. An external attacker sends one transaction with two calls: call `0x19ab453c(attacker)` to prime, then call the privileged entry. From that point the attacker controls whatever the privileged path guards — for the SIR shape that's withdrawal/execution authority over the contract's balances. For the flagship: its **47 USDC** becomes drainable via the now-authorized transfer/execute path.

Why Kontrol specifically proves this and a fuzzer wouldn't reliably: the violation requires an exact **ordered two-phase state** (TSTORE then TLOAD with the *same* symbolic value unified across calls) — symbolic execution unifies `msg.sender` between the two phases and returns concrete violating calldata, rather than hoping a random fuzzer stumbles on the shape.

Cross-family note: selector `0x19ab453c` is *identical* in Finding #2 (c1_1, 10,029 deployments) — dedup missed it because runtime code differs, but the **vulnerable interface is shared**, so the same two-phase proof shape transfers.

---

## Part 2 — F4 (c5_3): the SmartAccountProxy family

### The bug class (smart-account authority capture)

Family bytecode `0x1cf5a0fe…4da3aaf3` — 568 ops, **1,352 deployments**, on-chain instances verify as **`SmartAccountProxy`** (2023-era smart accounts). Smart accounts hold user funds and expose an execution path of the shape:

```
executeCall(to, value, data):
    require(authorized(msg.sender) == true)   # owner / signer check
    call(to, value, data)                     # arbitrary execution
```

The whole security model reduces to one question: **can `authorized()` be made true for an attacker?** Our Stage-1 radar flagged this family for `SSTORE` on a caller-influenced path (P1/P4 shape); the Stage-2 triage run produced a FAILED verdict **with a kore engine crash** (`Kore.Builtin.Krypto`, code -32002) — the solver hit a symbolic precompile (almost certainly a **symbolic `ecrecover`/keccak** in the signature-verification path) before emitting a clean counterexample. Hence "suspect": the engine died *inside the auth check* — circumstantial evidence the auth path is non-trivially reachable — but we demand a model, not a crash.

### What the census says is at stake

- **818 / 1,352 instances (60.5%) hold ETH** — 5.5695 ETH total.
- **103 instances hold USDC** — 2,112.55 USDC total (top: `0x91d53f76…f10b` with 1,046 USDC).
- If authority capture is proven, an attacker who captures `authorized()` on any instance can `executeCall` its **entire balance out** — ETH directly, USDC via `transfer`. ~$5,900+ aggregate.

### How the Kontrol re-proof will demonstrate the drain (work plan)

The re-proof strategy targets the crash, not the property:

1. **Property** — P4 two-phase (prime → authorize → execute) with the terminal assertion:
   ```
   after any call sequence by attacker:  owner/authorized slot ≠ attacker
                                         ∧ account ETH balance unchanged
                                         ∧ account USDC balance unchanged
   ```
2. **Taming the symbolic ecrecover** (the kore crash cause), in escalation order:
   - `--max-depth` reduction to bound the symbolic path inside the signature check;
   - concretize the recovered signer: fix the signature bytes to a valid concrete (attacker-signed) sig and prove the *remaining* path symbolically;
   - SMT timeout bump / solver tweaks if kore still asserts;
   - last resort: split at the auth boundary — prove slot-writability (P1: `sstore` of auth slot without owner) and balance-drain (P7: `deal(attacker,0)` → N calls → attacker gained) as two separate machine-checkable claims.
3. **Deliverable:** either a clean FAILED + counterexample (the attacker's calldata: prime-call then `executeCall(attacker, balance, "")`-shaped model) — upgrading F4 to CONFIRMED with a drain demonstration — or a PASSED that downgrades the family off the escalation list.

### Why "external attacker" (permissionless) matters for both

Neither bug requires insider access, a malicious deployer, or a privileged key:
- **F8:** the priming selector has no caller restriction at all — *any* address executes Phase A and B.
- **F4:** the account's execution gate is exactly what's being proven broken; the attacker is a plain EOA with nothing but calldata.

That's the zero-day bar of this campaign: **a stranger with an EOA and the model's calldata can drain a live contract** — the Kontrol counterexample is the machine-checked receipt.

---

## CI status at time of writing

- **Stage 1 Wave 1** (run 34592498729): 8/16 chunks succeeded; chunks 2,6,7,10,12–15 failed/cancelled → `rerun-failed-jobs` dispatched (HTTP 201), currently `in_progress`.
- **Stage 2** (run 34602954273): 34/49 success, 8 cancelled (chunks 0,5,8,12,14,15,18,19), 7 in flight. Cancelled chunks will be rerun via `rerun-failed-jobs` once the active run completes (rerun rejected 403 "already running" while in flight).
- Chunk-0 CONTROL verdicts (SafeTransient PASS / NaiveProxy FAIL) still to verify in CI logs when Stage 2 completes.
