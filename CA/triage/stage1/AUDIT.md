# Stage 1 live-reachable audit

Kontrol verdicts are *model* reachability. This audit reconciles each stage-1
`LIVE_REACHABLE` with what the code actually does on-chain.
Kontrol's failing node (property + path condition + model) is treated as the top lead.

## Summary

| Test | Contract | Function | Kontrol reason | On-chain check | Verdict |
|---|---|---|---|---|---|
| `test_p1_c27_0` | `HookBeaconProxy` | `initializeBeacon(address,bytes)` | **`CHEATCODE_UNIMPLEMENTED`** (abort) | beacon set; `initializeBeacon(dead,0x)` → **"contract is already initialized"** | **FALSE POSITIVE** |
| `test_p1_c27_1` | `CollectionBeaconProxy` | `setFinalImplementation(address)` | `EVMC_REVERT` / `P_STORAGE_CHANGED` | `finalImplementation == 0x0`; `setFinalImplementation(0xdEaD)` from a random EOA → **SUCCESS (no revert)** | **REAL / LIVE / CRITICAL** |

## 1. `test_p1_c27_0` — FALSE POSITIVE (drop)

- Hash `0x13e2982407cb413d05650ff6e74a4337885fe3aab7e364be14637cb74f75b757`, 46 deploys.
- Funded instances: `0xbafe85df…9849` (1.78Ξ), `0xc8212c46…2b81` (0.34Ξ), `0x17d1dac8…ed1b` (0.06Ξ).
- Verified contract: **`HookBeaconProxy`** (a modified OZ BeaconProxy). `0x7fe8e72c` = `initializeBeacon(address,bytes)`, `public initializer`.
- **Kontrol's failing node = `CHEATCODE_UNIMPLEMENTED`**, with `a0 = #address(FoundryCheat)` (`0x7109…d12d`) and `attacker = 1248875146012964071876423320777688075155124985543`. That is an **abort**, not a property violation: the probe set the *beacon argument* to the HEVM cheatcode address, and `initializeBeacon` → `_upgradeBeaconToAndCall` → `IBeacon(a0).implementation()` called the cheatcode address.
- Two harness causes combine:
  1. `a0`/`a1` are **not** constrained away from HEVM/console/precompiles (only `attacker` is), so the solver picks `a0 = FoundryCheat`.
  2. `P_AUTH_WRITE`/`P_STORAGE_CHANGED` model zeroes slots 0–15, which **erases the OZ `Initializable` `_initialized` flag in slot 0**, so the model sees an *uninitialized* proxy and lets `initializeBeacon` run.
- On-chain: stored beacon = `0x7130a0ad4e94b8643a3f878918d4292c571521db`; simulating `initializeBeacon(0x…dEaD, 0x)` from a random EOA **reverts "contract is already initialized"** on all 3 instances.
- **Conclusion: not exploitable. Kontrol reason = cheatcode abort + uninitialized-model artifact.**

## 2. `test_p1_c27_1` — REAL, LIVE, CRITICAL

- Hash `0x2e9882dd6faca9c9bded2892eca89b37296d2ffa127759641f16d2e93eac5515`, 31 deploys.
- Funded instances (full):
  - `0xee46ad688731f61d3e2132809389a500987634b5`
  - `0xf82d33559bb4b4469b80bd3601fa898086ad827a`
  - `0x5738414d36afb5e9992ad8eec9d474077837c956`
  (≈$10 ETH total, code 1260 B)
- Verified contract: **`CollectionBeaconProxy`**. Selectors: `getCurrentImplementation()` `0x29cca569`, `getBeacon()` `0x2d6b3a6b`, `getFinalImplementation()` `0xa094e836`, and **`setFinalImplementation(address)` `0xd884e61b`**.
- Source (verified):
  ```solidity
  function _implementation() internal view override returns (address) {
      if (finalImplementation == address(0)) { return IBeacon(_getBeacon()).implementation(); }
      else { return finalImplementation; }
  }
  function setFinalImplementation(address implementation_) public {
      if (finalImplementation != address(0)) { revert ImplementationLocked(); }
      finalImplementation = implementation_;
      emit FinalCollectionImplementation(address(this), finalImplementation);
  }
  ```
