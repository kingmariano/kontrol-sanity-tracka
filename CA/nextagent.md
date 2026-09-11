# 🤝 nextagent.md — Campaign Handoff (write date: 2026-09-11, ~20:00 UTC)

> ## ⚠️ UPDATE 2026-09-11 ~21:30 UTC (next agent)
> **F9 (§2 row 9, §3) is NOT a live zero-day.** The proven drain requires
> `slot5 == 0`, but all 194 funded instances have `slot5 = 1`; `0x0b5ab3d5`
> reverts `InvalidJump` on them (verified via `eth_call`), and a `slot5=0`
> state-override makes it succeed. The payout address is `slot2` (a third-party
> EOA), never the caller. Machine-checked in `CA/poc/` (5/5 tests).
> Full analysis: **`CA/FINDING_9_S2-38.md`**. See §9 below.
>
> Also: Stage 2 run completed → `rerun-failed-jobs` POSTed (HTTP 201, queued).
> Stage 1 chunks 12–15 were failing instantly because the in-flight run's SHA
> predates those files → new dispatch **34649498066** (chunks 12–15) queued.

Read this fully before acting. It is the complete state of the smart-contract
zero-day audit campaign. You are continuing an ongoing operation; the human
operator ("the user") is actively directing it in chat.

---

## 0. Mission (from the very beginning)

Hunt **permissionless zero-day vulnerabilities** (any EOA, only calldata needed)
across **all 69,788,231 deployed Ethereum contracts** (Zellic dataset:
69.8M deployments / 1,539,858 unique bytecodes) using **Kontrol symbolic
execution** (KEVM-based; docker image `runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255`)
with an etch + setArbitraryStorage-style harness, organized as staged CI
proof-matrices, triaged via a **radar → proof → census → live-funds** pipeline.

**Zero-day bar:** a stranger with an EOA and the model's calldata can drain a
live contract; the Kontrol counterexample is the machine-checked receipt.

**Iron rule (user decision): ALL new proof batches run in CI public repos —
never locally.** Each repo gets 20 parallel CI jobs. /tmp is volatile.

---

## 1. Pipeline stages (all built, working)

| Stage | What | Status |
|---|---|---|
| 0 — Radar | opcode scan (push-aware) over 69.8M contracts → `CA/data/opcode_features.parquet` (69.5MB, on GitHub) | ✅ done |
| 1 — Cheap sweep | P1 (`sstore` no auth) / P2 (`selfdestruct` reachability), 40 targets → 5k planned | 🔄 Wave 1 8/16 chunks done; rerun in flight |
| 2 — Deep auth | P4 two-phase transient (SIR-class) + P3-lite proxy; 49 chunks / 84 targets | 🔄 34+ success, 8 cancelled (rerun pending), rest in flight |
| 3 — Math/profit | P5/P6/P7 (AMM rounding, profit oracle) | later |
| 2.5 | selector-DB interface recovery (4byte.directory) for calldata shaping | planned |
| 4 — 7702 | P8 delegate accounts | n/a |

Property templates P1–P8 are defined in `CA/STAGES.md` with case studies
(SIR, Balancer, SWEAT, Cetus, SCONE-bench) in `CA/ZERO_DAY_RESEARCH.md`.

### Harness conventions (v4.2, battle-tested — do not change)
- Foundry project per repo from `CA/harness/skeleton/` (forge-std + kontrol-cheatcodes in `lib/`).
- Test files: `vm.etch(target, hex"<runtime bytecode>")`, `vm.deal(target, 1 ether)`,
  slots 0–7 zeroed via `vm.store`, `vm.prank(attacker)` with **symbolic attacker**,
  symbolic calldata args. One `kontrol prove --match-test '<Contract>.<test>'`
  invocation per test, `--auto-abstract-gas --workers 2`, verdicts flushed to
  `verdicts_chunk_N.txt` per test, KCFG checkpoints uploaded as artifacts
  (resume via `resume_run_id` input + `gh run download`).
- chmod dance between tests (container uid 1010 vs runner): `sudo chmod -R a+rwX .`
- CONTROL tests must hold: VulnerableTransient → FAILED, SafeTransient → PASS,
  NaiveProxy → FAIL. If controls break, the run is void.

---

## 2. FINDINGS LEDGER (9 findings; scoreboard 8 confirmed + 1 in re-proof)

