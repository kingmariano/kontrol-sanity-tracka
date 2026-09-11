# Findings Harvest — Stage 1 Wave 1 + Stage 2 Deep-Auth (CI batches)

**Date:** 2026-09-11 · **Sources:** kontrol-stage1-sweep (Wave 1) + kontrol-stage2-deepauth
**Status:** properties CONFIRMED as *model* violations; **live-gate re-check (2026-09-11)
found NO live-exploitable drain for F4–F9** — see `LIVE_GATE_RECHECK.md`.**

> ⚠️ **Live-gate summary:** F4 — 873/873 funded initialized (`slot0!=0`), rejected.
> F5 — hardcoded-owner gate + dust, rejected. F6/F7 — dormant. F8 — 8/8 code-bearing
> funded initialized (`slot1!=0`); 47 USDC safe; the lone "uninitialized" entry is a
> codeless account. F9 — all funded `slot5=1`, sweep reverts. **No live funds were
> drainable via any proven path.**

## Stage 2 P4 transient-auth hits (4 wild families)

The two-phase transient property (certified against the SIR-shape control) fired on
4 distinct wild bytecodes from the `transient_caller` radar pool:

| # | Bytecode hash | Ops | Deployments | Chunk |
|---|---|---|---|---|
| 5 | `0xa24e966a6a8d544d…` | 436 | 4,374 | S2-6 |
| 6 | `0x6f83343a067ba432…` | 752 | 3,004 | S2-10 |
| 7 | `0x3b7d6f59758a4aa6…` | 264 | 2,116 | S2-13 |
| 8 | `0x1aba7e718e34dc9a…` | 972 | 971 | S2-23 |

Full hashes:
```
0xa24e966a6a8d544de0580e9f47c0085de7430f9cce6dbc0f8b8bc9f009cada59
0x6f83343a067ba432f2f9f48b9d78148966a9647206bf932f67382fef4c534df0
0x3b7d6f59758a4aa6b2a0c9b55b0e19bd15a9bbcd0715299cecc974a05e904a06
0x1aba7e718e34dc9a2d223fc9b695a815b27a291fb2ea7446c8d9022f4307e3d9
```

Meaning: an attacker can prime transient storage with a chosen value (Phase A),
then pass the TLOAD-derived authorization on a second call (Phase B) — the exact
SIR-class pattern, found independently in 4 unrelated bytecode families.

## Live-funds triage (Blockscout, sampled instances)

| # | Sample instance | State |
|---|---|---|
| 5 (S2-6) | `0x676e1c7b…11de` (block 5.9M, 2018-era) | pending check |
| 6 (S2-10) | `0x04936955…1dae` (block 9.8M) | pending check |
| 7 (S2-13) | `0x0b371778…63f6` (block 9.1M) | pending check |
| 8 (S2-23) | `0x3952fe74…3201` (block 20.7M) | **0 ETH but holds 47 USDC — first live-value hit of the campaign**; 3 other sampled instances empty |
| 4 (c5_3) | `0xf040b7c7…6D24` — **verified `SmartAccountProxy`** (2023) | 0.0002 ETH dust, has logs — smart-account family; re-verify first |

## Inspectable instance addresses (copy-paste)
```
# F5 (S2-6, sel 0x44439209, hijack)
0x676e1c7b4b297ce36706eacdfe6d7fb93e0211de
# F6 (S2-10, prime 0x6b9f96ea / drain 0x00821de3)
0x049369551ad83b3c76b0dc58c26b06a335e41dae
# F7 (S2-13, sel 0x6b9f96ea, prime=0 trivial)
0x0b371778885b6fc9bf12eccf41f2ae9eb9c563f6
# F8 (S2-23, sel 0x19ab453c, SIR-shape, holds USDC)
0x3952fe747D6967b3Cf53A84593a95114E7De3201
# F4 suspect (c5_3, SmartAccountProxy, kore-crash verdict)
0xf040b7c786a90852bf387D3Afc81d4E627236D24
```

## Triage results (counterexample-level, from CI prove logs)

| # | Assertion fired | Selector(s) | Model highlights | Assessment |
|---|---|---|---|---|
| 5 (S2-6) | `P4-HIJACK-AFTER-PRIME` | `0x44439209` (both phases) | contract writes caller-chosen address (arg low-20-bytes) into privileged slot; solver unifies attacker with written address | **CONFIRMED** — arbitrary privileged-address installation |
| 6 (S2-10) | `P4-SD-AFTER-PRIME` (balance drained) | prime `0x6b9f96ea` → drain `0x00821de3` | two distinct selectors; balance 1 ETH → 0 | **CONFIRMED** — primable selfdestruct/drain |
| 7 (S2-13) | `P4-SD-AFTER-PRIME` (balance drained) | `0x6b9f96ea` (both phases, `prime = 0`) | same selector twice; zero prime suffices — trivially exploitable | **CONFIRMED** — weakest guard of the four |
| 8 (S2-23) | `P4-HIJACK-AFTER-PRIME` | `0x19ab453c` (both phases) | prime = attacker's own address → TSTORE → second call authorized | **CONFIRMED** — textbook SIR-shape; **same selector as Finding #2** (family lead) |

