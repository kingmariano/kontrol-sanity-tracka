# 08 — Lessons from OUR campaigns (the hard-won part)

Everything here was observed in the `kingmariano` main campaign and the `artsbykriss` Resolv
campaign. Treat as ground truth for the pinned version `1.0.255` unless re-tested.

## 8.1 `bound()` is NOT modelled; `vm.assume` IS — and differs from Foundry
- A/B experiment (main campaign): with `bound(x, …)` the prover still reached `x == 0`; with
  `vm.assume(x >= lo)` the `x == 0` path disappeared.
- **Rule: never use `bound()` in a Kontrol property. Use `vm.assume(...)`.**
- To get a value in `[lo,hi]` without bound, either `vm.assume(x >= lo && x <= hi)` and accept that
  the solver picks boundary/minimum values, or use modulo arithmetic for a uniform range.
- `vm.assume(false)` in Foundry *skips* the test; in Kontrol it makes the path infeasible
  (it appears as a `vacuous` node, not a skip).

## 8.2 THE BIG ONE: inline state-variable initializers read as ZERO
- **Symptom:** proof fails with `EVMC_REVERT` and the failing node's `<output>` is a custom error
  from a *token* (`e.g. ERC20InvalidReceiver(address(0))`), even though the test passes concretely
  for the reported model values.
- **Cause:** Kontrol did **not** apply the test contract's **inline state-variable initializers**
  (e.g. `address internal alice = address(0xA11CE);`). Those variables were **0** in the symbolic
  initial state. Storage set in `setUp()` (like `usr = new MockUSR()`) WAS correct. So
  `usr.mint(alice, amt)` became `usr.mint(0, amt)` → `_mint(0)` → `ERC20InvalidReceiver(0)`.
- **Proof:** decoded the failing frame calldata from the KCFG and saw the literal first argument
  was 32 zero bytes for `mint(address,uint256)`. setUp-assigned vars worked; only inline-initialised
  ones were zero.
- **Which suites failed vs passed is fully explained by this:** suites passed when the
  inline-initialised address was used only as a `vm.prank`/role target (0 is harmless there), and
  failed when it was used as a **mint/transfer recipient**.
- **Fix:** make such constants `address internal constant X = address(0x…);` (embedded in bytecode,
  no storage read), or assign them in `setUp()`. We applied this to all Resolv test files.
- **Detection recipe:** if a symbolic revert happens on a state that passes concretely at the model
  values, suspect a zero/mis-initialised state variable. Inspect the calldata of the reverting frame.

### KCFG extraction recipe (used to prove the above)
```python
import json, ast
def walk(o):
    if isinstance(o, dict):
        if o.get('node') == 'KApply': yield o
        for v in o.values(): yield from walk(v)
    elif isinstance(o, list):
        for v in o: yield from walk(v)
node = json.load(open(f'out/proofs/<id>/kcfg/nodes/<n>.json'))
cells = list(walk(node['cterm']['config']))
for ap in cells:
    if ap['label']['name'] == '<output>':
        # decode the byte token -> revert data -> `cast 4byte 0x<sel>`
        print(ast.literal_eval(<first b" token inside ap>).hex())
    if ap['label']['name'] == '<callData>':
        # first byte token = selector + static args; then `buf(32, var)` for dynamic tail
        print(...)
```
- `<output>` gives the revert selector (crucial).
- `<callData>` frames: current frame at config top; suspended frames in `<callStack>`.
- `TERMINAL` nodes come from `proof.json` (`"terminal": [...]`), so un-tar `*-kcfg` artifacts and
  read `out/proofs/<test>:<ver>/kcfg/nodes/<id>.json`.

## 8.3 External libraries / linking are handled — do NOT blame linking for a custom-error revert
- A library with external/public functions produces a `linkReferences` placeholder in the bytecode
  and is `DELEGATECALL`ed. Kontrol+Forge **auto-deploy and link** it.
- If the library call were the problem, the revert data would be **empty** (no code at target).
- In Resolv W3 the revert was a custom error from `_mint(0)`, i.e. the library calls **succeeded**
  and the failure was our 8.2 bug. Contradiction: `linkReferences != {}` + library params ⇒ linking
  is fine.

## 8.4 Failure signatures & how we classify (no-FP / no-FN discipline)
| Observation | Classification |
|---|---|
| Concrete `Status Code` + reachable path + model that reproduces on-chain | **REAL** (verify with a pinned concrete `forge test`) |
| Blank `Status Code`, path `#And { a0 == #address( FoundryCheat ) }` | **CHEATCODE FP** |
| `step exceeded … budget … cannot shrink further; stopping` + `PENDING: N nodes` | **ABORT** (INCOMPLETE), not a finding |
| `rc=124` (wall timeout) / `rc=137` (OOM/SIGKILL) | **INCOMPLETE** |
| `EVMC_REVERT` on a state that passes concretely at the model values | **SPURIOUS** (see 8.2) |
| `EVMC_REVERT` at the smallest assumed input, path = the assume | investigate calldata (usually spurious) |
- **Always decode `<output>`.** A revert is not automatically a vulnerability; and for "no-gain"
  properties a revert is never a gain.
- We proved real-vs-spurious by writing a scratch concrete test that pins the model value:
  `forge test --match-contract ZZScratch -vv`. (Local `forge test` is allowed; only *Kontrol/docker*
  must run in CI.)

## 8.5 Symbolic addresses cause 3-way branching (and slow proofs)
- Using a symbolic address (fuzz arg / prank target) makes Kontrol branch over membership in
  `<accounts>` (test contract, `vm`, each deployed contract) vs fresh.
- Mitigate: `vm.assume(addr != address(this)); vm.assume(addr != address(vm));`
  `vm.assume(addr != address(<each deployed>));` — or use the KCFG surgery in file 06.
- Kontrol already assumes `CALLER_ID`/`ORIGIN_ID`/`freshAddress()` differ from precompiles and the
  cheatcode address `0x7109…D12D`.

## 8.6 Mock fidelity is a FALSE-NEGATIVE risk
- `MockUSR`/`MockERC20` in our harness are **freely mintable with no roles**, whereas the real
  USR/RLP are role-gated `SimpleToken`s. **Proofs over mocks say nothing about the real token.**
- Prefer faithful mocks or a fork; otherwise add explicit token-level properties or exclude the
  token from the trust assumptions and state it.

## 8.7 CI / artifact mechanics (see file 10)
- Kontrol proof dirs contain `:` (e.g. `test%F.test_x(uint256):0`) — **artifacts reject `:`, so tar
  the KCFG dir before upload**: `tar -czf kcfg_<Suite>.tgz -C out proofs`.
- The container writes as root; the bind-mounted workspace must be world-writable
  (`chmod -R a+rwX .`) **before** build and **before each** prove run, else
  `PermissionError: 'out/proofs/<id>:0'`.
- A job SIGKILLed mid-write must not fail the job: tar with `|| true` and print verdicts explicitly.
- `kontrol prove` (1.0.255) has **no `--match-contract`** — drive `--match-test` per test from a
  `tests/<Suite>.tests` list.
