#  nextagent.md — Track A Handoff (written 2026-09-15)

> **UPDATE 2026-09-15 (Track A full-matrix implementation).** The §5 "BROKEN
> STATE" is **resolved**. `ProbeBaseA` builds green; the v2 controls are pinned by
> a concrete `test/TrackASanity.t.sol` (12/12); `gen_track_a.py` is rewritten to
> the ProbeBaseA API and emits per-class chunks (controls + full sweep); CI now
> has `tracka-generate.yml` (duckDB + extended features + scanners + chunk gen)
> and per-class `tracka-a{1,2,5,6,7,9}.yml` callers over `stage-matrix.yml`
> (`src_run_id` + `wave` support); `resume-watchdog.yml` is Track-A-only with
> stuck-run cancel + next-wave follow. See `CA/TRACK_A_PROPERTIES.md` →
> "Where we are (2026-09-15)" for the authoritative status.

> **READ THIS FULLY BEFORE ACTING.** It is the current state of the campaign +
> the exact broken/next steps from the previous agent's session.
> The previous agent (this file's author) hit a tool-call malfunction mid-session
> and could not finish; the work is **partially applied**. See §5 "BROKEN STATE".

---

## 0. MISSION (unchanged from the very beginning)

Hunt **permissionless zero-day vulnerabilities** (any EOA, calldata-only) across
**69,788,231 deployed Ethereum contracts** (Zellic dataset) using **Kontrol
symbolic execution**, organized as staged CI proof-matrices, triaged via
**radar → proof → census → live-funds**.

**Zero-day bar:** a stranger with an EOA + the model's calldata can drain a live
contract; the Kontrol counterexample is the machine-checked receipt.

### IRON RULES (non-negotiable — user has repeated these many times)
1. **NEVER run Kontrol or docker locally.** Every Kontrol/docker job runs as a
   **GitHub Actions CI workflow**. "No matter how small the work is, as long as it
   involves Kontrol or docker, run it in GitHub Actions — I am on a 2-core machine
   so my CPU gets filled up quickly."
2. **Local `forge build` / `forge test` IS allowed** (no docker). Use it to shape
   and sanity-check proofs before CI.
3. `/tmp` is volatile (wiped on recycle). The huge DB
   (`/tmp/eth-contracts/eth_contracts.duckdb`, ~23.6 GB) is **reproducible** via
   `CA/scripts/recover.sh` (which DOES use docker — only run it in CI or when the
   user accepts it; normally the parquet on GitHub is enough).
4. Every batch / finding / census gets committed to the relevant repo(s).
5. The user likes **per-step verification end-to-end** and rich status tables.
6. This is a **2-core Codespaces, disk ~90% full**. Do not download huge datasets
   locally. Never delete `~/.local/share/opencode` (live session DB) without asking.

---

## 1. WHAT HAS ALREADY HAPPENED (context)

- **Main campaign (stages 1/2/3) is STOPPED and fully triaged.** Cancelled
  in-flight runs; disabled `resume-watchdog`, `stage1-cheap`,
  `stage2-deepauth`, `stage3-math` on all 5 repos. Zero non-completed runs.
  Net result: **1 real live finding** (CollectionBeaconProxy
  `setFinalImplementation`, `test_p1_c27_1`) + FPs. Details in
  `CA/triage/RETRIAGE.md`, `CA/triage/stage1/AUDIT.md`.
- **Resolv protocol audit is DONE and was DELETED this session** at the user's
  request (`CA/protocols/resolv/` removed; `CA/protocols/` removed). Its final
  state: run `34900452514` = **68 PASS / 0 FAIL / 2 INCOMPLETE**; FINDING-OFT-01
  (`SimpleOFTAdapter` missing `_disableInitializers`) was the only finding.
  NB the persistent **Kontrol knowledge base `CA/kontrol/` was KEPT** (it is tool
  knowledge, not protocol files) — it still cites Resolv examples.
- **Disk cleanup done this session:** removed ~1.2 GB unused VS Code extensions
  (openai.chatgpt, markdown-pdf+chrome, web-dev snippets), uv python cache, npm
  cache, copilot cache. Deleted Resolv dir + `/tmp/rv4|rv5|rv6|kcfg`. (Freed
  space may only show after a VS Code Reload Window, as deleted extension files
  are held open by the VS Code server.)
- **The `nextagent.md` you are reading replaced the old main-campaign handoff**
  (old content: F4–F9 findings ledger, census, live-gate recheck). If you need
  that, the underlying docs still exist: `CA/FINDINGS_HARVEST.md`,
  `CA/FINDING_*.md`, `CA/CENSUS_LIVE_FUNDS.md`, `CA/LIVE_GATE_RECHECK.md`,
  `CA/STAGES.md`, `CA/ZERO_DAY_RESEARCH.md`, `CA/VULN_CLASS_RESEARCH.md`.

---

## 2. CURRENT WORKSTREAM: **TRACK A** (the user's active directive)

Track A = the **sweepable permissionless-drain classes** that a zeroed/arbitrary
storage, ABI-agnostic bytecode probe can actually reach. Spec = **`CA/TRACK_A_PROPERTIES.md`**.

| Stage | Class | Template | Sweepable? |
|---|---|---|---|
| A1 | unprotected initialize / reinitialize | SINGLE | ✅ |
| A2 | unprotected upgrade / attacker-controlled impl slot | SINGLE | ✅ |
| A5 | multicall / batch `msg.value` reuse | VALUE | ✅ |
| A6 | fee-on-transfer / manipulable accounting | SINGLE | ✅ |
| A7 | unchecked external call still advancing state | SINGLE | ✅ |
| A9 | unauthenticated pull (attacker-named payer) | UNAUTH_PULL + ConsentToken | ✅ |
| A3 | signature / permit replay | needs SIGNER template | ❌ → Track B |
| A4 | rounding / round-trip inflation | multi-party, symbolic-amount mul | ❌ → Track B |
| A8 | hostile callback / reentrancy | needs concrete etched counterparty | ❌ → Track B |

Each stage MUST ship a **chunk 0 control gate** (`mode: sanity`) that is green
before the full matrix fires: a MUST_FAIL and a MUST_PASS control with the **same
shape**, differing only by the class bug.

User's explicit goals for this Track A build (verbatim intent):
- "setup/harness **much better than the previous stage1/2/3 which had different lapses**";
- "**implement all those properties robustly**";
- "**commit all the workflow to my main GitHub account (kingmariano)**";
- "**watchdogs implemented effectively**".

---

## 3. THE KONTROL KNOWLEDGE BASE — USE IT, DON'T REDISCOVER

**`CA/kontrol/`** (11 files) is the compaction-proof memory. Read it first:
`README.md`, `01-ecosystem-architecture.md`, `02-build.md`,
`03-prove-cli-flags.md`, `04-cheatcodes.md`, `05-kcfg-and-diagnosis.md`,
`06-lemmas-advancing-proofs.md`, `07-performance-and-cse.md`,
`08-lessons-from-our-campaigns.md`, `09-property-authoring-playbook.md`,
`10-config-snippets.md`.

Highest-value gotchas (ground truth for pinned `1.0.255`):
- **`bound()` is NOT modelled by Kontrol → always use `vm.assume(...)`.**
- **Inline state-variable initializers read as ZERO** under Kontrol
  (`address internal alice = address(0xA11CE);` was `0`). Fix: `address internal
  constant`, or assign in `setUp()`. (This caused 27 spurious FAILs in Resolv.)
- **Symbolic addresses branch 3-way**; kill it with `vm.assume(addr != address(this));
  vm.assume(addr != address(vm)); vm.assume(addr != <each deployed>);`.
- **Verdict classification (no FP / no FN):** `PROOF PASSED` → pass; `PROOF FAILED`
  with a concrete status code + reproducing model → REAL; blank status code +
  `#And { a0 == #address( FoundryCheat ) }` → **CHEATCODE FP**; `step exceeded …
  cannot shrink further; stopping` + `PENDING:` → **ABORT/INCOMPLETE**; `rc=124`
  (wall timeout) / `rc=137` (OOM/SIGKILL) → **INCOMPLETE**; revert on a state that
  passes concretely at the model values → **SPURIOUS** (see inline-init bug).
- **Always decode `<output>`** (revert selector) from the KCFG node JSON.
- CI mechanics: proof dirs contain `:` → **tar the KCFG dir before upload**;
  `chmod -R a+rwX .` **before build and before every prove** (root container vs
  runner uid); `kontrol prove` 1.0.255 has **no `--match-contract`** → drive a
  per-test loop from `tests/<Suite>.tests`.
- Recommended prove flags (used by our workflows):
  `--use-booster --no-break-on-calls --no-stack-checks --no-log-rewrites
  --max-frontier-parallel 2 --max-depth 50000 --max-iterations 100000
  --smt-timeout 30000 --smt-retry-limit 2 --workers 2 --step-timeout 600
  --auto-abstract-gas`.

---

## 4. EXISTING TRACK A INFRASTRUCTURE (all in `CA/`)

### 4.1 Harness
- `CA/harness/skeleton/` — foundry + kontrol project (forge-std in `lib/`,
  `kontrol-cheatcodes` in `lib/`). `foundry.toml` pins **solc 0.8.24, evm_version
  cancun**. `kontrol.toml` present.
- **Old** `src/ProbeBase.sol` — stage1/2/3 harness. Etches an embedded
  `MockERC20` runtime at USDC/WETH/USDT/DAI and checks ONLY counter slots 0/1/2
  (`transferCount`,`lastTo`/`lastSpender`). Blanket checks over slots 0..15.
- `src/ConsentToken.sol` — real mapping-backed ERC-20 with **fixed slots**:
  `0 balanceOf`, `1 allowance`, `2 transferCount`, `3 lastFrom`, `4 lastTo`,
  `5 lastAmount`. Interface `IConsentToken`. (Keccak-free observation via slots 2/3/4.)
- `src/TrackAControls.sol`, `src/TrackAValueControls.sol` — old controls (see §5).
- Other controls: `src/Controls.sol` (VulnerableControl/SafeControl),
  `src/Stage15Controls.sol` (transient + naive proxy), `src/Stage3Controls.sol`
  (profit/amplify).
- `CA/harness/controls/*.hex` — compiled control **runtime** bytecode consumed by
  the generators via `vm.etch(target, hex"…")`. List includes
  `VulnerableInit/SafeInit`, `VulnerableUpgrade/SafeUpgrade`, `VulnerableFee/SafeFee`,
  `VulnerableUnchecked/SafeUnchecked`, `VulnerablePull/SafePull`,
  `VulnerableValue/SafeValue`, `ConsentToken`, `MockERC20`, `KillerImpl`,
  `NaiveProxy/SafeProxy`, `VulnerableControl/SafeControl`,
  `VulnerableTransient/SafeTransient`, `VulnerableProfit/SafeProfit`,
  `VulnerableAmplify/SafeAmplify`. **These are currently STALE** (see §5).
- `CA/harness/stages/stage{1,2,3}/` — stage sweep chunks + `chunk_*.tests` +
  `manifest.json`.
- `CA/harness/stages/stagetracka_batch{1,2,3}/` — **control-only** chunks
  (`Stage…Chunk_0.sol`, `chunk_0.tests`, `manifest.json`). No real sweep targets yet.

### 4.2 Generators / tools (`CA/scripts/`)
- `gen_stage.py` — unified per-stage target generator. Reads the DuckDB
  `opcode_features` (gone locally after /tmp wipe) or `--from-manifest` from an
  existing `manifest.json`. Templates: `SINGLE`, `TWO_PHASE`, `MULTI`, `PROXY`,
  plus `HDR`/`SETUP`/`CHECKS`. **These templates target the OLD `ProbeBase` API**
  (`_etchTokens`, `_checkTokens`, inline slot checks) — they must be rewritten for
  the new `ProbeBaseA` API (§5/§7).
- `gen_track_a.py` — Track A control-only generator. `--batch 1` (A1/A2/A6/A7 via
  `gen_stage.SINGLE`), `--batch 2` (A9 via `UNAUTH_PULL` template + ConsentToken),
  `--batch 3` (A5 via `VALUE` template). Reads `harness/controls/<Name>.hex`.
- `build_controls.py` — **NEW this session** (see §5): runs `forge build` and
  extracts `out/**/<Name>.json → deployedBytecode.object` into
  `harness/controls/<Name>.hex`, for every control/token name.
- `recover.sh` — idempotent recovery (DB+features+harness). Uses docker; CI only.
- `triage_live.py`, `triage_enrich.py` — offline live-gate triage (DuckDB + RPC).
- `hf_sync.py`, `import_features.py`, `export_radar.py`, `opcode_scan.py`,
  `ingest.py`, `finalize.py`.

### 4.3 Scanners + target universes (`CA/scanners/`, `CA/data/stages/`)
- `scanners/common.py` — shared metadata-stripped, push-aware disassembly +
  feature cache (`data/stages/features_ext.parquet`).
- `scanners/scan_a{1..9}_*.py` — per-class candidate scanners.
- `CA/data/stages/a{1..9}_*_targets.json` — the candidate universes; schema:
  `{stage, note, matched_bytecodes, matched_deployments, targets:[…]}`.
  Scanner yield (bytecodes/deployments), per `TRACK_A_PROPERTIES.md`:
  A1 39,130/475,534 · A2 18,031/1,605,663 · A3 18,990/435,167 · A4 2,460/2,655 ·
  A5 4,260/5,482 · A6 73,429/95,500 · A7 96,800/8,629,770 · A8 25,435/47,336 ·
  A9 9,828/14,621.

### 4.4 CI workflows (in the repos; `sanctracka` = `kingmariano/kontrol-sanity-tracka`)
- `.github/workflows/stage-matrix.yml` — **reusable** matrix. `plan` derives
  chunk list from `CA/harness/stages/stage<stage>/manifest.json` (or explicit
  `chunks`); `mode: sanity` = chunk 0 only. Per-chunk job (`max-parallel: 20`,
  `timeout-minutes: 350`) does: materialize `probe/` from
  `harness/skeleton/` + copy the chunk `.sol` → optional KCFG resume via
  `resume_run_id` + `gh run download` → `kontrol build` (docker) → **per-test
  prove loop** with `timeout -k 30s <budget>` and `--match-test <bare name>` →
  writes `verdicts_chunk_N.txt` (explicit line per test; timeout → `INCOMPLETE`)
  → `tar -czf kcfg_checkpoint.tgz -C out proofs || true` → `exit 0` → uploads
  `stage<stage>-results-chunk-N` (verdicts + logs) and
  `stage<stage>-kcfg-chunk-N`.
- `.github/workflows/tracka-batch{1,2,3}.yml` — thin callers
  (`stage: tracka_batchN`, `mode: sanity|full`, `chunks`, `resume_run_id`).
- `.github/workflows/resume-watchdog.yml` — self-healing. Triggers: `workflow_run`
  (completed), `schedule */30`, `workflow_dispatch{dry_run}`. For each caller it
  finds chunks whose verdicts are missing/`INCOMPLETE` and re-dispatches with
  `resume_run_id` + the KCFG checkpoint. Guards: overlap (skip busy chunks),
  runaway cap (≤8 runs/6h), progress guard (stop if incomplete set did not shrink
  vs the previous same-`head_sha` run).
- Also present: `stage1-cheap.yml`, `stage2-deepauth.yml`, `stage3-math.yml`
  (main campaign; currently disabled on the repos).

---

## 5. ️ BROKEN STATE — WHAT THIS SESSION CHANGED AND WHAT IS NOT FINISHED

The previous agent wrote the improved harness + controls + build script, but the
**build is currently RED** and the changes are therefore **not committed**. Nothing
was pushed. Recover as follows.

### 5.1 New files written this session (present on disk)
1. **`CA/harness/skeleton/src/ProbeBaseA.sol`** — NEW Track A harness v2. Design:
   - Etches `ConsentToken` (deployed via `new` in `setUp`) at USDC/WETH/USDT/DAI.
   - **Keccak-free** token observation via ConsentToken fixed slots
     (`TK_TRANSFER_COUNT=2`, `TK_LAST_FROM=3`, `TK_LAST_TO=4`) — avoids symbolic-keccak blowup.
   - `NSLOTS = 32` (better than stage1/2/3's 15).
   - Selectable state model: `_seedZeroed(target)` (fast, comparable) vs
     `_seedSymbolic(target)` = `vm.setArbitraryStorage(target)` (sound; catches
     writes that store zero and closes the "favourable zero state" FN).
   - `_assumeAttacker(attacker,target)` centralised; excludes `0`, `>0xff`, HEVM,
     console, `address(this)`, `address(vm)`, target, the 4 tokens, and `ADMIN`.
   - `ADMIN = address(0xA11CE)` role used by MUST_PASS controls.
   - Checks: `_markBalances`, `_snapshotTarget/_snapshotTokens`,
     `_checkTarget(target,attacker,zeroedModel)` (P_BALANCE_LOST,
     P_ATTACKER_PROFIT, P_STORAGE_CHANGED over 32 slots; **P_AUTH_WRITE only when
     `zeroedModel`** — under symbolic storage an untouched slot is unconstrained,
     so `slot != attacker` would be satisfiable for the wrong reason = FP),
     `_checkValue` (A5), `_checkTokens` (P_TOKEN_OUTFLOW via slot2, P_TOKEN_TO_ATTACKER
     via slot4), `_checkVictim` (A9: P_UNAUTH_PULL_FROM via slot3).
   - **BUG IN THE FILE AS WRITTEN:** lines ~33–34 still declare
     `address internal constant HEVM = 0x7109…D12D;` and
     `address internal constant CONSOLE = 0x0000…6c6f67;`. These **collide with
     forge-std `lib/forge-std/src/Base.sol`** → `forge build` fails with
     `Error (9097): Identifier already declared.` (Confirmed: the compiler points
     at `src/ProbeBaseA.sol` line 34 `CONSOLE` vs `Base.sol:14`). An earlier
     `sed -i` rename did NOT persist. **FIX (do this first):**
     rename `HEVM`→`KONTROL_HEVM` and `CONSOLE`→`KONTROL_CONSOLE` in
     `ProbeBaseA.sol`, including the two uses in `_assumeAttacker`.
     Also rename `bytes32 now` → `bytes32 cur` (and `uint256(now)`→`uint256(cur)`)
     in `_checkTarget` to clear warning 2319 (shadows builtin).
2. **`CA/harness/skeleton/src/TrackAControls.sol`** — REWRITTEN (v2). Genuine
   same-shape MUST_FAIL/MUST_PASS pairs with `address constant ADMIN = address(0xA11CE);`
   (no more `require(msg.sender == address(0))` trick): A1 `VulnerableInit/SafeInit`,
   A2 `VulnerableUpgrade/SafeUpgrade`, A6 `VulnerableFee/SafeFee` (manipulable
   `reserve` → permissionless `sync()`), A7 `VulnerableUnchecked/SafeUnchecked`
   (`pay(address,uint256)` unchecked inner call → `credited += amt`).
3. **`CA/harness/skeleton/src/TrackAValueControls.sol`** — REWRITTEN (v2).
   `CONSENT_TOKEN = 0x…1111`, `VALUE_ADMIN = address(0xA11CE)`. A9
   `VulnerablePull/SafePull` (`transferFrom(solver, msg.sender, amt)`; safe adds
   `solver == msg.sender || msg.sender == VALUE_ADMIN`). A5
   `VulnerableValue/SafeValue` (double-credit msg.value vs single).
4. **`CA/scripts/build_controls.py`** — NEW. Runs `forge build` in the skeleton,
   then for each name in `NAMES` finds `out/**/<Name>.json`, takes
   `deployedBytecode.object`, strips `0x`, writes `CA/harness/controls/<Name>.hex`.
   Flags: `--no-build`, `--check`. **Never ran successfully yet** (blocked by 5.1.1).

### 5.2 Consequences / must-do
- **`CA/harness/controls/*.hex` are STALE** — they still hold the OLD control
  bytecode, inconsistent with the new `.sol`. After fixing the build you MUST run
  `python3 CA/scripts/build_controls.py` to regenerate them, and verify the new
  control shapes are actually etched.
- `forge build` in `CA/harness/skeleton` is currently **RED** because of
  `ProbeBaseA.sol` (5.1.1). Fix it, then `forge build` must be green.
- **The generators still emit OLD-API probes.** `gen_stage.py` `SETUP`/`CHECKS`
  and `gen_track_a.py` reference `ProbeBase` + `_etchTokens`/`_checkTokens` and
  inline slot checks. They must be rewritten to the `ProbeBaseA` API
  (`_seedZeroed`/`_seedSymbolic`, `_snapshotTarget`, `_markBalances`,
  `_checkTarget(target,attacker,zeroedModel)`, `_checkValue`, `_checkVictim`).
- **No local `forge test` was added yet** to pin the controls concretely.

**Nothing from this session was committed or pushed.**

---

## 6. REPOS / AUTH / OPS

- **Main account = `kingmariano`** (the user wants Track A committed here).
  Fit remotes in `/workspaces/codespaces-blank` (git repo root; `CA/` is a subdir):
  `origin`=zany-xylophone (control tower), `sweep`=kontrol-stage1-sweep,
  `stage2`=kontrol-stage2-deepauth, `stage3`=kontrol-stage3-math,
  `sanctracka`=**kontrol-sanity-tracka** (the Track A repo), `data`=kontrol-datasets.
  `git push` works via the stored credential helper (even when the API key is
  stale). Token in `CA/.env` (`GITHUB_API_KEY`, scopes incl. `workflow`/`repo`).
- The **`artsbykriss`** account (Resolv) used a separate classic token
  `CHRIS_GITHUB_API_KEY` in `CA/.env`; the main token is read-only there. **Resolv
  is done** — you likely don't need CHRIS. (Gotcha if you ever do: `.env` had a
  trailing `\r`; strip with `tr -d '"' | tr -d '\r' | tr -d '[:space:]'`; push via
  a temp `GIT_ASKPASS` + `git -c credential.helper=`.)
- `.env` also holds HF token (`Mariano234/kontrol-campaign-data`), campaign GH
  token, RPC keys. **Rotate anything that was ever pasted in plaintext.**
- Hygiene: `CA/.gitignore` exists. Never commit `.env`.

---

## 7. EXACT NEXT STEPS (do in order)

1. **Fix `ProbeBaseA.sol`** (rename `HEVM`/`CONSOLE` → `KONTROL_HEVM`/`KONTROL_CONSOLE`;
   rename `now`→`cur`). Then:
   ```bash
   cd /workspaces/codespaces-blank/CA/harness/skeleton && forge build
   ```
   must be green.
2. **Regenerate control bytecode:**
   ```bash
   python3 /workspaces/codespaces-blank/CA/scripts/build_controls.py
   python3 /workspaces/codespaces-blank/CA/scripts/build_controls.py --check
   ```
3. **Add `CA/harness/skeleton/test/TrackASanity.t.sol`** — a concrete
   `forge test` that, for each MUST_FAIL control, etches it, zero-seeds, pranks a
   concrete attacker and asserts the state/value DID move; for each MUST_PASS
   control, asserts it did NOT. This pins the controls BEFORE the symbolic CI gate
   (this is the biggest quality upgrade vs stage1/2/3, which never verified
   controls concretely). Run `forge test --match-contract TrackASanity -vv`.
4. **Rewrite the generators for the `ProbeBaseA` API** and add a **full-sweep
   generator** that reads `CA/data/stages/a<stage>_*_targets.json` and emits
   `harness/stages/tracka_<class>/Stage…Chunk_<n>.sol` + `chunk_<n>.tests` +
   `manifest.json` (chunk 0 = the v2 controls; targets chunked by size class like
   `gen_stage.chunk_targets`). Do NOT require the DuckDB: the target JSONs already
   carry `hash`/`ops`/`deployments`/`addresses`; embed the bytecode via
   `CA/data/bytecodes_sel.parquet` if present, else via `--from-manifest` style.
5. **Update `tracka-batch{1,2,3}.yml`** to a real full sweep (or add
   `tracka-a1.yml … tracka-a9.yml` callers) and make `stage-matrix.yml`
   verdict-classify **CHEATCODE FP / ABORT** explicitly, not only timeout.
6. **Extend `resume-watchdog.yml`** to (a) include every new Track A caller, and
   (b) add **stuck-run detection**: a run left `in_progress` beyond the job cap
   with no active jobs → cancel + resume. Verify the
   progress/runaway guards still hold.
7. **Commit + push to `kingmariano`** (Track A repo `sanctracka` /
   `kontrol-sanity-tracka`, and any new repo). Include: `ProbeBaseA.sol`,
   regenerated `harness/controls/*.hex`, `build_controls.py`, the sanity test,
   the generator(s), updated workflows, and an updated `CA/TRACK_A_PROPERTIES.md`
   "where we are" note.
8. **Run the sanity gate in CI** (`gh workflow run tracka-batch1.yml -f mode=sanity`)
   and confirm: `VulnerableInit` FAIL / `SafeInit` PASS (+ the other A-pairs)
   BEFORE firing any full matrix. Then fire the full sweep per class.
9. Only after a FAIL is harvested: run the offline live-gate
   (`triage_live.py`) — **read the real guard slot with `eth_getStorageAt`
   before any "funds at risk" claim** (the F9 lesson: proofs run with storage
   zeroed/symbolic).

---

## 8. QUICK COMMANDS / FACTS

```bash
# git
cd /workspaces/codespaces-blank
git status -sb && git remote -v
# forge (local, allowed)
cd CA/harness/skeleton && forge build && forge test -vv
# controls
python3 CA/scripts/build_controls.py [--check]
# CI
gh workflow run tracka-batch1.yml -f mode=sanity
gh run list --workflow=tracka-batch1.yml -L 5
gh run download <run-id> -n stage<stage>-results-chunk-<n> -D /tmp/art
# watchdog (manual, dry)
gh workflow run resume-watchdog.yml -f dry_run=true
```
- Kontrol image: `runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255`.
- Local toolchain: `forge 1.8.1`, `solc 0.8.24` (pinned), 441 artifacts in
  `CA/harness/skeleton/out`.
- Control runtime-bytecode extraction: `out/<file>.sol/<Name>.json` →
  `deployedBytecode.object` (strip `0x`).
- Proof dirs contain `:` → tar before upload.
- ETH ≈ $4,700/ETH assumed in older estimates.

---

## 9. WHAT "DONE" LOOKS LIKE FOR TRACK A

- Green concrete `forge test` for every control pair.
- Green CI **sanity** run per stage (chunk 0 controls hold).
- Full matrices generated from `a<stage>_*_targets.json` and firing in CI.
- Watchdog keeps them self-healing (resume + stuck-run cancel).
- Every verdict classified PASS / FAIL / CHEATCODE-FP / ABORT / INCOMPLETE.
- Any FAIL triaged with the live gate (guard-slot read + `eth_getCode`) before
  being called a finding.
- Everything committed to `kingmariano`.

— end of handoff (Track A) —