- **Kontrol reason:** `EVMC_REVERT`, output `P_STORAGE_CHANGED … != 0`, path condition `selector == 3632588315` (=`0xd884e61b`), `a0 == 0`; model `attacker = 1248875146012964071876423320777688075155124985543`. So: a random caller invoked `setFinalImplementation` and the slot changed (slot 0 written with an address).
- Bytecode confirms: dispatch contains `0xd884e61b`; body does `SLOAD(slot0) → mask low 20 bytes → OR address → SSTORE(slot0)`.
- **On-chain:** `finalImplementation == 0x0000000000000000000000000000000000000000` on **all three** funded instances (`getFinalImplementation()`), `currentImplementation = 0xb9b9cc01b94bb09bdbe601acdf5fa014ac8c5837`.
- **Exploitability:** simulating `setFinalImplementation(0x…dEaD)` from a random EOA returns **success with no revert** → the one-shot guard passes because it is unset. Any EOA can permanently install an arbitrary implementation; afterwards `_implementation()` returns it for every delegatecall and `ImplementationLocked` prevents anyone from changing it back.
- **Impact:** permanent proxy takeover of a live `CollectionBeaconProxy` (31 deployments in the cohort). The 3 instances hold little ETH; the real asset at risk is the proxy's control of the collection/implementation.
- **No transaction was sent — simulation only.**

### Value at risk (all deployments, ETH @ $2,480.14)
- **25 / 31** `CollectionBeaconProxy` deployments still have `finalImplementation == 0` (vulnerable).
- **ETH held by those 25 proxies: 0.0040 ETH ≈ $9.92.**
- **ERC20 held: none.** **NFTs held by the proxies: none.**
- The collections are test collections (e.g. `"Test NFT+Print mainnet"`, symbol `test TM 19`, `totalSupply()` = 9).
- **Total drainable USD ≈ $9.92** — a genuine, deterministic, no-auth, permanent takeover, but with negligible value at risk (test/dust contracts).

### Vulnerable deployments — full addresses (25 / 31; `finalImplementation == 0`)
```
0xee46ad688731f61d3e2132809389a500987634b5   (funded)
0xf82d33559bb4b4469b80bd3601fa898086ad827a   (funded)
0x5738414d36afb5e9992ad8eec9d474077837c956   (funded)
0x04139272ccb542566da247cf649793a887a89242
0xea2264e3c7ed2c6b97f3b4fd4291dfe5ef7c808f
0xc428c721bf759995eccb5ddd519af855bbc464c5
0xb1c60abc0e43023d89a608f837afa9a33ff55962
0xb25d6e4f29ec2e4d3994d5b83cbb015cfc49c4cd
0xc324daa174d29401fe8c11cf62e4bf09e1df8853
0x7fff64a1dc787d3aa445f0ff47e5cde4cf06de5a
0x0f0cca32d32256be7cf0800f9e4ca159e796bfdd
0x30a7c7c11a5aba435eac353f139e0bd6a9af6923
0x15d81de55a9fae15fd8da82704f7891a1100e2a2
0x4400dfab00961294e76d6398a077c0dc0539ed57
0xc2bef3c4e5132c76974acd60d4d8290db4f7d4e6
0x89760d0576b65aa96ff06bab6b17eb6b597878fe
0xddaa3dea57c1045f83a63e99253f726a53f4a006
0x6fa15cdfa0f2a2899b2071ac4d1b06c45be928bd
0xc40f61e91e397d76d134af0aaa9ce0de16046ffd
0xde384de779e3311743c1248d468b998eea9544f9
0x5465871f428425852f5715b7028b02ea8e7af9bd
0x0ee2e5141591841dad17fc7ce9e6019ae224f913
0xaa68954f2721fdc9f571f812a6dd7bb124ef5392
0x3ae08a936c5be9bb2a02c8596f41e9cee0ec8012
0xeda0afab1548be31602ffbdb5b8970f343d70997
```
(Remaining 6 of 31 already have `finalImplementation` set.)


## Harness corrections this exposed
1. `a0`/`a1` (and any calldata word) must be constrained away from HEVM/console/precompiles, like `attacker` — prevents the `CHEATCODE_UNIMPLEMENTED` FP.
2. Do **not** silently zero slot 0 on `Initializable` proxies in the model (or gate it in the live-check via `eth_call`), since it fabricates "uninitialized proxy" states.
3. CI verdict parser should reclassify a failing node whose status is `CHEATCODE_UNIMPLEMENTED` (or any abort) as **INCOMPLETE**, never `FAILED`.