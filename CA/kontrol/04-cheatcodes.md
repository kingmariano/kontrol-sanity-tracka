# 04 — Cheatcodes (supported set + SEMANTIC DIFFERENCES)

All cheatcodes dispatch through the Foundry cheatcode address
`0x7109709ecfa91a80626ff3989d68f67f5b1dd12d` by ABI selector.
Foundry + Kontrol-proprietary are implemented in
`src/kontrol/kdist/cheatcodes.md` (`FOUNDRY-CHEAT-CODES`) and `assert.md` (`KONTROL-ASSERTIONS`).

## Foundry-compatible (supported)

**Address manipulation:** `prank(address)`, `prank(address,address)`, `startPrank(...)`, `stopPrank()`.

**Account/state:** `setArbitraryStorage(address)` (alias: `symbolicStorage`), `load`, `store`,
`copyStorage`, `deal`, `etch`, `getNonce`, `setNonce`.

**Environment:** `warp`, `roll`, `fee`, `chainId`, `coinbase`.

**Symbolic helpers:** `assume(bool)`, `randomUint()`, `randomUint(min,max)`, `randomBool()`,
`randomBytes(n)`, `randomAddress()`, `randomBytes4()`, `randomBytes8()`.

**Address utils:** `label(address,string)`, `addr(uint256)`, `computeCreateAddress(address,uint256)`.

**Revert/event/call expectation:** `expectRevert()` / `expectRevert(bytes4)` / `expectRevert(bytes)`,
`expectEmit(...)`, `expectStaticCall/expectDelegateCall/expectRegularCall/expectCreate/expectCreate2`.

**Crypto:** `sign(uint256,bytes32)`.

**Mocking:** `mockCall(address,bytes,bytes)`, `mockFunction(address,address,bytes)`.

**FFI:** `ffi(string[])` (gated — see below).

**Assertions:** `assertEq`, `assertNotEq`, `assertTrue`, `assertFalse`, `assertGe`, `assertGt`,
`assertLe`, `assertLt`, `assertApproxEqAbs`, `assertApproxEqRel`, plus raw `assert(bool)`.
Implemented in `assert.md`.

## Kontrol-proprietary (break `forge test` compatibility — prefer Foundry names)
- `freshUInt(uint8[,string])`, `freshBool([string])`, `freshBytes(uint256[,string])`, `freshAddress([string])`
  — named variants give readable counterexample variables.
- `symbolicStorage(address[,string])` — alias of `setArbitraryStorage`.
- `copyStorage(address,address)`.
- `forgetBranch(uint256,uint8,uint256)` — drop a path constraint on the current branch.
- `setGas(uint256)`, `infiniteGas()`.
- `allowChangesToStorage(address,uint256)`, `allowCallsToAddress(address)`, `allowCalls(address,bytes)`.

## SEMANTIC DIFFERENCES (critical)
1. **`vm.assume(cond)`** — Foundry *discards* the fuzz input when false; Kontrol injects `cond`
   as a **hard path constraint** on the symbolic path. => `vm.assume` is how you constrain the
   symbolic state; it does NOT mean "skip this test". It IS honored (our proofs show `1 <=Int amount`
   in the path condition).
2. **`bound(x,lo,hi)` is NOT constrained by Kontrol** — a bounded value stays symbolic over its full
   type. **A/B-proven in the main campaign**: with `bound`, `x==0` survived; with
   `vm.assume(x>0)` it did not. => **Always replace `bound(...)` with `vm.assume(...)` plus a `%`/
   arithmetic transform if you need a value in a range.**
3. **`random*` ≡ `fresh*`** — both are fresh unconstrained symbolic values; no randomness exists
   at the prover level.
4. **`ffi`** — Foundry always runs the shell command; Kontrol runs it only if `FOUNDRY_FFI=true`,
   `DAPP_FFI=true`, or `ffi = true` in `foundry.toml`. Otherwise `vm.ffi` returns a **fresh symbolic
   variable** (unknown external output).
5. **Symbolic `prank`/`startPrank` addresses branch 3-way** (see file 08): Kontrol branches on whether
   the pranked address equals the test contract / the `vm` cheatcode address / a deployed contract,
   vs a fresh account. Add `vm.assume(addr != address(this)); vm.assume(addr != address(vm)); …`
   to kill these branches.

## Default address preconditions Kontrol adds automatically
`CALLER_ID`, `ORIGIN_ID`, and `freshAddress()` results are assumed **≠ precompile addresses** and
**≠ the cheatcode address** `64532647442654720331341006915390590852536243434` (= `0x7109…D12D`).

## NOT implemented (do not rely on)
- Environment-variable manipulation (`setEnv`, `envBool`, …)
- File ops (`readFile`, `writeFile`, …)
- Fork management (`createFork`, `selectFork`, …)
- FFI (only via the gate above)
- String conversion utilities
- `expectRevert` with a **specific** reason/selector is supported, but matching semantics can be
  loose in older versions — verify a failing reason by inspecting the actual revert data.

## Internal cells (for debugging cheatcode state)
- Prank: `<prevCaller> <prevOrigin> <newCaller> <newOrigin> <active> <depth> <singleCall>`
- Expected revert: `<isRevertExpected> <expectedDepth> <expectedReason>`
- Expected opcode: `<isOpcodeExpected> <expectedAddress> <expectedValue> <expectedData> <opcodeType>`
- Expected emit: `<recordEvent> <isEventExpected> <checkedTopics> <checkedData> <expectedEventAddress>`
- Whitelist: `<isCallWhitelistActive> <isStorageWhitelistActive> <allowedCallsList> <storageSlotList>`
- Mocks: `<mockCall>` (`<mockAddress>` → `<mockValues>` map)
