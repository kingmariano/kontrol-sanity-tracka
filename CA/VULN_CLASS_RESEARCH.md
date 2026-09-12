# Vulnerability Class Research — Kontrol Matrix Expansion

- **Status:** research only. No pipeline/MATRIX change has been made for anything below.
- **Date:** 2026-09-12
- **Context:** current pipeline is v5 (stage 1–3 full matrices running on `2fd96e8`):
  metadata-stripped radar, `ProbeBase` (slots 0..15 + 4 etched ERC-20s), templates
  `SINGLE / TWO_PHASE / PROXY / MULTI`, controls as chunk 0.
- **Purpose:** decide what to add to the *mass sweep* (Track A / light batch) and
  what to explicitly refuse, so Kontrol budget is spent only on permissionless,
  state-dependent, high-novelty classes.

---

## 0. The framing that decides everything: two tracks

The word "vulnerability" hides two different proof problems. Only one scales to
the 69.8M-deployment universe.

| | **Track A — mass sweep (light batch)** | **Track B — curated invariants** |
|---|---|---|
| Unit | one deployed bytecode | a wired system of 2–10 contracts |
| Interface | ABI-agnostic symbolic selector + args | named functions, known roles |
| Sequence | 1–3 attacker calls | 3–10 ordered transitions |
| Property | self-contained (value/state cannot move) | economic (profit ≤ entitlement, desync) |
| Reach | all 69.8M deployments | dozens, chosen by radar |
| Empirical cost | min → ~4h per full pass | days per harness |

Kontrol does **not** run against mainnet state (no fork cheatcodes in our setup).
Any Track B dependency must be `vm.etch`-ed or stubbed, which is exactly why
Track B cannot be a mass sweep. The list below is split accordingly.

> **Not a Kontrol capability limit.** Kontrol is *designed* to prove these
> stateful invariants. Track B is kept out of the light-batch mass workflow for
> two operational reasons: (1) each invariant requires a hand-built, per-target
> harness (named functions, etched counterparties), so it cannot be
> auto-generated from the 69.8M-bytecode universe; (2) cost — a passing 3-call
> control already took 4h12m, and a 3–10 transition multi-contract invariant is
> far heavier, so it must run in a **separate low-parallelism Track B CI**, not
> inside the 20-way matrix. Every Track B item below *is* provable in Kontrol.

---

## 1. ADD — next light-batch (Track A) stages

These are thoroughly researched, permissionless, self-contained, and expressible
against a single bytecode. They are **not** currently in the matrix.