Full details in `CA/FINDINGS_HARVEST.md`, `CA/FINDINGS_BATCH1.md`,
`CA/FINDING_2_c1_1.md`, `CA/FINDING_3_c0_2.md`, `CA/BREAKDOWN_F4_F8.md`,
`CA/CENSUS_LIVE_FUNDS.md`.

| # | Bytecode hash | Ops | Deploys | Key selectors | Verdict | Live funds |
|---|---|---|---|---|---|---|
| 1 | batch1 (`FINDINGS_BATCH1.md`) | — | 144 | — | CONFIRMED | dormant |
| 2 | `0x038cfd30…80ca497` | 412 | 10,029 | `0x19ab453c` | CONFIRMED | not censused |
| 3 | `0xf9e2d368…0ba1907` | 509 | 19,130 | `0xf09a4016` | CONFIRMED | not censused |
| 4 | `0x1cf5a0fe…4da3aaf3` | 568 | 1,352 | TBD (ecrecover auth) | **SUSPECT — kore crash** → re-proof RUNNING | **$2,112.55 USDC + 5.5695 ETH** (103 USDC holders, 818 ETH-funded) |
| 5 (S2-6) | `0xa24e966a…cada59` | 436 | 4,374 | `0x44439209` | CONFIRMED (priv-addr install) | dust only |
| 6 (S2-10) | `0x6f83343a…4c534df0` | 752 | 3,004 | prime `0x6b9f96ea` → drain `0x00821de3` | CONFIRMED (primable drain) | dormant |
| 7 (S2-13) | `0x3b7d6f59…5e904a06` | 264 | 2,116 | `0x6b9f96ea` both phases | CONFIRMED (prime=0 trivial) | dormant |
| 8 (S2-23) | `0x1aba7e71…4307e3d9` | 972 | 971 | `0x19ab453c` both phases | CONFIRMED (SIR-shape) | **47.0 USDC on flagship** |
| **9 (S2-38)** | `0x8824fcf9…2a971c8a` | ~1142B | **376** | `0x05b34410`, `0x0b5ab3d5`, +8 more | property violation (slot5=0 model) — **LIVE EXPLOIT REJECTED** | 194/376 funded but **all slot5=1 → sweep reverts; payout is slot2, not attacker** (`FINDING_9_S2-38.md`) |

### Key instance addresses (copy-paste)
```
# F8 flagship (holds 47.0 USDC, verified 3 ways, NOT yet exploited — zero outgoing USDC transfers ever)
0x3952fe747D6967b3Cf53A84593a95114E7De3201
# F4 top USDC holder (1,046 USDC) / verified SmartAccountProxy family sample
0x91d53f76dde0b809eea80e0969d5625e07def10b
0xf040b7c786a90852bf387D3Afc81d4E627236D24
# F9 largest funded instances (USER IS DECOMPILING THESE ON DEDAUB — unverified code)
0xbce5113025fecc7b6e3118ea043e5ba7492c02b5   (0.2 ETH)
0x4d7abff0967ccc9f9a66d7b1da61d8440f0c079f   (0.1 ETH)
0x3fe9a9fe7e6016ce82f58373db739b6d6cb3e876   (0.012 ETH — the ~190-instance uniform pattern)
# F5 inspectable: 0x676e1c7b4b297ce36706eacdfe6d7fb93e0211de
# F6 inspectable: 0x049369551ad83b3c76b0dc58c26b06a335e41dae
# F7 inspectable: 0x0b371778885b6fc9bf12eccf41f2ae9eb9c563f6
```

### Census summary (all queries verified, 0 missing)
F5: 2/4374 ETH (dust), 0 USDC · F6/F7: fully dormant · F8: 8 ETH-funded,
4 USDC holders (47.2 USDC) · F4: 818 ETH-funded (5.57 ETH), 103 USDC (2,112.55) ·
F9: 194 ETH-funded (7.787 ETH), 0 USDC. Raw CSVs: `CA/data/census/`.

---

## 3. F9 DEEP-DIVE — RESOLVED: not a live zero-day (see `FINDING_9_S2-38.md`)

**Outcome (next agent):** the PoC was built at `CA/poc/` and the open question is
answered. The recipient is `slot2`; the sweep is enabled only when `slot5 == 0`;
all funded instances have `slot5 = 1` → `InvalidJump`, no drain. The disassembly
below is correct and retained for reference.

User asked for a **realistic Foundry PoC in a `poc/` folder** draining the full
7.787 ETH to an attacker EOA. Work started: the runtime bytecode (1,142 B) was
disassembled. Findings so far:

