# Ethereum Contracts Audit Campaign — Dataset Reference

## Dataset: `Zellic/all-ethereum-contracts`
- Source: https://huggingface.co/datasets/Zellic/all-ethereum-contracts
- Blog: https://www.zellic.io/blog/all-ethereum-contracts
- Snapshot: **block 21,850,000 (Feb 15, 2025)** — all contracts ever deployed on Ethereum mainnet
- License: none stated on HF page (OK for internal research/audit; confirm before redistribution)

## Where things live
| Path | Size | Persistent? |
|---|---|---|
| `/tmp/eth-contracts/eth_contracts.duckdb` | ~23 GB | ❌ wiped on container rebuild |
| `/tmp/eth-contracts/contracts.zip` | 2.25 GB | ❌ |
| `/tmp/eth-contracts/bytecodes.zip` | 4.14 GB | ❌ |
| `/tmp/eth-contracts/contracts.csv` | 8.3 GB | ❌ (deletable) |
| `/tmp/eth-contracts/bytecodes.csv` | 20.4 GB | ❌ (deletable) |
| `./scripts/ingest.py` (+ validate/followup/finalize) | — | ✅ in workspace |
| `./DATASET.md` | — | ✅ in workspace |

**Persistence rules:** stop/restart of the Codespace preserves `/tmp`; a container
*rebuild* or Codespace *recreation* wipes it. `/workspaces` always survives.

## Schema
```
contracts(address VARCHAR, bytecode_hash VARCHAR, blocknum BIGINT)   -- 69,788,231 rows
bytecodes(bytecode_hash VARCHAR, bytecode VARCHAR, code_size_bytes)  -- 1,539,859 rows
VIEW all_contracts  -- contracts JOIN bytecodes ON bytecode_hash (+ code_size_bytes)
```
All addresses/hashes lowercased on ingest. Join on `bytecode_hash`.

## Verified stats
- Contracts: **69,788,231** (242 rows have NULL bytecode_hash — deployed but bytecode unavailable; excluded from view → 69,787,989)
- Unique bytecodes: **1,539,859**; empty-code hash `0xc5d2460...a470` covers **4,837,939 contracts (6.9%)**
- Block range: 47,205 .. 21,850,000
- Code-size distribution (unique bytecodes): ≤32 B: 858 | ≤256 B: 190,557 | ≤2 KB: 262,456 | ≤8 KB: 621,037 | ≤16 KB: 322,947 | >16 KB: 142,004
- Avg code size (non-empty): ~6,589 bytes; max ~24,577 bytes (EIP-170 limit)
- Top template: a 22-byte contract deployed **10.3M times**; runner-up 23 bytes deployed 6.6M times (likely minimal proxies / vanity contracts)

## Usage
```python
import duckdb
con = duckdb.connect("/tmp/eth-contracts/eth_contracts.duckdb", read_only=True)
con.execute("SET memory_limit='6GB'"); con.execute("SET threads=4")
# e.g. all contracts whose code contains opcode selector for ERC20 transfer:
con.execute("""
  SELECT address, blocknum FROM all_contracts
  WHERE bytecode LIKE '%a9059cbb%'
  LIMIT 100
""").fetchall()
```
TIP: 65.5% of all contract addresses share just 10 bytecodes — dedupe by
`bytecode_hash` before any per-bytecode analysis.

## Caveats
1. **Bytecode only** — no verified source. Join with Etherscan/Sourcify for source-level audit.
2. **Stale snapshot** — nothing deployed after Feb 15, 2025. Top up with an RPC/node scan.
3. **Recovery after a rebuild** — everything needed is in `./scripts/`. Run:
   ```bash
   mkdir -p /tmp/eth-contracts && cd /tmp/eth-contracts
   curl -L -C - -o contracts.zip https://huggingface.co/datasets/Zellic/all-ethereum-contracts/resolve/main/contracts.zip &
   curl -L -C - -o bytecodes.zip https://huggingface.co/datasets/Zellic/all-ethereum-contracts/resolve/main/bytecodes.zip &
   wait
   pip install duckdb
   cp /workspaces/codespaces-blank/CA/scripts/*.py .
   python3 -u ingest.py > ingest.log 2>&1 &     # ~7 min; NOTE: exits with
       # AssertionError on 1 NULL-hash 'orphan' -> expected; just run finalize:
   python3 -u finalize.py                       # normalizes + view + smoke tests
   python3 -u opcode_scan.py > opcode_scan.log 2>&1 &   # ~31 min full scan
   python3 -u /workspaces/codespaces-blank/CA/scripts/export_radar.py   # ~30 s
   ```
   **Fast path (data/ survives rebuilds):** `data/opcode_features.parquet` holds the
   full scan result — re-attach without rescanning:
   ```sql
   CREATE TABLE opcode_features AS SELECT * FROM read_parquet(
     '/workspaces/codespaces-blank/CA/data/opcode_features.parquet');
   ```
   (Still need contracts/bytecodes tables re-ingested for deployment joins.)

## Persistent artifacts (survive rebuilds)
| Path | Size | Contents |
|---|---|---|
| `data/opcode_features.parquet` | 69.5 MB | Full push-aware opcode scan, 1,539,858 rows × 25 cols |
| `data/RADAR.md` | 3.4 KB | Signal prevalence + combos + top templates |
| `scripts/` | — | ingest, finalize, opcode_scan, export_radar |
| `ZERO_DAY_RESEARCH.md` | — | Bug-class taxonomy + case studies |

## Suggested campaign next steps
1. Triage: filter out templates with >1000 deployments unless first-of-kind.
2. Opcode-level feature extraction on the 1.54M unique bytecodes (e.g., detect delegatecall, selfdestruct, uninitialized storage patterns).
3. Dedup + similarity clustering to find "mutants" of known-vulnerable templates.
4. Selective source retrieval for high-interest candidates (verified via Etherscan API).
