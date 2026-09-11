# Finding #3 — P1 Unprotected Address Write (Stage 1 Wave 1, chunk 0)

**Status:** CONFIRMED property violation · recent deployments (2024-25) · triage in progress

## Target
| | |
|---|---|
| Bytecode hash | `0xf9e2d36819eab1d19e19372266a32e00cb30b02a96732fa6174ccdb560ba1907` |
| Size | 509 ops |
| Deployments | **19,130** |
| Verified | No |

## Counterexample (from the proof — exact, not fuzzed)
- **Property:** `P1-UNPROTECTED-WRITE`
- **Selector:** `0xf09a4016` (4036640790)
- **Path condition:** Kontrol explored and *eliminated* 4 other selectors
  (`1198859202`, `1777921804`, `2993252381`, `3730046165`) before isolating the
  violating path at `selector == 4036640790` — genuine branch reasoning
- **Interpretation:** unprotected privileged-address installation, same class as Finding #2

## Inspectable instance addresses (copy-paste)
```
0xe9A59ddB3C43aE01D59d195C56Cbbda14dFE3b11
0xa0e943c9d0aed6a072ec7feca9c18abd8f2db560
0x2d0200a85d2db3bc5465564cf1f6f9347db4f5fd
```

- Etherscan: https://etherscan.io/address/0xe9A59ddB3C43aE01D59d195C56Cbbda14dFE3b11
- Vulnerable function selector: `0xf09a4016`
- Full runtime bytecode hash: `0xf9e2d36819eab1d19e19372266a32e00cb30b02a96732fa6174ccdb560ba1907`

## Live-state triage (Blockscout, sampled)
- `0xe9A59ddB…3b11` (block 21,332,519, Nov 2024): 0 ETH, no tokens, no activity
- Unlike Findings #1/#2 these are RECENT deployments (blocks 20.1M-21.6M, late 2024-2025)
  — same dormant state so far, but the family is younger; worth periodic re-checks
