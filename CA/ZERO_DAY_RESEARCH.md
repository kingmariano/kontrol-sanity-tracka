# Deep Research: Permissionless Zero-Day Bug Classes (2025–2026)
*Research dossier for the audit campaign — compiled 2026-09-10. Sources: primary
post-mortems (SIR, BlockSec/Phalcon, Trail of Bits, Check Point, Fireblocks, rekt,
Dedaub, Anthropic). No properties written yet per instructions.*

---

## PART 1 — CASE STUDIES (primary-source verified)

### 1.1 SIR Trading — transient storage collision (Mar 30, 2025, $355K)
- **Mechanism**: `uniswapV3SwapCallback` verified caller-is-Uniswap-pool by reading
  TLOAD(slot 1), but the protocol itself later did `tstore(1, mintAmount)` — by the
  time the check mattered, slot 1 held an attacker-controlled `uint256`, not an address.
- **Amplifier**: attacker brute-forced a **CREATE2 vanity address whose numeric value
  equaled the forged `mintAmount`** so the corrupted "pool address" check passed.
- Repeated callback invocations siphoned the entire vault TVL.
- Attack tx: `0xa05f047ddfdad9126624c4496b5d4a59f961ee7c091e7b4e38cee86f1335736f`.
- **Permissionless**: no keys, no signatures, no victim interaction.
- **Class**: transient-storage lifecycle bug — stale TLOAD after TSTORE overwrite +
  cross-type aliasing (uint256 vs address) + vanity-address forging.

