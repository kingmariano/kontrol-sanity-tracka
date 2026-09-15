# 05 — KCFG anatomy, reading failures, counterexamples

## KCFG = K Control Flow Graph
A proof is a graph of **nodes** (symbolic states) linked by **edges** (execution). Inspect with:
- `kontrol show '<Contract>.<sig>(types)' [--version N] [--omit-unstable-output]` — static text.
- `kontrol view-kcfg '<Contract>.<sig>(types)' [--version N]` — interactive TUI (exit `Ctrl+C`).
- `kontrol get-model <test> [<node>]` — the counterexample model for a node.

Node types shown: `init` (root), `leaf` (no successors), `split` (branches), `expanded`,
`target` (goal), `terminal` (finished via a terminal rule), `frontier` (discovered, not executed).
Also `pending`, `refuted`, `stuck`, `vacuous`.

Each node line summarises: `(N steps since prev)`, node id + type, `k: <k-cell head>`, `pc`,
`callDepth`, `statusCode`, and a `src:` Solidity file:line:col if the source map is available.

## TUI panes
- **Term view** (hotkey `M` to minimize) — the full EVM config in K cells.
- **Constraint view** (`c`) — path constraints on symbolic vars.
- **Custom view** (`V`) — Solidity source highlighting the current line.

## Reading a failure (the important part)
Kontrol reports a failing node as three parts:
1. **Failure reason** — e.g. `EVMC_REVERT`, failed assertion.
2. **Path condition** — the constraints that must hold for this failure (in `Int`/K syntax).
3. **Model** — concrete values of the symbolic variables (the counterexample).
And the failing node's `<output>` cell holds any **revert data**.

**→ Decode `<output>` to identify the exact custom error/selector.** Steps we use:
- Extract the `<output>` byte token from the node JSON under `out/proofs/<id>/kcfg/nodes/<n>.json`
  (or un-tar the CI `*-kcfg` artifact).
- `cast 4byte 0x<selector>` (or `cast sig "<Sig>"`) to name it.

## Key K / KEVM syntax cheatsheet (from "debugging failing proofs")
- `*Int` = unbounded integer multiply; `/Word` = EVM 32-byte word division; `chop(x)` = `x mod 2^256`.
- `maxUInt160 &Int X` extracts an address-sized word; `maxUInt8` a bool.
- `#lookup(?STORAGE0, 6)` = storage slot 6 of symbolic storage `STORAGE0`.
  - symbolic storages are named in call order: `STORAGE`, `STORAGE0`, `STORAGE1`, … map to the
    order `symbolicStorage`/`setArbitraryStorage` was called.
  - map a slot to a variable name with `forge inspect <Contract> storage` (JSON).
  - slot offset shown as `>>Int 8` → the variable at byte offset 1 in that slot.
- `bool2Word(cond)` wraps a Bool as an Int; `#Not`, `#Equals`, `_==Int_`, `_<=Int_`, `_<Int_`.
- `#halt` in `<k>` = execution finished; then read `<statusCode>`.
- Account cells: `<accounts>` → each `<account>` has `<acctId>` and `<storage>`.

## Default symbolic-address branching (why a simple test has 3 ways)
When a symbolic address is used (as caller/prank target), Kontrol **non-deterministically branches**
on whether it equals each pre-existing account (test contract, `vm` cheatcode, deployed contracts)
or is fresh. Fix by assuming inequality, or use `remove-node`+`split-node`+`refute-node` surgery
(file 06). This is one of the biggest time sinks for address-parameterised tests.

## Known unnecessary branch: symbolic address ∈ <accounts> (evm-semantics#1752)
Same as above; resolve with one `vm.assume(symbolicAddress != <each preexisting address>)`.

## Overflows
Compiler-inserted overflow checks appear as a branch condition like
`#Not(n #Equals chop(n *Int n /Word n))`; fix with `vm.assume(n <= type(uint128).max)` etc.,
or wrap in `unchecked`.

## "Simplify the proof" when it hangs / kore-rpc returns empty
- `kontrol show` / `view-kcfg` and look for abnormally large cell expressions → write lemmas.
- Break complex proofs into smaller parts; verify components separately.
- Use concrete values for some variables.

## Distinguishing a REAL counterexample from an artifact
- **Real**: concrete `<statusCode>` (e.g. failed assertion / a real revert reachable on-chain) +
  path condition + a model that, when substituted, reproduces on-chain. **Verify by pinning that
  model into a concrete `forge test`.**
- **Artifact/FP** signatures seen in our campaigns:
  - blank `Status Code` + path `#And { a0 == #address( FoundryCheat ) }` → CHEATCODE abort (FP).
  - `step exceeded … budget / cannot shrink further; stopping` + `PENDING: N nodes` → abort, not a result.
  - `rc=124/137` (wall-timeout/OOM) → INCOMPLETE, not a result.
  - **A revert on a state that passes concretely at the exact model values** → spurious path
    (see file 08's inline-initializer bug).