| ID | Vulnerability class | Evidence / taxonomy | Radar signal required | Property proved | Template | Priority |
|---|---|---|---|---|---|---|
| **A1** | **Unprotected initialize / reinitialize** (permissionless takeover) | OWASP SC10 (2026), SC01 | selector `initialize(...)`, `reinitialize`, `__init` + `SSTORE` + no caller gate | attacker calldata cannot set an admin/owner slot or flip the initialized flag | `SINGLE` | **P0** |
| **A2** | **Unprotected upgrade / attacker-controlled DELEGATECALL** | OWASP SC10 (2026) | `upgradeTo` 0x3659cfe6, `upgradeToAndCall` 0x4f1ef286, `setImplementation`, `changeAdmin` + `DELEGATECALL` | no DELEGATECALL whose target is calldata/attacker-derived; impl/admin slot cannot be attacker-set | `SINGLE` / `MULTI` | **P0** |
| **A3** | **Signature / permit replay** | OWASP SC05; scsfg signature attacks | `ecrecover` staticcall + selectors `permit`, `transferWithSig`, `execute` | two calls with **identical** symbolic args cannot move value twice; nonce must advance | `MULTI` (replay variant) | **P0** |
| **A4** | **Rounding / round-trip value conservation** (near-empty market, self-contained form) | OWASP SC07 (new 2026); OZ 2025 rewind (zkLend, ResupplyFi) | ERC-4626/vault selectors: `deposit`, `mint`, `withdraw`, `redeem`, `convertToShares/Assets`, `preview*`, `getSharesByPooledEth` | `deposit→redeem` (and `mint→withdraw`) cannot increase caller value; `shares>0` when `assets>0` | `ROUNDTRIP` (new) | **P1** |
| **A5** | **Multicall / batch `msg.value` reuse** | Multicall3 docs; classic delegatecall/`msg.value` | `multicall(bytes[])` 0xac9650d8, `batch`, `executeBatch`, `tryAggregate` + CALLVALUE | Σ msg.value-dependent credits ≤ msg.value; no per-subcall reuse | `VALUE` (new) | **P1** |
| **A6** | **Deflationary / fee-on-transfer / rebasing accounting** | OZ Notorious Bug Digest #4 (KRC, FIRE) | contract reads its own `balanceOf`; AMM `skim`/`sync` selectors | no accounting advance based on a balance a third party can change mid-flow | `SINGLE` + hostile token mock | **P1** |
| **A7** | **Unchecked external call / calldata-derived call target** | OWASP SC06 | CALL/STATICCALL target/amount from calldata; result not branched | no state advance when an external call is attacker-controlled or fails | `SINGLE` | **P2** |
| **A8** | **Hostile callback accounting** (the *interesting* reentrancy only) | OWASP SC08; your #3 | hook selectors `tokensReceived`, `onERC1155Received/Batch`, `onERC721Received`, `onFlashLoan`, `uniswapV2Call`, ERC-3156 `execute` | during a callback, target re-entered with arbitrary selector cannot exceed entitlement | `REENTRANT` (new) | **P2** |
| **A9** | **Unauthenticated pull / attacker-named payer (approval siphoning)** | OWASP SC01/SC02/SC05; ExVul 2026-09-11 ether.fi/Veda AtomicQueue (~15.45 ETH) | `transferFrom` 0x23b872dd / `safeTransferFrom` 0x42842e0e,0xb88d4fde **called** on a token, with the `from`/payer argument calldata-derived and not checked against `CALLER`/consent | no caller can move tokens from an address that has merely approved the contract (no active consent) | `UNAUTH_PULL` (new) | **P0** |

### Per-stage notes

- **A1 INIT.** Parity-style; no economics to model; the highest zero-day-per-CU
  class in the sweep. Overlaps the existing `P_STORAGE_CHANGED` only partially —
  that flag fires on *any* slot write, whereas A1 keys on the **initializer
  selector**, so it can target (and not drown in) the right bytecodes.
- **A2 UPGRADE.** `sig_proxy_like` already isolates 35,605 bytecodes / 20.46M
  deployments of delegatecall shells; A2 is the takeover property on top.
  The "attacker-controlled DELEGATECALL target" check is the genuinely new
  invariant (current suite never inspects call targets).
- **A3 REPLAY.** Two identical calls with the same symbolic signature; perfectly
  self-contained and very Kontrol-shaped. Catches missing-nonce / missing
  consumption-record bugs that static tools miss.
- **A4 ROUNDTRIP.** This is your #1 "near-empty market" in its *sweepable* form.
  It is **not** the same as P7_PROFIT: P7 is a generic div-dense profit oracle,
  A4 is a directional round-trip conservation property keyed on vault selectors.
- **A5 MULTICALL.** Blocked today by gap #1 below (calls carry 0 value). Needs a
  value-carrying template.
- **A6 FEE/DEFLATIONARY.** The target must be allowed to read a manipulable
  balance; model with a fee-on-transfer token mock, not the current no-op mock.
- **A7/A8.** Lower priority but cheap once call-target and `expectCall` machinery
  exist; A8 replaces "can I reenter?" with "can I reenter into *stale accounting*?".
- **A9 UNAUTH PULL.** The fresh live exploit (ExVul, 2026-09-11). Permissionless,
  single-contract, arbitrary calldata. The core is *"the contract spends an
  address's allowance that only `approve`d it, with no active consent"*. Needs a
  mock ERC-20 with real per-account balances + allowance enforcement and a
  modeled victim: property = victim balance cannot change unless the victim is
  `msg.sender` (or a valid consent signature is checked). Bytecode precision is
  the lowest of the set (`from` may legitimately equal `CALLER`); pair the
  scanner with the stage-2.5 4byte/ABI assist to confirm a `solver`/`payer`
  parameter.