**Cross-family leads:** `0x6b9f96ea` appears in findings 6 & 7 (different
bytecodes, 752 vs 264 ops — likely one protocol family); `0x19ab453c` matches
Finding #2's selector exactly — bytecode-hash dedup missed it because the runtime
code differs, but the *vulnerable interface* is shared.

## Finding #4 (c5_3) — DOWNGRADED TO SUSPECT
The FAILED verdict is accompanied by a kore engine crash
(`Kore.Builtin.Krypto` assertion, code -32002 — symbolic precompile/keccak
artifact), not a clean property counterexample. **Re-verification required**
before counting it. Adjusted scoreboard: **7 confirmed, 1 suspect.**

## Triage results (counterexample-level, from CI prove logs)
## Stage 1 Wave 1 hits (running total)

| # | Bytecode hash | Ops | Deployments | Selector | Doc |
|---|---|---|---|---|---|
| 1 | `0xecf1f013…` (batch 1) | — | 144 | — | FINDINGS_BATCH1.md |
| 2 | `0x038cfd30…80ca497` | 412 | 10,029 | `0x19ab453c` | FINDING_2_c1_1.md |
| 3 | `0xf9e2d368…0ba1907` | 509 | 19,130 | `0xf09a4016` | FINDING_3_c0_2.md |
| 4 | `0x1cf5a0fe…4da3aaf3` | 568 | 1,352 | TBD | this file |

Full hash for #4:
```
0x1cf5a0fe3bf24282cc81b8ffae2e5e3aa750f3f182a6665e22ba4ab24da3aaf3
```

## Scoreboard
- **8 confirmed property violations** across 8 independent bytecode families
- ~40,000 deployments covered by failed proofs; ~700,000+ deployments mathematically cleared
- Triage queue: get-model per hit → concrete selector/args → deployment census → live-funds check

## ⚠️ Finding #9 (S2-38, chunk 38 / test_p4_w39) — property violation, LIVE EXPLOIT REJECTED

> **CORRECTION (next agent, 2026-09-11):** the "full ETH drain" below is a
> **zeroed-storage model artifact**, not a live exploit. All 194 funded instances
> have `slot5 = 1`; the public sweep `0x0b5ab3d5` requires `slot5 == 0` and
> otherwise reverts (`InvalidJump`). `eth_call` against live instances confirms
> the revert; a `slot5=0` state-override makes it succeed. Even then the payout
> goes to `slot2` (a third-party EOA), never the caller. Machine-checked in
> `CA/poc/` (5/5 tests). Full analysis: **`CA/FINDING_9_S2-38.md`**. The text
> below is retained as the original (pre-correction) record.

- **Bytecode:** `0x8824fcf9d1571b0d30d734c29b728e282437ef12747696a848581c112a971c8a`
- **Family:** wild `transient_caller` [P4-HEAVY] — **376 deployments**
- **Verdict:** `PROOF FAILED` with clean counterexample (run 34602954273, job chunk-38, artifact created 17:56 UTC)
- **Assertion fired:** `P4-SD-AFTER-PRIME: 0 != 1000000000000000000` — target's full 1 ETH **drained to 0**
- **Model:**
  - Phase A: `selA = 0x05b34410`, **prime = 0** (trivial — no attacker-chosen value needed)
  - Phase B: `selB = 0x0b5ab3d5`
  - Result: balance 1 ETH → 0 under attacker-controlled sequence
- **Assessment:** weakest guard class of the campaign alongside F7 — zero-value prime suffices for a full drain. **Census + live-triage required immediately** (same pipeline as F4–F8: balancemulti + WSS USDC sweep over all 376 instances).
- Cross-family: unrelated bytecode to F6/F7 (no shared selector), but same two-phase transient shape.

### F9 live-funds census (complete, 0 missing queries)

| Metric | Value |
|---|---|
| Instances | 376 |
| ETH-funded | **194 (51.6%)** |
| Total live ETH | **7.7870 (~$36.6K)** |
| USDC holders | 0 |

Pattern: ~190 instances hold exactly 0.012 ETH (uniform deposit/mint-fee fingerprint — an active protocol collecting per-user deposits), plus two 2.0 ETH instances, one 1.0 ETH, and `0xbce51130…02b5` (0.2 ETH) / `0x4d7abff0…079f` (0.1 ETH) outliers. **NOT drainable: all 194 funded instances have `slot5=1`, which disables the public sweep — see the correction above and `CA/FINDING_9_S2-38.md`.**
