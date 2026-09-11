# Findings Harvest — Stage 1 Wave 1 + Stage 2 Deep-Auth (CI batches)

**Date:** 2026-09-11 · **Sources:** kontrol-stage1-sweep (Wave 1) + kontrol-stage2-deepauth
**Status:** all properties CONFIRMED violations by symbolic proof; live-funds triage pending for the new batch

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
