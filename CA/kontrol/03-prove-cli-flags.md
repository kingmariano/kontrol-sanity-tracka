# 03 — `kontrol prove` flags & recommended sets

## The flags that matter (from docs + repo CLAUDE.md)

### Test selection
| Flag | Notes |
|---|---|
| `--match-test <regex>` (`--mt`) | Selects functions. Docs (newer) say it matches the **full signature**, e.g. `'ERC20Test.testTransfer(address,uint256)'`. **Older 1.0.x** matched the **bare function name** regex only. Repeatable. **There is NO `--match-contract`.** To select a whole suite, drive a per-test loop from a `tests/<Suite>.tests` file. |
| `--test <Contract>.<fn>` | Older alias used in cheatsheet examples; multiple allowed for parallel. |

### Execution control
| Flag | Notes |
|---|---|
| `--reinit` | **Discard the saved KCFG and restart. DEFAULT IS RESUME**, so to continue a stuck proof just re-run without `--reinit`. |
| `--max-depth <n>` | Max K steps per `execute` request (split a long edge). |
| `--max-iterations <n>` | # of times to expand the next pending node in the KCFG (bounds a run). |
| `--bmc-depth <n>` | Bounded model checking: unroll loops to depth n. |
| `--run-constructor` | Include the contract constructor in test execution. **Relevant to our inline-initializer lesson (file 08).** |
| `--init-node-from <deployment_state.json>` | Start from a JSON deployment state. |
| `--with-non-general-state` | Init state of a non-test function as if a test (Simbolik). |
| `--hevm` | Use the hevm success predicate instead of Foundry's. |
| `--depth <n>` | Max depth to execute to. |

### Performance / branching
| Flag | Notes |
|---|---|
| `--use-booster` / `--no-use-booster` | Booster RPC (default, fast) vs legacy Kore. |
| `--no-break-on-calls` | **Do not store a KCFG node on every EVM call (default).** Huge node-count/time saver. |
| `--break-on-calls` | Store a node per call (debugging; also needed to *see* call boundaries). |
| `--break-every-step` | Node per opcode (very expensive). |
| `--break-on-jumpi` | Node per jump. |
| `--break-on-storage` | Node per SSTORE/SLOAD. |
| `--break-on-basic-blocks` | Node per basic block (implies break-on-calls). |
| `--break-on-cheatcodes` | Break on all Foundry rules. |
| `--auto-abstract-gas` | Extract the gas cell when infinite gas is enabled → simpler/faster. |
| `--use-gas` | Enable gas computation (costly; avoid unless gas is the property). |
| `--workers <n>` / `-j <n>` | Parallel processes. Guidance: at most `(M-8)/8` for an `M` GB machine. |
| `--cse` | Compositional Symbolic Execution (see file 07). |

### SMT
| Flag | Notes |
|---|---|
| `--smt-timeout <ms>` | Default **1000ms**. Raise for hard queries (we use 30000). |
| `--smt-retry-limit <n>` | Retry SMT with scaling timeouts. |
| `--smt-tactic <tactic>` | e.g. `'(check-sat-using smt)'`, `'(check-sat-using qfnra-nlsat)'` (non-linear arith). |

### Reporting / debugging
| Flag | Notes |
|---|---|
| `--verbose` / `-v`, `--debug` | logs |
| `--failure-information` / `--no-failure-information` | failure summary (default on) |
| `--counterexample-information` | show models for failing nodes (default on) |
| `--fail-fast` / `--no-fail-fast` | stop other branches on first failure (default **on**). `--no-fail-fast` explores everything. |
| `--haskell-log-dir DIR` | capture per-RPC JSONL logs (why Booster aborted — see file 07) |
| `--haskell-log-entries E1,E2,…` | which backend entry families to request |
| `--booster-only-simplify` | skip the Kore simplification pass after Booster |
| `--xml-test-report` | JUnit XML |
| `--bug-report <name>` | dump a bug report |
| `--include-summary <name>` | include a summary as a lemma |
| `--port`, `--maude-port`, `--kore-rpc-command` | attach to an existing RPC server |
| `--foundry-project-root` | path to project root |

## Recommended flag sets

### Our campaign default (safe, general-purpose; 1.0.255)
```
--use-booster --no-break-on-calls --no-stack-checks --no-log-rewrites \
--max-frontier-parallel 2 --max-depth 50000 --max-iterations 100000 \
--smt-timeout 30000 --smt-retry-limit 2 --workers 2 --step-timeout 600 \
--auto-abstract-gas
```
(`--no-stack-checks`, `--no-log-rewrites`, `--max-frontier-parallel`, `--step-timeout` are
booster/kevm_pyk options present in the 1.0.255 CLI even when not in the GitBook table.)

### Fast (docs-recommended "maximum speed")
```
kontrol prove --test MyC.test1 --test MyC.test2 \
  --bmc-depth 10 --smt-timeout 10000 \
  --auto-abstract-gas --no-break-on-calls --workers 2 --use-booster
```

### Debug a slow/failing step
```
# advance to the frontier, one extension at a time:
kontrol prove --match-test 'MyC.testThing()' --max-iterations 1
# then log just the next step:
kontrol prove --match-test 'MyC.testThing()' \
  --max-iterations 1 --max-depth 1 --haskell-log-dir hlog --verbose
```

## Script pattern (docs-recommended)
Wrap build+prove in `test/run-kontrol.sh` with `set -euxo pipefail`, print `time bash test/run-kontrol.sh 2>&1 | tee log.out`.
