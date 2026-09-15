# Kontrol Knowledge Base (persistent memory)

Authoritative, compaction-proof notes on Kontrol + the K/KEVM ecosystem.
Sources: https://docs.runtimeverification.com/kontrol , https://github.com/runtimeverification/kontrol
(especially the repo `CLAUDE.md` on `master`, which is the most current), plus lessons
derived in the Resolv/main campaigns (see `08-lessons-from-our-campaigns.md`).

READ THIS FIRST when writing/repairing Kontrol proofs. It exists so a fresh context
does not have to rediscover flags, cheatcode semantics, or failure signatures.

| File | Contents |
|---|---|
| `01-ecosystem-architecture.md` | What Kontrol is, repos, K/KEVM/pyk/booster, package layout, versions |
| `02-build.md` | `kontrol build`, kompile/kdist, lemmas, digest, rebuild rules |
| `03-prove-cli-flags.md` | Every `kontrol prove` flag that matters + recommended flag sets |
| `04-cheatcodes.md` | Supported cheatcodes + **semantic differences** (assume/ffi/random) |
| `05-kcfg-and-diagnosis.md` | KCFG anatomy, node types, reading failures, counterexamples |
| `06-lemmas-advancing-proofs.md` | Lemmas, attributes, stuck nodes, refute/split/merge surgery |
| `07-performance-and-cse.md` | Speed: workers, break flags, bmc, CSE, haskell logging |
| `08-lessons-from-our-campaigns.md` | Hard-won gotchas from OUR proofs (the important part) |
| `09-property-authoring-playbook.md` | How to write properties that actually prove & find drains |
| `10-config-snippets.md` | Copy-paste kontrol.toml / CI workflow patterns we use |

Rule of thumb: when a fact here conflicts with a memory of the docs, trust this file
(it is sourced), and re-fetch the page if it is critical.
