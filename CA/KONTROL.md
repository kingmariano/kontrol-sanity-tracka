# Kontrol — Research Notes for the Audit Campaign

Sources: github.com/runtimeverification/kontrol (BSD-3-Clause) + docs.runtimeverification.com/kontrol
Status: RESEARCHED, NOT INSTALLED (per instructions — install later into /tmp)

## 1. What it is
Symbolic-execution formal verifier for EVM. Stack: K Framework → KEVM (formal EVM
semantics in K) + Foundry integration. You write specs as Foundry tests (Solidity);
Kontrol proves them for ALL inputs via symbolic execution over real bytecode.
Commands: `kontrol init | build | prove | list | show | view-kcfg | refute-node |
unrefute-node | split-node | remove-node | setup-storage | summary`.
Two-stage: `kontrol build` (compiles Foundry project into K definition) then
`kontrol prove` (symbolic execution, SMT-backed, produces KCFG proofs).

## 2. Bytecode-verification mode (our key feature)
- `vm.etch(ADDR, BYTECODE)` deploys raw runtime bytecode; define a Solidity interface;
  `vm.setArbitraryStorage(ADDR)` makes storage fully symbolic; write property tests.
- Bytecode sources: `cast code <addr> --rpc-url`, Etherscan, our dataset.
- This bypasses source-code requirements entirely → perfect fit for the
  Zellic dataset (69.8M bytecodes, 1.54M unique).

## 3. Key cheatcodes (verification-relevant)
- Symbolic: `setArbitraryStorage`, `randomUint/Bool/Bytes/Address`, `assume`
- State: `etch`, `deal`, `load`, `store`, `copyStorage`, `warp/roll/fee/chainId/coinbase`
- Access control: `prank`/`startPrank`; expectations: `expectRevert`, `expectEmit`,
  `expectStaticCall/expectDelegateCall/expectRegularCall/expectCreate*`
- Call control: `mockCall`, `allowCalls`/whitelist machinery; expect*Call assertions
- Missing (not implemented): fork management (`createFork`/`selectFork`), FFI,
  file ops, env vars, string utils. (Note: bytecode guide suggests
  `vm.createSelectFork`, but cheatcodes page lists fork mgmt as unimplemented — verify at install time.)

## 4. Critical flags (kontrol prove)
- `--test/--match-test` (regex over full signature), `--workers N` (parallel proofs)
- `--max-depth`, `--max-iterations`, `--bmc-depth N` (loop unrolling bound)
- `--smt-timeout` (ms per SMT query), `--auto-abstract-gas` (kill gas branching)
- `--no-break-on-calls` (don't split at every external call), `--break-on-cheatcodes`
- `--use-booster` (fast LLVM-based backend), `--cse` (compositional symbolic exec)
- `--run-constructor`, `--reinit`, `--rekompile`, `--xml-test-report`
- `--generate-counterexample` (emits Foundry-runnable failing test file)
- Speed combo from docs: `--bmc-depth 10 --smt-timeout 10000 --auto-abstract-gas --no-break-on-calls --workers 2 --use-booster`

## 5. Killer features for us
- **CSE**: function summaries generated once, reused across tests → attacks path explosion
- **Node refutation**: `refute-node`/`split-node`/`unrefute-node` to prune junk branches
- **Counterexample generation** (`--generate-counterexample`): concrete .sol repro files
- **Digest file caching** (`out/digest`): re-proofs only what changed (CI-friendly)
- **Structured symbolic storage**: `kontrol setup-storage` from storageLayout (experimental; mappings/arrays limited)
- **Lemmas/invariants**: custom .k lemmas to discharge SMT gaps
- KCFG inspection: `kontrol show` (text), `kontrol view-kcfg` (visualizer)

## 6. Requirements vs OUR environment
- Docs recommend: 16GB RAM + 16GB swap. We have 15GB RAM, 0 swap, 4 cores → must add swap file (Codespaces allows this) and cap --workers at 2-3.
- Install: `bash <(curl https://kframework.org/install)` → `kup install kontrol`
  (heavy first install; alternative: Docker image runtimeverificationinc/kontrol)
- Needs Foundry (forge/cast) for the harness project.

## 7. Limitations (from docs + structural)
1. Slow: minutes-hours per nontrivial proof; SMT timeout tuning required
2. SMT/KEVM reasoning gaps → needs hand-written lemmas (advancing-proofs guide)
3. Loops need invariants or --bmc-depth bound (incompleteness)
4. Symbolic keccak/sha3 with symbolic inputs = very hard, often needs abstractions
5. Missing cheatcodes: forks, FFI, env, file I/O
6. Counterexample gen + structured storage are experimental; dynamic types limited
7. Bytecode mode needs interfaces: selectors must be known (signature DB needed)
8. Per-bytecode analysis cost means it can NEVER cover 1.54M bytecodes — strict triage needed
9. Proof maintenance burden: digest invalidation re-runs proofs when code/lemmas change

## 8. Campaign integration plan
1. Triage (DuckDB): pick candidate bytecodes (size 257B-16KB band, exclude top
   templates, opcode features: delegatecall into unknown, selfdestruct reachable, etc.)
2. Interface recovery: extract 4-byte selectors from bytecode → match against
   open-signature DB (4byte.directory / etherscan labels) → auto-generate IFace.sol
3. Harness: forge project; per-target test contract: etch + setArbitraryStorage +
   generic property suite (e.g. "cannot selfdestruct", "onlyOwner enforced",
   "no uninitialized-storage writes", reentrancy guards hold)
4. Run matrix: first pass --bmc-depth small + --auto-abstract-gas + booster + workers;
   deep-dive only failed/interesting proofs; use CSE + refute-node to control branching
5. Counterexamples → reproducible forge tests → findings