- Dispatcher with 10 selectors: `0x05b34410`, `0x0b5ab3d5`, `0x13af4035`,
  `0x2b20e397`, `0x3fa4f245`, `0x674f220f`, `0x8da5cb5b`, `0xbbe42771`,
  `0xfaab9d39`, `0xfb1669ca`.
- **Owner gate** at 0x3cc(972)/0x384(900)/0x2d8(728): `SLOAD(0) == CALLER`,
  else **silent no-op** (jumps to dispatcher start → STOP, does NOT revert).
- `0xfaab9d39` → transferOwnership: owner-gated `SSTORE(slot0, arg)`.
- `0x13af4035` → owner-gated **sets slot2 AND slot3** (address fields) with
  event topic `0xa2ea9883…` (recipient update).
- `0x2b20e397` → returns slot0 (owner). `0x8da5cb5b` → returns slot2.
  `0x674f220f` → returns slot3. `0x3fa4f245` → returns slot4 (uint).
  `0x05b34410` → returns slot1 (getter, **no auth** — the "prime" arg in the
  model was actually unused; the model's prime=0 was the getter's arg).
- **`0x0b5ab3d5` — THE DRAIN (NOT owner-gated):** checks `SLOAD(5) & 0xff == 0`
  (inverted JUMPI: proceeds only when slot5 == 0, i.e. unclaimed), then
  `CALL` sends **the contract's ENTIRE balance to `SLOAD(2)`** (recipient slot).
  If the CALL fails → `SELFDESTRUCT(0x…dead)`.
- `0xbbe42771` → owner-gated claim path (slot5 flag set, CALL payout, event
  topic `0xbb2ce2f5…`) — not fully stack-simulated yet.
- **Model reconciliation:** in the harness slots 0–7 are zeroed → slot5==0
  (gate passes) and slot2==0x0 → `0x0b5ab3d5` alone drains the full balance
  **to the zero address**. That's why the counterexample needed only selB
  (selA was a no-op getter).
- **OPEN QUESTION — RESOLVED (no Dedaub needed):** live storage reads show
  slot0=owner contract `0x012233b3…` (fixed), slot2 ∈ {0x0, `0x5fc8a61e…`,
  `0x4811e699…`, `0x5c19cf6b…`} (third-party EOAs, owner-set only), and
  **slot5=1 on all 194 funded instances**. `0x0b5ab3d5` requires slot5==0, so it
  reverts (`InvalidJump`) on every funded instance; a state-override to slot5=0
  makes it drain — to slot2, not the caller. **F9 is not attacker-profitable.**
- **PoC — DONE:** `CA/poc/` Foundry project (5/5 tests) with (a) deterministic
  etch tests replicating the counterexample and (b) mainnet-fork tests proving
  the live gate (`FINDING_9_S2-38.md`). Commit to the repos.

---

## 4. INFRA — API keys & the silent-failure lessons (READ THIS)

Keys live in `CA/.env` (gitignored). Status as of handoff:
- **Alchemy (new)**: WORKS (user rotated 2026-09-11). Old one was revoked.
- **ETHERSCANV2_API_KEY**: WORKS — best ETH path (`balancemulti`, 20 addr/call, 5 rps).
- **dRPC**: WORKS again (earlier "expired" was transient) — but **free tier
  silently 403s JSON-RPC BATCHES** (single calls fine).
- **BlockPI**: HTTP single calls fine; HTTP batches 403; **WSS pipelining WORKS (~50 rps with pacing + error-retry)** — best USDC path.
- **INFURA, ANKR: DEAD. GITHUB_API_KEY: user says re-rotated (verify before use).**
  Fallback for GitHub API: `git credential fill` token works for pushes/API reads.
- Dune API key exists (in .env, user pasted in chat — should be rotated); CLI at
  `/home/codespace/.local/bin/dune` (`dune query run-sql --sql "..." -o json`);
  `tokens_ethereum.balances` view is BROKEN server-side.

**Silent-failure horror stories (do not repeat):**
1. Alchemy retry-storm dropped responses → census reported all-zeros. Caught
   ONLY because the user manually checked Etherscan and found the F8 flagship
   still holding 47 USDC.
2. dRPC batch 403s defaulted every USDC balance to 0 in two full sweeps.
3. Rule: every sweep MUST carry a ground-truth assert (e.g. flagship == 47e6)
   and report a MISSING count; never default failures to zero.