### 1.2 Balancer V2 — rounding-direction inconsistency (Nov 3, 2025, $128.6M)
- **Mechanism (BlockSec, confirmed by Balancer's official report)**:
  upscaling used *unidirectional* rounding (`mulDown`), downscaling used
  *bidirectional* rounding (up + down). The asymmetry violates the core invariant
  "rounding must always favor the protocol".
- **Amplification (Check Point)**: balances pushed to the **8–9 wei boundary** where
  Solidity integer division loses maximal precision; **65+ micro-swaps executed in
  the attacker contract's constructor** compounded the loss; `_upscaleArray` in the
  StableMath invariant path distorted invariant D → BPT price computable as wrong.
- **Evasion**: two-stage — exploit tx with no immediate profit, profit realized in a
  separate withdrawal tx. Protocol could not be paused; forks (Beets Fi etc.) hit too.
- **Shameful history (Trail of Bits)**: they found this exact rounding class in 2021
  audits (TOB-BALANCER-004, "undetermined severity"); the Sept 2022 ComposableStablePool
  review explicitly excluded the Stable Math library. Bug lived 4+ years until $128M.
- **Systemic**: one bytecode template shared by forks — our bytecode dedup finds these.

### 1.3 SWEAT (NEAR) — missing callback guard (Apr 2026, ~$3.5M)
- **Mechanism**: NEP-141 `ft_resolve_transfer` lacked the `#[private]` guard
  (predecessor == self check). Attacker contract performed a noop transfer that
  returned empty bytes → interpreted as "receiver consumed zero" → refund logic
  sent the **victim's entire balance to the attacker**. Direct, permissionless call.
- **Detection (Fireblocks)**: 20 min alert→root-cause via receipt-graph parsing +
  WASM decompilation; then **proactive class-hunting** found the identical flaw in
  the HOT token (22M holders) — patched same day.
- **EVM analog**: unprotected critical functions (missing onlyOwner/initializer/
  internal-only guards). This is THE most bytecode-symbolic-detectable class.

### 1.4 Cetus (Sui) — near-zero denominator math (May 22, 2025, $223M)
- **Mechanism**: `get_liquidity_from_a` with a 200-tick price range → denominator
  ~0 → 1 SCA deposit minted **10^34 liquidity units**; overflow checks existed but
  missed this path (Dedaub). Every Cetus AMM pool drained; $60M crossed Wormhole.
- **Systemic**: Verichains found the same shared math library in 3 Sui protocols
  ($24.6M TVL); auditors had marked the shared lib "out of scope".
- **Class**: bounded-input → unbounded-output failure; division/precision explosion.

### 1.5 Anthropic SCONE-bench — agent-discovered zero-days (Dec 2025)
- 417 real incidents (DeFiHackLabs-sourced), contract forked at historical block on
  local anvil; agent writes `FlawVerifier.sol` whose `executeOnOpportunity()` must
  extract >= 0.1 native token — **profit is the oracle**. Grader restarts anvil, so
  state-staging cheats are impossible.
- Frontier models (Opus 4.5 / Sonnet 4.5 / GPT-5) developed exploits worth **$4.6M**
  on post-knowledge-cutoff incidents; exploit revenue doubling every ~1.3 months.
- **Novelty test**: on 2,849 recently deployed no-known-vuln contracts, agents found
  **2 novel zero-days** worth $3,694 (GPT-5 cost $3,476 in API). One was an
  unprotected write-capable calculator function -> token inflation.
- **Implication for us**: profit-conditioned properties are the right oracle class;
  our Kontrol approach does *exhaustively* what agents do *heuristically*.

---

## PART 2 — PERMISSIONLESS ZERO-DAY CLASS TAXONOMY
("Permissionless" = no privileged key, no victim signature, no user interaction.
Symbolic translation: **EXISTS attacker address AND EXISTS contract state such that
an invariant is violated**, attacker quantified over all addresses — exactly
`prank` + `setArbitraryStorage` in Kontrol terms.)

| # | Class | Canonical case | Bytecode-static signal | Symbolic feasibility |
|---|---|---|---|---|
| 1 | Missing auth on exposed state-changing fn | SWEAT | no CALLER check on path to SSTORE of critical slot | *** trivial: prank arbitrary caller -> expect revert |
| 2 | Transient storage lifecycle | SIR | TLOAD(0x5c)/TSTORE(0x5d) present; auth value from TLOAD | ** hard: bound slot values, model cross-call tstore |
| 3 | Rounding-direction inconsistency | Balancer | DIV/MULUP/MULDOWN asymmetry; tiny-balance paths | *** KEVM exact arithmetic: pool balance after N swaps >= before |
| 4 | Near-zero denominator / precision explosion | Cetus | DIV on computed denominator; tick-range math | ** property: bounded deposit => bounded mint |
| 5 | Callback authorization spoofing | SIR, Uniswap callbacks | msg.sender compared against derived (not stored) value | *** expect*Call + prank machinery |
| 6 | Delegation invariants (EIP-7702) | sweeper/drainer delegates | 0xef0100 prefix; missing nonce/value/gas checks | ** audit delegates directly |
| 7 | Uninitialized storage / UUPS / selfdestruct | classic-recurring | SELFDESTRUCT reachable; DELEGATECALL target from SLOAD 0 | *** fully bytecode-symbolic |
| 8 | Oracle price manipulation | many 2024-25 hacks | needs external pool state | * needs forking; Kontrol has no fork cheatcodes |

## PART 3 — STRATEGIC INSIGHTS FOR OUR CAMPAIGN
1. **Bytecode dedup = fork detection.** Balancer forks, 3 Sui protocols sharing math:
   one finding of a vulnerable template generalizes to every deployment of that
   bytecode. Our DuckDB `bytecode_hash` groupby is a force multiplier: finding X in
   bytecode B -> instant census of all deployed instances + addresses.
2. **The profit oracle beats the state-change oracle.** Trail of Bits knew the
   Balancer bug in 2021 but could not value it ("undetermined severity"). Properties
   should be written as: EXISTS input sequence such that attacker profit > 0,
   not merely "state changed".
3. **Two-stage / cross-transaction attacks** (Balancer) — model both stages in one
   symbolic test (call 1: no profit; call 2: withdraw).
4. **Class-hunting loop** (Fireblocks): after a novel finding in one bytecode,
   pattern-search all 1.54M for structurally similar code, then re-run properties.
5. **Novel-edge hunting is viable at scale** (Anthropic): recent deployments with no
   known vulns yielded real zero-days. Our Feb-2025 snapshot + size-band filtering
   targets exactly that population.
6. **Static pre-filters we can run today on the DuckDB corpus:**
   - TLOAD/TSTORE presence (classes 2 and 5)
   - SELFDESTRUCT reachability (class 7)
   - DELEGATECALL target from SLOAD/computed value (class 7)
   - DIV density near low-balance paths (classes 3/4)
   - no CALLER-check before SSTORE on selector hot paths (class 1)

## PART 4 — KNOWLEDGE-CORPUS INTEL (from context, verified against sources)
- **FORGE / FORGE-Curated** (27,497 findings / 6,454 audits / 81,390 files, 296 CWEs)
  — best for mining property-template patterns; FORGE-Curated has verified
  code-location mappings (Dec 2024 - Feb 2026).
- **X23** — normalized findings + embeddings -> semantic retrieval for triage hints.
- **Nyx/SPECA** — CodeHawks + Code4rena + Sherlock normalized corpus.
- **DeFiHackLabs** — the ground-truth PoC catalog; **it is literally what SCONE-bench
  was built from** -> dual use: regression harness for our property templates.
- **Warning** (applies to corpus use, not directly to us): massive overlap between
  these datasets; dedupe by (protocol, finding, function, code hash) before treating
  counts as meaningful.
- For our purpose we do not need to *train* anything: these corpora serve as
  **property-template catalogs** (root cause -> precondition -> effect -> profit).

## PART 5 — WHAT'S NEXT (proposed, awaiting go-ahead)
1. Static opcode-feature scan of 1.54M unique bytecodes (class 1/2/5/7 signals).
2. Property template library v0: 8 templates mapped to the taxonomy, each with a
   symbolic harness skeleton (etch + setArbitraryStorage + prank + profit assertion).
3. Pilot on ~50 hand-picked high-signal bytecodes -> measure pass/fail/timeout rates
   to calibrate throughput before scaling.

