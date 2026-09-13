# Campaign triage (rerun generation)

Generated 2026-09-13 10:28Z. Source: completed runs since 2026-09-12T14:40Z (sanity + full + resumes).

Live-gate: Kontrol failures are *model* reachability, not live exploits. `LIVE_REACHABLE` = funded + code present; still needs human review.

## Stage 1
- FAILED verdicts: **19**  ->  CONTROL_OR_UNMAPPED=1, DORMANT=16, LIVE_REACHABLE=2
- LIVE_REACHABLE:
  - `test_p1_c27_0` (P1_AUTH_WRITE) hash `0x13e2982407cb413d05650ff6e74a4337885fe3aab7e364be14637cb74f75b757` deploys=46 funded=3 coded=3
  - `test_p1_c27_1` (P1_AUTH_WRITE) hash `0x2e9882dd6faca9c9bded2892eca89b37296d2ffa127759641f16d2e93eac5515` deploys=31 funded=3 coded=3

## Stage 2
- FAILED verdicts: **7**  ->  LIVE_REACHABLE=2, DORMANT=5
- LIVE_REACHABLE:
  - `test_p4_c10_1` (P4_TWO_PHASE) hash `0x2bbdccaa35b0042c313f001f5c4a0ae141ba06dd8e4c10c7c261cba423e40369` deploys=3 funded=2 coded=2
  - `test_p4_c12_1` (P4_TWO_PHASE) hash `0x56a425069c0de5252925685a504238f58720a594d67cc899d320a507ed7a6a1a` deploys=3 funded=2 coded=2

## Stage 3
- FAILED verdicts: **10**  ->  CONTROL_OR_UNMAPPED=1, DORMANT=7, LIVE_REACHABLE=2
- LIVE_REACHABLE:
  - `test_p7_c24_0` (P7_PROFIT) hash `0xd2ca7fb94a6c1969318e98c6c9b57d96f2ab57dc13f56a40ea9ebedfefe698d4` deploys=7321 funded=3 coded=3
  - `test_p7_c3_0` (P7_PROFIT) hash `0x27c02a1a822222c2ad6a9a01021c98abf05dbe6d19540035756ef97697ed41d0` deploys=222108 funded=1 coded=1

## Notes
- Stage 3 is partial: several chunks were still running/queued at triage time.
- Enrichment (top instance, balances, guard slots) in each `stageN/instances.md`.
- Re-run: `python3 CA/scripts/triage_live.py --stage N --artifacts CA/artifact/stageN --out CA/triage/stageN/report.md`