Working sweep scripts (in `CA/scripts/`): `es_eth_sweep.py` (Etherscan ETH),
`wss_usdc_sweep.py` (BlockPI WSS USDC, queue-retry), `drpc_usdc_sweep.py`,
`balance_sweep.py` (deprecated). F9-only copies in /tmp are ephemeral.

---

## 5. LIVE WORKFLOWS (state at handoff — POLL THESE FIRST)

| Repo | Run | What | State |
|---|---|---|---|
| `kingmariano/kontrol-stage1-sweep` | 34592498729 | Wave 1 rerun chunks 2,6,7,10 (those files exist at the old SHA); **chunks 12–15 failed instantly because the old SHA lacks them** | in_progress (4 jobs) |
| `kingmariano/kontrol-stage1-sweep` | **34649498066** | NEW dispatch (2026-09-11 21:27) for chunks 12–15 on current `main` | queued |
| `kingmariano/kontrol-stage2-deepauth` | 34602954273 | run completed: 34 success / 15 cancelled → **`rerun-failed-jobs` POSTed (HTTP 201, queued)** | rerun queued |
| `kingmariano/kontrol-f4-reproof` | **34639568835** | F4 kore-crash re-proof, 3 solver regimes: default (depth 1000/smt 10s), shallow (250/5s), smtheavy (2000/60s) × 4 tests (p4_two_phase, p1_sstore_no_caller, p7_drain_oracle, VulnerableTransient CONTROL-must-FAIL) | in_progress |

Poll commands:
```bash
GK=$(grep '^GITHUB_API_KEY=' CA/.env | cut -d= -f2- | tr -d '"')
curl -s -H "Authorization: Bearer $GK" \
  "https://api.github.com/repos/kingmariano/<repo>/actions/runs?per_page=5"
# artifacts: .../actions/runs/<id>/artifacts ; download zip via
# .../actions/artifacts/<artifact_id>/zip ; verdicts are inside probe/verdicts_*.txt
```
Artifact naming: stage1 `probe-results-chunk-N`, stage2 `stage2-results-chunk-N`,
f4 `f4-reproof-<variant>` + `f4-kcfg-<variant>`.
**Stage 2 rerun is now POSTed** (`rerun-failed-jobs`, HTTP 201, queued) for its 15
cancelled chunks. Poll it; when it lands, harvest FAILED verdicts.
Watch for more FAILED chunks (F9 was found this way — chunk 38, test_p4_w39) —
**but before calling any balance-drain a live risk, read the real guard slot(s)
via `eth_getStorageAt`** (F9 lesson: the proof ran with storage zeroed).

### F4 re-proof decision matrix (when run 34639568835 lands)
- FAILED with model on p4/p1/p7 → F4 = CONFIRMED, drain calldata in hand → escalate.
- shallow PASSED where default crashed → depth-induced crash → F4 downgraded.
- CONTROL (VulnerableTransient) must FAIL, else run void.
- All INCOMPLETE/kore-crash again → next escalation: concrete-signature etch
  (fix sig bytes to attacker-signed valid sig, prove rest symbolically) or
  split into P1 slot-writability + P7 balance-drain claims.

---

## 6. USER'S STATED PLAN / DIRECTIVES (chronological)

1. ✅ Full-census balance triage with API keys (done for F4–F8, F9).
2. ✅ F4 kore-crash re-proof in a **new public repo CI** (done — run live).
3. ✅ F8 kept as-is (proof already clean; no rework).
4. ✅ Bug breakdowns of F4/F8 written (`CA/BREAKDOWN_F4_F8.md`).
5. ✅ Poll Stage 1 + Stage 2 → harvested → **found F9**.
6. ✅ **DONE: Foundry PoC built at `CA/poc/`** — but the honest result is that
   the 7.787 ETH is **NOT drainable**: all funded instances have slot5=1 and the
   payout is slot2. See §3 and `FINDING_9_S2-38.md`. **The "drain to attacker"
   objective is not achievable; do not pursue it further.**
7. ✅ F9 question resolved from live storage (no Dedaub needed): slot0=owner
   contract, slot2=third-party recipient, slot5=1 gate. **Next: apply the same
   guard-slot check to F4/F6/F7/F8 before any live-funds claim.**
8. **Wave 2 (P1b/P2b value-write-sensitive properties) fires when Wave 1
   completes** — add `--wave` flag to `CA/scripts/gen_probe.py` (user-confirmed directive).
