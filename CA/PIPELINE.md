# Pipeline Architecture (rebuilt 2026-09-11)

Replaces the ad-hoc `gen_probe.py` / `gen_stage2.py` + two bespoke workflows.
Goal: **no chaff** (no model-only "findings"), one public repo per stage,
comfortable use of GitHub's parallel runners, and a repeatable sanity gate.

## Why the old pipeline produced chaff

1. **Radar was contaminated by solc metadata.** The push-aware scanner decoded
   the compiler metadata trailer (`a165627a7a…` / `a26469706673…`) as code, so
   bytes `0x5c`/`0x5d` inside it fired `sig_transient`. F5–F8 had **no real
   TLOAD/TSTORE at all** yet were queued into the "SIR-shape" Stage-2 pool.
2. **Zeroed-storage proofs were read as live risk.** The harness zeroes slots
   0..7, which is a *favourable* state (F9 `slot5=0`, F4 `slot0=0`, F8 `slot1=0`).
   A FAIL proves reachability from that state, not from live state.
3. **No live check before recording a finding.** Funded census came later, and
   "funded" can include **codeless accounts** (F8 `0xd1c68218`).

## Fixes in this rebuild

| Layer | File | Change |
|---|---|---|
| Radar | `scripts/opcode_scan.py` | strip solc/vyper metadata trailer before scanning; new `has_metadata`, `code_size_eff` columns |
| Targets | `scripts/gen_stage.py` | unified per-stage selection; honest per-probe labels (`class`, `state_model`); controls always chunk 0; `--controls-only` needs no DB |
| CI | `.github/workflows/stage-matrix.yml` | reusable: plan → per-chunk matrix → resume → artifacts; `mode: sanity\|full` |
| CI | `.github/workflows/stage{1,2}-*.yml` | thin per-stage callers (one repo each) |
| Triage | `scripts/triage_live.py` | FAILED verdict → deployments → ETH funded → `eth_getCode` → guard slots → optional `eth_call`; classifies NO_DEPLOYMENTS / NO_CODE / DORMANT / LIVE_REACHABLE / LIVE_DRAIN |

## Repos (one per stage → 20 parallel jobs each)

| Stage | Properties | Repo |
|---|---|---|
| 1 | P1 unprotected write, P2 balance/selfdestruct | `kingmariano/kontrol-stage1-sweep` |
| 2 | P4 two-phase, P3 naive proxy | `kingmariano/kontrol-stage2-deepauth` |
| 3 | P5/P6/P7 math + profit oracle | `kingmariano/kontrol-stage3-math` (to create) |
| 0 | radar + triage + docs (no proofs) | `kingmariano/zany-xylophone` control tower |

## Workflow usage

```bash
# 1) sanity ("stage N.5"): controls only — MUST be green before the matrix
gh workflow run stage2-deepauth.yml -f mode=sanity
#    expect: VulnerableTransient FAIL, SafeTransient PASS,
#            NaiveProxy FAIL, SafeProxy PASS
# 2) full matrix
gh workflow run stage2-deepauth.yml -f mode=full
# 3) resume a giant's KCFG
gh workflow run stage2-deepauth.yml -f mode=full -f chunks=38 -f resume_run_id=<run>
```

Verdicts land as artifacts `stage<N>-results-chunk-<c>` (verdicts + prove log)
and `stage<N>-kcfg-chunk-<c>`. Download them, then run triage **locally** (needs
the DuckDB + RPC keys, which the runner does not have):

```bash
gh run download <run_id> -D /tmp/artifacts
python3 CA/scripts/triage_live.py --stage 2 --artifacts /tmp/artifacts
```

## Rules (do not regress)

1. **Sanity first.** Never fire a full matrix for a stage/property until its
   control chunk is green (STAGES.md operating rule).
2. **A FAIL is a candidate, not a finding.** Record a finding only after
   `triage_live.py` says `LIVE_REACHABLE`/`LIVE_DRAIN` *and* a human confirms the
   exact call sequence moves value to the attacker.
3. **One `kontrol prove` per test** so a timeout never erases verdicts.
4. **Check code presence** (`eth_getCode`) — funded addresses can be empty.
5. **Read the real guard slot(s)**, not the harness's zeroed state.

## /tmp volatility

`/tmp` (DuckDB 23.6 GB, docker image, swap) is lost on container rebuild. Run
`CA/scripts/recover.sh` to restore; the radar result is persisted at
`CA/data/opcode_features.parquet`, so a rebuild only needs re-ingesting
contracts/bytecodes + `CREATE TABLE opcode_features AS SELECT * FROM read_parquet(...)`.
