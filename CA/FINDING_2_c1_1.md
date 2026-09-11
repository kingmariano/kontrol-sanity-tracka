# Finding #2 — P1 Unprotected Address Write (CI Light Batch, chunk 1)

**Status:** CONFIRMED property violation · dormant family · **low live impact**

## Target
| | |
|---|---|
| Bytecode hash | `0x038cfd30a54785c310890eb5dbca5667cb56f069e624efd7011271f8880ca497` |
| Size | 412 ops |
| Deployments | **10,029** (factory: `0xf6874c88…c61`, blocks 14.1M–15.2M, mid-2022) |
| Verified | No (unverified bytecode) |

## Counterexample (from the proof — exact, not fuzzed)
- **Property:** `P1-UNPROTECTED-WRITE` — a storage slot (0..7) ends holding the attacker's address after one arbitrary call
- **Selector:** `0x19ab453c` (430654780)
- **Path condition:** `attacker == #asWord(#range(#buf(32, a0), 12, 20))` — the low 20 bytes of the first calldata argument are written into storage as an address
- **Interpretation:** classic "anyone can set owner/admin/mapping-entry" — a single call to selector `0x19ab453c` with `a0 = <victim-addr-padded>` installs an arbitrary address into a privileged slot

## Live-state triage (Blockscout, sampled instances)
- `0xdd5c8639…26fe` (block 15,177,860): 0 ETH, no tokens, no activity since creation
- `0x4ddbdb40…525d` (block 14,137,295): 0 ETH, no tokens, no activity since creation
- `0xe8601eab…1b67`: no ERC-20 holdings
- All unverified, all created by the same mass-deployer factory → dormant batch, no funds at risk

## Verdict
Property violation mathematically confirmed; exploit monetization would require
one of these 10,029 contracts to have ever held funds or privileges — none did.
**Severity: confirmed vulnerability, negligible live impact.** Family recorded for
the dedup ledger — any future deployment of this bytecode inherits the finding.