9. Stage 2.5: selector-DB interface recovery (4byte.directory) for calldata shaping.
10. Policy: everything runs in CI public repos; every batch/findings/census is
    committed to ALL THREE remotes (`origin`=kingmariano/zany-xylophone
    control tower, `sweep`=kontrol-stage1-sweep, `stage2`=kontrol-stage2-deepauth, main).
11. User likes per-step verification ("make sure everything is working end to
    end") and frequent rich status tables.

---

## 7. REPO / FILE MAP

- Control tower: `/workspaces/codespaces-blank/CA/` (all remotes share history)
- Docs: DATASET.md, KONTROL.md, KONTROL_SETUP.md, STAGES.md, ZERO_DAY_RESEARCH.md,
  FINDINGS_HARVEST.md (ledger + F9), FINDINGS_BATCH1.md, FINDING_2_c1_1.md,
  FINDING_3_c0_2.md, BREAKDOWN_F4_F8.md, CENSUS_LIVE_FUNDS.md, RADAR.md (data/)
- Harness: `CA/harness/skeleton/` (foundry+kontrol project), `CA/harness/src/Controls.sol`,
  `CA/harness/src/Stage15Controls.sol`, `CA/harness/generated/` (16 Stage-1 chunks),
  `CA/harness/generated2/` (49 Stage-2 chunks + manifest)
- Generators: `CA/scripts/gen_probe.py` (stage-1 chunker, needs `--wave` for Wave 2),
  `gen_stage15.py`, `gen_stage2.py`, `import_features.py`, `export_radar.py`,
  `opcode_scan.py`, `ingest.py`+`finalize.py` (rebuild DB; finalize handles a
  known NULL-hash assert), `recover.sh` (idempotent environment recovery — run first after any /tmp wipe)
- Local DB: `/tmp/eth-contracts/eth_contracts.duckdb` (23.6GB; tables
  contracts/bytecodes/opcode_features; bytecodes PK = `bytecode_hash`, code column = `bytecode`)
- Workflows: `.github/workflows/kontrol-proof-matrix.yml` (v4.2, stage 1),
  `kontrol-stage2-matrix.yml`; f4 repo has its own `kontrol-f4-reproof.yml`

## 8. QUICK FACTS FOR ORIENTATION

- Git pushes work via credential helper even when GITHUB_API_KEY is stale.
- Kontrol docker mount pattern: `-v "$PWD":/work/probe -w /work/probe` + chmod dance.
- Bytecode → disassembly: use the inline Python EVM disassembler pattern from
  this session (push-aware, handles PUSH0 as UNK on old image) — or Dedaub.
- F9 selector→handler map + owner-gate semantics are in §3; slot map:
  0=owner, 1=uint(getter 0x05b34410), 2=recipient-A, 3=recipient-B,
  4=uint threshold/counter, 5=claimed-flag(&0xff).
- ETH ≈ $4,700/ETH assumed in estimates.

## 9. LIVE-GATE RE-CHECK (2026-09-11, after the F9 correction)

Full write-up: **`CA/LIVE_GATE_RECHECK.md`**. Result: **no live-exploitable
permissionless drain in F4–F9.**

| Family | Guard | Funded | Live guard state | Verdict |
|---|---|---|---|---|
| F4 proxy | `slot0==0` to `initialize` | 873 | **873/873 `slot0!=0`** | rejected |
| F5 `setSpender` | `CALLER==0x65b0bf8e…` (hardcoded) | 2 dust | gate constant | rejected |
| F6 | — | 0 | — | dormant |
| F7 `flush()` | none (pays fixed `destinationAddress()`) | 0 | — | dormant |
| F8 `init` | `slot1==0` | 9 | **8/8 code-bearing `slot1!=0`; 9th codeless** | rejected |
| F9 `sweep` | `slot5&0xff==0` | 194 | **194/194 `slot5=1`** | rejected |

PoC: `CA/poc/` (8/8 tests pass with `MAINNET_RPC_URL`). New methodology rules:
(1) read the real guard slot before any "funds at risk" claim; (2) `eth_getCode`
each funded address (codeless census entries exist — F8 `0xd1c68218`); (3) the
`sig_transient` radar is contaminated by solc metadata trailers (`0x5c/0x5d` in
`a165627a7a…`/`a26469706673…`) — strip metadata before re-scanning Stage 2;
(4) hardcoded-address gates (F5) are P1 false positives.

— end of handoff —
