# F9 PoC — Kontrol counterexample vs. live state

Bytecode under test: `0x8824fcf9d1571b0d30d734c29b728e282437ef12747696a848581c112a971c8a`
(376 mainnet deployments). Full write-up: `../FINDING_9_S2-38.md`.

## Layout
```
poc/
  foundry.toml
  src/F9.sol            # verbatim runtime bytecode + selector/slot map
  test/F9Drain.t.sol    # 5 tests: harness model + live mainnet fork
  test/F8Live.t.sol     # 3 tests: F8 funded instances all initialized; codeless entry
  lib/forge-std/
```

## Tests
| Test | Network | Asserts |
|---|---|---|
| `test_A_harness_model_drains_when_slot5_zero` | none (etch) | reproduces the Kontrol result: sweep drains 1 ETH when `slot5==0` |
| `test_A2_harness_model_with_zero_recipient_burns_funds` | none (etch) | with `slot2==0` the ETH burns; attacker gains nothing |
| `test_B_live_instance_slot5_blocks_public_drain` | mainnet fork | funded instance has `slot5=1`; `0x0b5ab3d5` reverts (InvalidJump); balance unchanged |
| `test_B2_live_2eth_instance_gated` | mainnet fork | largest funded instance (2 ETH) is gated identically |
| `test_C_forcing_slot5_zero_drains_to_slot2_not_attacker` | mainnet fork | forcing `slot5=0` (vm.store) allows the sweep, but funds go to `slot2` (a third-party EOA), not the caller |

## Run
```bash
forge test                               # A/A2 (fork tests self-skip)
MAINNET_RPC_URL=<rpc> forge test         # all 5
```
`MAINNET_RPC_URL` is read from the environment and never committed.
