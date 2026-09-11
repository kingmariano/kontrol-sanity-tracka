# Probe Findings — Batch 1 (2026-09-10)

## Pipeline
Raw bytecode (etch) → zeroed storage (slots 0..7) → 1 ETH funding → symbolic call
(arbitrary selector + args + attacker) via Kontrol/KEVM. Two properties:
- **P2-SELFDESTRUCT**: target balance must survive the call
- **P1-HIJACK**: no storage slot may come to hold the attacker's address
Controls validated: SafeControl proven safe (27m22s); VulnerableControl flagged with
the `kill()` selector (0x41c0e1b5) as concrete counterexample (13m43s).

## Batch 1 scoreboard (8 wild candidates + 2 controls)
| Probe | Signal class | Ops | Verdict | Time |
|---|---|---:|---|---:|
| safe_control | control | — | ✅ PASSED | 27m22s |
| vulnerable_control | control | — | ❌ FAILED (expected) | 13m43s |
| selfdestruct_delegate_5 | SD+DELEGATE | 22 | ✅ PASSED | 6m18s |
| **selfdestruct_delegate_6** | **SD+DELEGATE** | **24** | **🚨 FAILED — 9 failing nodes** | pending branches |
| sstore_no_caller_delegate_2 | no-auth+DELEGATE | 509 | ✅ PASSED | 6m54s |
| sstore_no_caller_delegate_3 | no-auth+DELEGATE | 266 | ✅ PASSED | 6m33s |
| sstore_no_caller_delegate_4 | no-auth+DELEGATE | 514 | ✅ PASSED | 6m46s |
| transient_caller_small_7 | transient+CALLER | 87 | ✅ PASSED | 6m44s |
| transient_caller_small_8 | transient+CALLER | 83 | ✅ PASSED | 6m44s |
| transient_top_template_9 | transient+CALLER | 524 | ✅ PASSED | 22m12s |

## Finding #1 — `0xecf1f013d5c530d01b8a970a170b9f07664aa892eda19723c21e4aab35748e6f`
- 24-op contract with reachable SELFDESTRUCT + DELEGATECALL (symbolic caller, any selector)
- 9 failing nodes at flag time; 139 branches still being explored (--no-fail-fast)
- **Blast radius:** 144 deployments, ALL within block 11,462,839–11,463,489
  (~650 blocks, single campaign, ~Jan 2021), identical creation tx (batch factory)
- **Live-state triage (Blockscout):** sampled instances hold **zero ETH, zero tokens**,
  balances untouched since creation, unverified, single deployer
  (`0x4c9Cea68...`) → dormant 5-year-old contract family
- **Assessment:** CONFIRMED property violation / LOW practical impact (no funds at risk).
  Exactly the SCONE-bench lesson in practice: property violation ≠ profitable exploit —
  the profit-oracle filter (P7) is what separates findings from noise.

## Calibration (per-proof cost, 2 workers, this box)
| Contract size | Typical proof time |
|---|---:|
| ~66-node small (22-119 ops) | 6m20s-6m55s |
| ~240-340 nodes (524 ops, 807B control) | 22-27 min |
| fail-fast early exit | 13m43s |
→ Stage-1 sweep budget: ~7 min/small target, ~25 min/large target (2 workers).

## Honest caveats
1. Zeroed-storage harness: findings are for the *generic* instance; state-dependent
   exploits need per-deployment state (that's what setArbitraryStorage runs add).
2. `sig_sstore_no_caller` candidates passed because the P1 check requires the written
   value to equal the caller — mapping-style writes (balances[attacker]) are invisible
   to this probe; needs P1b (value-unchanged-invariant) variant.
3. Bounded by --max-depth 1000: "PASSED" means "no violation within depth", not
   unbounded proof (except where pending=0 and no loops — the small candidates).
