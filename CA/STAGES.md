# Campaign Stages & Research-Class Map — Reference

*The single-page map from researched zero-day classes → symbolic properties →
execution stages → compute. Companion to ZERO_DAY_RESEARCH.md and FINDINGS_BATCH1.md.*

## Research classes → properties

| # | Research class (canonical case) | Property | Harness shape | Property cost |
|---|---|---|---|---|
| 1 | Missing auth on exposed fn (SWEAT) | **P1** — attacker's address must never appear in storage slots 0..7 after arbitrary call; **P1b** (planned) — no storage value change at all | single call | ~7 min |
| 2 | Kill-switch / selfdestruct | **P2** — target ETH balance must survive arbitrary call | single call | ~7 min |
| 3 | Rounding-direction inconsistency (Balancer) | **P6** — deposit(d) → k swaps (BMC-bounded) → withdraw ⇒ attacker balance ≤ d | multi-call sequence | ~1-3 h |
| 4 | Near-zero denominator (Cetus) | **P5** — bounded input ⇒ bounded output (output/input ≤ 10⁶) | single call + math compare | ~15-30 min |
| 5 | Callback/transient auth (SIR) | **P4** — two-call sequence: attacker primes TSTORE, then a different selector's auth-check passes | two-call sequence | ~30-60 min |
| 6 | Callback spoofing (Uniswap-style) | **P4-variant** — auth value derived from msg.sender/calldata instead of stored constant | single/two-call | ~15-30 min |
| 7 | Uninitialized proxy / UUPS (classic) | **P3** — DELEGATECALL target must be a compile-time constant or EIP-1967 slot | single call + KCFG target check | ~15-30 min |
| 8 | EIP-7702 delegate invariants | **P8** — sponsor cannot redirect without nonce/value/gas/target checks | direct delegate audit | n/a (not in dataset) |
| M | Master profit oracle (SCONE-style) | **P7** — deal(attacker, 0) → N calls ⇒ attacker gained ≥ 0.1 ETH or target lost funds | N-call sequence | refiner for survivors |

## Stage breakdown

| Stage | Properties | Target set (radar) | Size | Compute | Status |
|---|---|---|---|---|---|
| **0 — Foundation** | — | 69.8M deployments → 1,539,858 unique bytecodes | opcode radar, push-aware | DuckDB | ✅ DONE (parquet persisted) |
| **0.5 — Pilot** | P1, P2 | 8 triaged + 2 controls | 10 proofs | ~2 h local | ✅ DONE — 1 wild finding (FINDINGS_BATCH1.md) |
| **1 — Cheap sweep** | P1, P2 | sstore_no_caller+delegate (19,670) ∪ selfdestruct+delegate (28,184), deployment-weighted triage | 40 now → ~5k total | ~7 min/small, ~25 min/large proof; CI matrix parallelizes | 🔄 CI sweep starting |
| **2 — Deep auth** | P3, P4 | transient+caller (136,092), delegate (338,176) → triaged | ~1-2k | ~30-60 min/proof | next |
| **3 — Math + profit** | P5, P6, P7 | AMM/math templates (div-heavy, bytecode-similar to known pools) + Stage-1/2 survivors | ~100s | 1-3 h/proof, resumable CFGs | later |
| **4 — 7702 delegates** | P8 | 0xef0100-prefixed accounts (separate scan) | n/a | separate pipeline | n/a |

## Compute compression table (Stage 1 = 5,000 targets)

| Setup | Parallel proofs | Wall-clock |
|---|---|---|
| This Codespace (2 workers) | 2 | ~2 weeks |
| GitHub Actions, public repo, 20 concurrent (free) | 20 | ~2 days |
| GitHub Actions, 50 concurrent | 50 | ~1 day |
| Larger runners (16 vCPU) × 50 | 100 | ~12 h |
| Self-hosted spot fleet (5× 16-core) | 80 | ~10-15 h |

Mechanics: chunked .sol files (5 proofs/chunk) committed → matrix jobs prove
independently → verdicts + counterexample models uploaded as artifacts.
Long proofs: Kontrol KCFG state is resumable — a job nearing the 6h GitHub cap
uploads `out/kcfg`; the next run continues it (no `--reinit`).

## Finding severity ladder (how a flag becomes a report)
1. **Property violation** (proof FAILED) — mechanical fact
2. **Deployment census** — how many addresses share the bytecode (DuckDB join)
3. **Live-state triage** — Blockscout: balances, tokens, activity (zero funds ⇒ dormant)
4. **P7 profit oracle** — is there a *monetizable* sequence?
5. **Report** — counterexample + census + live state, FINDINGS_BATCH*.md
