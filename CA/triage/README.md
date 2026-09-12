# Live-gate triage — campaign results

Method: `triage_live.py` (does a FAILED verdict correspond to funded, code-bearing
live deployments?) then `triage_enrich.py` (exact ETH + ERC-20 holdings + slots).
Proof FAILs are **reachability filters**, not findings, until triaged here.

## stage 1 (P1_AUTH_WRITE / P2) — run 34683405358
FAILED: 5 targets (+1 control). **All DORMANT** — no funded instance among the
sampled deployments. No live risk. See `stage1/report.md`.

## stage 2 (P3_PROXY / P4_TWO_PHASE) — run 34683406423
FAILED: 17 targets. 15 **DORMANT**; 2 **LIVE_REACHABLE**:

| test | hash | deploys | findings |
|---|---|---|---|
| `test_p3_c23_0` | `0xaefdf0b5…` | 269,148 | 45-byte **EIP-1167 minimal-proxy clones**, impl `0x39778bc7…` (2,075 B). Sampled instances hold ~6.2 ETH + many scam/airdrop ERC-20s. FAIL is proxy-like storage change — needs impl review, **not confirmed**. |
| `test_p4_c11_1` | `0xb6aa9c41…` | 4 | 394-byte contract, ~2.0 ETH across 2 instances. Slots 0/1 = owner/operator contracts. **Needs manual review.** |

Controls green (stage1 chunk 0: VulnerableControl FAILED / SafeControl PASSED).

## verdict
No confirmed live drain yet. Two stage-2 candidates require deeper manual review.
More results pending (stage 3 + remaining chunks); re-run the downloader + triage.
