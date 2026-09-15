# 01 — Ecosystem & architecture

## What Kontrol is
- **Kontrol = Foundry integration for KEVM.** It compiles a Foundry project's Solidity into **K**
  and runs **symbolic-execution proofs** over `test*` functions. You keep writing Foundry tests;
  Kontrol proves them for *all* inputs instead of fuzzing 256.
- Thin Python layer (`src/kontrol/`) over two upstream deps:
  - **`kevm-pyk`** — the EVM semantics + K frontend (pinned by `kevm-pyk@git+…@vX.Y.Z` in `pyproject.toml`).
  - **`pyk`** — K's Python toolkit: options system, proof/KCFG infra, RPC clients.
- Only **Foundry-specific semantics** live in Kontrol: `src/kontrol/kdist/` (`kontrol.md`,
  `cheatcodes.md`, `foundry.md`, `assert.md`, `kontrol_lemmas.md`).
- EVM-layer semantics/lemmas live **upstream** in `runtimeverification/evm-semantics` (KEVM).

## Repos / components (the "ecosystem")
| Repo | Role |
|---|---|
| `runtimeverification/kontrol` | this tool; CLI + Foundry semantics |
| `runtimeverification/evm-semantics` (KEVM) | formal EVM model in K; `kevm-pyk` |
| `runtimeverification/k` | K framework (frontend + tooling) |
| `runtimeverification/haskell-backend` | the **Kore** backend (symbolic reasoning, SMT) |
| `runtimeverification/llvm-backend` | the LLVM backend (concrete execution) |
| **Booster** (`kore-rpc-booster`) | fast rewriting engine that *falls back* to Kore when it can't finish |
| `runtimeverification/pyk` | Python K tooling (Options, KCFG, RPC) |
| `runtimeverification/kup` | package manager: install/override `kontrol`/`kevm`/`k` versions |

- **Booster vs Kore**: Booster is the fast path; when Booster aborts it falls back to Kore
  (slow but complete). A proof stalling often = Booster aborting repeatedly. See `07`.
- **Success predicate** is defined in `src/kontrol/kdist/foundry.md` (`#Foundry` success predicate).
  Failure = (evm revert status code) OR (failed assertion) OR (other Foundry failure), reported as
  **failure reason + path condition + model**.

## `src/kontrol` package map (from repo CLAUDE.md)
- `__main__.py` — entry point; command `foo-bar` → `exec_foo_bar()` → `foundry_*`.
- `cli.py` — `KontrolCLIArgs` (subclass of `kevm_pyk`'s `KEVMCLIArgs`) + `_create_argument_parser()`.
- `options.py` — one `Options` dataclass per command (`ProveOptions`, `ShowOptions`, `BuildOptions`).
  **Same option can come from CLI flag, `kontrol.toml`, or default → wire a new flag in all three.**
- `foundry.py` — `Foundry` class; `FoundryKEVM(KEVM)`, `KontrolSemantics(KEVMSemantics)`
  (cheatcodes as custom KCFG steps).
- `prove.py` — `foundry_prove()`: spins up Kore/Booster RPC, builds test list from `--match-test`,
  drives a `pyk` `KCFGExplore` per test.
- `solc_to_k.py` / `kompile.py` — solc JSON → per-contract K; builds `foundry.k`.
- `display.py` — `foundry_show()` / `foundry_view()` (text KCFG / TUI).

## The `kontrol` command set
- **Setup/build:** `init`, `setup-storage`, `build`, `load-state`, `version`, `clean`.
- **Prove/inspect:** `prove --match-test <regex>`, `show <test>`, `view-kcfg <test>`, `list`, `get-model`.
- **KCFG surgery:** `simplify-node`, `step-node`, `section-edge`, `split-node`, `merge-nodes`,
  `remove-node`, `minimize-proof`, `refute-node`, `unrefute-node`.

## Proof state on disk
- `out/kompiled/` — the compiled K definition.
- `out/digest` — rebuild-detection hash of K files + options + Kontrol version.
- `out/proofs/<test-id>/<version>/` — the `APRProof`/KCFG (read/written by all inspect commands).
  Directory naming uses `test%<Contract>.<sig>(types):<version>` (the `:` is why artifacts must be tarred).
- `kontrol clean --proofs` clears proofs; `--reinit` rebuilds a single proof.

## Versions
- Repo pins: `deps/k_release`, `deps/kevm_release`, `deps/z3`, `deps/uv_release`, `deps/uv_release`.
- Docker images we use: `runtimeverificationinc/kontrol:ubuntu-jammy-1.0.255` (campaign image).
  The tag encodes `<ubuntu>-<kontrol-version>`.
- `kup install kontrol --version vX.Y.Z` / `kup list kontrol` / `kup list kontrol --inputs`
  (override nested deps with `--override <input-path> <ver>`).
