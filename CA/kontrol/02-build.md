# 02 — Build (`kontrol build`, kompile/kdist, lemmas, digest)

## What `kontrol build` does
1. `forge build` the Foundry project.
2. `solc_to_k` → per-contract K.
3. generate `foundry.k`, then **kompile** it via `kevm_pyk`.

Outputs: `out/kompiled/`, `out/digest`, `out/` artifacts.

## `build` flags
| Flag | Meaning |
|---|---|
| `--verbose` | verbose build trace |
| `--require <file>` | include a lemmas file (e.g. `test/myproject-lemmas.k`) |
| `--module-import <TestContract>:<MODULE>` | import a module from the `--require` file into the test contract's module |
| `--rekompile` | force rebuild of the K definition (REQUIRED after changing lemmas) |
| `--regen` / `--reinit` (version-dependent) | regenerate project definition (see below) |
| `--keccak-lemmas` / `--auxiliary-lemmas` | select `KONTROL-KECCAK` / `KONTROL-AUX`/`FULL` definition |

Example:
```
kontrol build --require test/myproject-lemmas.k \
              --module-import MyProperties:MYPROJECT-LEMMAS \
              --rekompile
```
After adding/altering lemmas you MUST `--rekompile`, else Kontrol won't see them.
In older docs, the pattern is `kontrol build --regen --rekompile`.

## kdist targets (the K semantics Kontrol owns)
- `kontrol.base` → `KONTROL-BASE` (no extra lemmas)
- `kontrol.keccak` → `KONTROL-KECCAK` (keccak lemmas)
- `kontrol.aux` → `KONTROL-AUX` (aux helper lemmas)
- `kontrol.full` → `KONTROL-FULL` (everything)
Build: `uv run kdist --verbose build -j2 'kontrol.*'` (Linux prefix `CXX=clang++-14`).
**Any change to `src/kontrol/kdist/` requires a full rebuild** (no incremental build).

## Digest / rebuild detection
`out/digest` is a hash of K files + options + Kontrol version. If `--regen` is not used, a stale
digest can mean a definition change is silently ignored.

## Linked libraries
- A library with **≥1 external/public** function must be **deployed separately**; the using
  contract's bytecode contains an address **placeholder** `__$<hash>$__`.
- **Kontrol + Forge automatically deploy and link libraries** when running tests — you normally
  don't hand-deploy them. (Verified in the docs "linked library example".)
- If a library call reverts with *empty returndata*, suspect a linking/lookup problem; if it reverts
  with a *custom error from inside the library*, linking is fine and the revert is real (this is how
  we ruled out linking as the cause of the Resolv W3 failures — the revert was `_mint(0)`).

## Kompiled project reuse
Integration tests can reuse a pre-kompiled project via pytest `--foundry-root PATH`.
For our CI we always `kontrol build` inside the pinned Docker image.

## Gotchas
- Integration tests require a **pre-built kdist**, else a missing-artifact error.
- `prove.py` uses `multiprocess` (not stdlib `multiprocessing`).
- `foundry.py` uses `tomlkit` to preserve TOML formatting.
- Stray `kore-rpc-booster` processes can hang; `pkill -9 -f kore-rpc-booster` afterwards.