### Track A gaps this exposes (fix before A1–A9)
1. **No `msg.value`** — every probe calls with 0 value → all payable accounting
   classes are false-negatives today (A5).
2. **No selectors** — the radar has opcode counters + 8 structural flags only;
   vault/proxy/init/permit/pull functions are invisible.
3. **Slots 0..15 only** — no admin-slot targeting.
4. **No call-target / `expectCall` / reentry machinery** (A2/A7/A8).
5. **No consent/approval model** — `MockERC20` has no balances or allowance
   semantics, so A9 (and any pull) cannot be expressed yet.
6. **No selector-DB/ABI assist** — needed to raise A9 precision.

---

## 2. FILTER OUT — do not spend Kontrol budget

| Class | Why filter | Better served by |
|---|---|---|
| **Plain reentrancy / cross-function reentrancy with no accounting twist** | OWASP 2026 SC08 dropped to #8, rated Medium; AI/human detection 94%/96% — saturated | slither/fuzzing; only the stale-accounting variant survives (A8) |
| **Generic missing `onlyOwner` / access control** | low novelty, high false-positive; individual functions "look correct" | static review; the *takeover* variants are A1/A2 |
| **Simple overflow / underflow** | Solidity 0.8 reverts; residual only inside `unchecked` | compiler + fuzzing |
| **Timestamp dependence, insecure randomness, pure DoS** | removed/absent from OWASP 2026; not value-extraction | static review |
| **Basic flash-loan → spot oracle → borrow** | requires modeling an external market, not a bytecode-local property | Track B phase/order harness (#4) |
| **Unbounded 10-step "find me a bug" searches** | path explosion; our 3-call control already hit 4h12m | `--bmc-depth` bounded Track B per-target |

### Explicitly rejected *despite* being on the candidate list
- **Generic reentrancy detectors** — replaced by A8 (accounting-scoped only).
- **"Missing `onlyOwner`"** as a class — replaced by A1/A2 (permissionless takeover).
- **Broad oracle manipulation** — only the *two-reads-in-one-op phase* variant is
  admitted, and only in Track B.

---

## 3. Already covered — do not duplicate

| Existing property | Sweeps stage | What it already catches |
|---|---|---|
| `P_STORAGE_CHANGED` slots 0..15 | all | arbitrary calldata corrupting admin/accounting slot |
| `P_AUTH_WRITE` | all | attacker address written to a slot |
| `P_BALANCE_LOST` / `P_ATTACKER_PROFIT` | all | ETH extraction |
| `P_TOKEN_OUTFLOW/APPROVAL/TO_ATTACKER` | all | ERC-20 value movement |
| stage-1 P1/P2 | 1 | `sstore` no-caller+delegate, selfdestruct+delegate |
| stage-2 P3/P4 | 2 | naive-proxy hijack, TSTORE two-phase |
| stage-3 P7 | 3 | div-dense value-extraction oracle (not rounding-direction) |

---

## 4. Kontrol-capable but pipeline-incompatible — Track B curated invariants (not light batch)

Kept separate from §1 because each needs a per-target harness with etched
dependencies. This is where your top-5 list actually lives.

| Invariant | Candidate-list item | Why not sweepable | Harness sketch |
|---|---|---|---|
| **Near-empty market / inflation** | #1 | needs vault + underlying token + donation semantics | model vault + 1 token, direct-mint to vault, bound `donate/deposit/mint/withdraw/redeem` |
| **Cross-function accounting desync** | #2 | "entitlement" is protocol-specific | snapshot all accounting slots; permute `deposit/withdraw/borrow/repay/liquidate/harvest/claim` |
| **Callback / order-dependent accounting** | #3 | needs a forced reentry hook | `expectCall` (kontrol-cheatcodes) into a reentrant mock |
| **Same-tx oracle phase** | #4 | needs an oracle stub the attacker can mutate between reads | etched oracle stub; prove stability between two reads |
| **Impossible-state transition** | #5 | bad predicate is protocol-specific | prove unreachability of `totalDebt>totalAssets`, `shares==0 ∧ assets>0`, `reserve==0 ∧ claimable>0` |
| **Read-only reentrancy of `getPrice()`/`getReserves()`** | (external suggestion) | bug lives in the **consumer**, not the provider | flag providers in radar; prove *consumer* uses a stale view during a state-changing call |
| **Library-fingerprint bugs** | (your last point) | needs code fingerprinting + the specific invariant | fingerprint PRBMath `mulDivSigned` v1.1.0–4.0, OZ ERC4626 `_deposit` overrides, deflationary assumptions; prove the exact arithmetic invariant per match |

Evidence this matters: Certora found `PRBMath.mulDivSigned` rounding the wrong way
for negatives in every version 1.1.0–4.0; MetaPool allowed free `mint()` after
overriding `ERC4626._deposit`'s receipt check; Curve `get_virtual_price` was
misreported via read-only reentrancy (dForce, Feb 2023).

---

## 5. Per-stage opcode scanning — one scanner per stage

Decision: **no single shared "flag" scanner.** Every stage gets its own module
with its own detection predicate, explicit false-positive filters, and its own
full target output (bytecodes + deployments + contract addresses). This keeps a
stage's targeting reproducible and reviewable, and stops one stage's FP
tolerance from leaking into another's.

```
CA/scanners/
  common.py              # metadata strip, push-aware disasm, operand mask,
                         # selector extraction (PUSH4 + dispatcher region),
                         # code-hash normalization, parquet/duckdb IO
  scan_p1_auth_write.py  scan_p2_balance.py
  scan_a1_init.py        scan_a2_upgrade.py
  scan_a3_replay.py      scan_a4_roundtrip.py
  scan_a5_multicall.py   scan_a6_fee.py
  scan_a7_unchecked.py   scan_a8_callback.py
  scan_a9_unauth_pull.py
```

Each scanner emits, for its stage:

- `data/stages/<id>.parquet` — one row per **unique bytecode**:
  `bytecode_hash, n_ops, code_size_eff, has_metadata, deployments,
   <stage evidence cols>` (e.g. selectors found, call/value pattern, slot hints).
- `data/stages/<id>_deployments.parquet` — bounded address sample:
  `bytecode_hash, address, blocknum`.
- `harness/stages/<id>/manifest.json` + chunk plan (top-N by deployments),
  so `gen_stage.py` and `triage_live.py` need no rescan.

### Common FP filters (every scanner)
1. **Metadata-stripped** code only (already implemented in `opcode_scan.py`).
2. Selector must be in the **dispatcher region**, not any PUSH4 constant
   (constants/strings contain accidental selector bytes).
3. **Allowlist** of known singletons/libraries (Multicall3, Permit2, WETH,
   canonical proxy impls) excluded unless the stage targets them.
4. **Dedup by normalized code hash** (metadata-insensitive) so forks don't
   multiply the target list.
5. Minimum `n_ops` / `code_size_eff` to drop trivial stubs.
6. Live-state cross-check in triage (initialized / guarded / funded).

### Stage-specific detection + FP filters
| Stage | Detect (dispatcher) | Key FP filters |
|---|---|---|
| A1 INIT | `initialize`/`reinitialize`/`init` + SSTORE in same function | require an unguarded path to SSTORE; exclude already-initialized via triage |
| A2 UPGRADE | `upgradeTo`/`upgradeToAndCall`/`setImplementation`/`changeAdmin` | require DELEGATECALL; require target from CALLDATALOAD; exclude transparent-proxy admin paths |
| A3 REPLAY | `permit`/`transferWithSig`/`execute` + `ecrecover` precompile call | exclude same-function nonce SSTORE; exclude Permit2 singleton |
| A4 ROUNDTRIP | ERC-4626/vault selectors + div/mul density | require selector **set** (`deposit`+`redeem`+`convertToShares`); exclude virtual-offset `+1` pattern |
| A5 MULTICALL | `multicall`/`batch`/`executeBatch` + CALLVALUE | exclude Multicall3; require a payable entry |
| A6 FEE | STATICCALL to token `balanceOf` 0x70a08231 + AMM `skim`/`sync` | exclude contracts that cache reserves and never re-read |
| A7 UNCHECKED | CALL/STATICCALL target/amount calldata-derived, result unused | exclude safe-call wrappers (returndatasize check) |
| A8 CALLBACK | hook selectors implemented | exclude pure receivers with no accounting |
| A9 UNAUTH PULL | CALL `transferFrom`/`safeTransferFrom`, `from` arg from CALLDATALOAD | exclude `from == CALLER` guarded paths; needs stage-2.5 selector-DB/ABI to confirm a `solver`/`payer` parameter |

After these scanners run once, each stage becomes an ordinary target list +
`gen_stage.py` template (+ sanitized light batch), exactly like P1–P7 today.

---

## 6. Light-batch sanity (stage N.5) — controls per new stage

Same rule as today: controls are chunk 0, and if a control breaks the run is void.

| Stage | MUST-FAIL control | MUST-PASS control |
|---|---|---|
| A1 INIT | unprotected `initialize` sets owner | `initializer`-guarded / gated |
| A2 UPGRADE | unprotected `upgradeTo` writes impl slot | `_authorizeUpgrade` / `onlyOwner` |
| A3 REPLAY | nonce never incremented (double effect) | `_useNonce` advances |
| A4 ROUNDTRIP | donation-inflated first depositor | virtual shares/assets offset |
| A5 MULTICALL | `msg.value` reused across subcalls | per-call value accounting |
| A6 FEE | reads own `balanceOf` after donation | cached reserve |
| A7 UNCHECKED | state advances on failed call | revert/branch on failure |
| A8 CALLBACK | harvest reads stale `totalAssets` on reenter | state updated before callback |

Cost caveat: a passing 3-call control already took 4h12m. New stages use
`--bmc-depth` (bounded loops), `--fail-fast`, `--no-break-on-calls`, `--use-booster`.
Track B multi-step proofs must run in a **separate low-parallelism workflow**,
never inside the 20-way mass matrix.

---

## 7. Recommended build order

1. **Per-stage scanners** (§5, `CA/scanners/`) — unblocks everything; one rescan.
2. **A1 INIT + A2 UPGRADE + A9 UNAUTH PULL** — pure permissionless takeover/pull,
   no economics. A9 additionally needs the consent/allowance mock.
3. **A3 REPLAY + A4 ROUNDTRIP** — self-contained, closes the precision-loss gap.
4. **A5 MULTICALL + A6 FEE/DEFLATIONARY** — needs the value template + hostile token mock.
5. **A7 UNCHECKED + A8 CALLBACK** — needs call-target and `expectCall` machinery.
6. **Track B** — top-TVL candidates from the enhanced radar; start with inflation
   (#1) and impossible-state (#5) as the most tractable invariants.

---

## 8. Evidence & sources

- OWASP Smart Contract Top 10 2026 — SC01 Access Control, SC02 Business Logic,
  SC03 Price Oracle, SC05 Input Validation, SC06 Unchecked External Calls,
  SC07 Arithmetic Errors (rounding), SC08 Reentrancy, SC10 Proxy/Upgradeability.
- OpenZeppelin, *Web3 Security Auditor's 2025 Rewind* — zkLend rounding/inflation,
  ResupplyFi near-empty ERC-4626 collateral manipulation.
- OpenZeppelin, *Notorious Bug Digest #4* — KRC/FIRE deflationary AMM drains,
  MetaPool `ERC4626._deposit` override free-mint, Permit2 nonce desync.
- Certora, *Problems in Solidity Fixed Point Libraries* — `PRBMath.mulDivSigned`
  rounds toward zero instead of −∞ (v1.1.0–4.0).
- ChainSecurity, *Curve LP Oracle Manipulation Post Mortem* — `get_virtual_price`
  read-only reentrancy; dForce (Feb 2023).
- Multicall3 README — `msg.value` persists across `delegatecall` subcalls.
- scsfg *Signature-related Attacks*; arXiv 2511.09134 — `ecrecover` nonce/replay.
- ExVul (@exvulsec), 2026-09-11 — ether.fi Liquid / Veda `AtomicQueue.solve`
  unauthenticated `solver` → `safeTransferFrom(solver, user, amount)`, ~15.45 ETH
  pulled from 11 approving users. Attacker `0xa5cc6e49…b64ea`, vulnerable queue
  `0xd45884b592e316eb816199615a95c182f75dea07`. → stage **A9**.
