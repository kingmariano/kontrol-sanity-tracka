# How the full-matrix targets are sourced (auditable)

Every target in `harness/stages/stage{1,2,3}/manifest.json` can be reproduced
from three persisted inputs. This note documents each step so the selection is
verifiable, not hand-waved.

## 1. Source data (public)

`Zellic/all-ethereum-contracts` on HuggingFace, snapshot **block 21,850,000**
(Feb 15 2025). Ingested by `scripts/ingest.py` + `finalize.py` into DuckDB:

| table | schema | rows |
|---|---|---|
| `contracts` | `address VARCHAR, bytecode_hash VARCHAR, blocknum BIGINT` | **69,788,231** |
| `bytecodes` | `bytecode_hash VARCHAR, bytecode VARCHAR, code_size_bytes` | **1,539,859** |
| `opcode_features` | 25 cols (see §2) | **1,539,858** |

Join key is `bytecode_hash` (lowercased). A target = one unique runtime bytecode;
its "deployments" = number of rows in `contracts` with that hash; its addresses =
the `address` column of those rows.

## 2. Radar (`scripts/opcode_scan.py`) → `data/opcode_features.parquet`

For **each of the 1,539,858 unique runtime bytecodes**:
1. **Strip the solc/vyper metadata trailer** (`<cbor><2-byte len>`, detected by
   `bzzr`/`ipfs`/`solc` in the candidate). This is the fix that removed the
   phantom `sig_transient` targets.
2. Push-aware linear-sweep disassembly (PUSH operand bytes excluded via a numpy
   fixpoint), then count tracked opcodes and derive signals.

Tracked opcodes: `caller, sload, sstore, delegatecall, callcode, call,
selfdestruct, tload, tstore, create, create2, keccak, div, eq, mload`.

Signals used for selection:
| signal | definition |
|---|---|
| `sig_sstore_no_caller` | `sstore > 0 and caller == 0` |
| `sig_transient_caller` | `(tstore>0 or tload>0) and caller>0` |
| `sig_selfdestruct` | `selfdestruct > 0` |
| `sig_delegate` | `delegatecall > 0` |
| `sig_proxy_like` | `delegatecall > 0 and n_ops <= 30` |
| `sig_div_heavy` | `div >= 3` |

Metadata-strip impact: `sig_transient` 157,396 → **37,059**;
`sig_transient_caller` 136,092 → **24,441** (F5–F8 had *no real* TSTORE/TLOAD).

## 3. Target selection (`scripts/gen_stage.py`)

Per stage, one SQL query per property class, deployment-weighted, deterministic:

```sql
-- STAGE 1
P1_AUTH_WRITE : WHERE sig_sstore_no_caller AND sig_delegate        AND code_size_eff BETWEEN 40 AND 16000
P2_BALANCE    : WHERE sig_selfdestruct      AND sig_delegate        AND code_size_eff BETWEEN 40 AND 16000
-- STAGE 2
P4_TWO_PHASE  : WHERE sig_transient_caller  AND n_ops BETWEEN 80 AND 1500
P3_PROXY      : WHERE sig_proxy_like        AND code_size_eff BETWEEN 20 AND 2000
-- STAGE 3
P7_PROFIT     : WHERE sig_div_heavy         AND n_ops BETWEEN 100 AND 3000 AND code_size_eff BETWEEN 200 AND 16000

-- every query:
FROM opcode_features o JOIN contracts c USING (bytecode_hash)
GROUP BY o.bytecode_hash, o.n_ops
ORDER BY n DESC, 1 ASC          -- deterministic tie-break
LIMIT 40                        -- per class (widened later)
```

For each selected hash the generator:
* reads the **runtime bytecode hex** from `bytecodes` and embeds it in the chunk
  `.sol` as a `vm.etch(target, hex"…")` literal (`fetch_code`);
* records `ops` (from `opcode_features`) and `deployments` (count from `contracts`);
* embeds up to `--addr-cap` (default 500) **most-recent deployment addresses**
  from `contracts` into `manifest.json`, so triage works even with no DuckDB.

### Chunking (size-class partition)
A job is only as slow as its slowest probe: `>1500 ops` gets its own chunk;
`601-1500` pairs up; `<=600` groups of 5 (P1/P2/P3) or 2 (P4/P7). Controls are
always chunk 0.

## 4. Result (what was generated, and the audit)

| stage | classes | targets | wild chunks | manifest↔DB verified |
|---|---|---|---|---|
| 1 | P1_AUTH_WRITE 40, P2_BALANCE 40 | 80 | 53 | **80/80** |
| 2 | P4_TWO_PHASE 40, P3_PROXY 40 | 80 | 28 | **80/80** |
| 3 | P7_PROFIT 40 | 40 | 24 | **40/40** |

Verification ran `SELECT count(*) FROM contracts WHERE bytecode_hash=?` and
`SELECT n_ops ...` for every manifest target and compared to the embedded
values — all matched.

Top targets by deployment coverage:
```
Stage 1: 0xf9e2d368… 492 ops 19,130 deploys (F3 family) | 0x038cfd30… 399 ops 10,029 (F2 family)
Stage 2: 0x562d59a5…  24 ops 4,700,956 (minimal clones)  | 0x1b460c82… 24 ops 4,106,154
Stage 3: 0x07be01e7… 498 ops 401,549                    | 0x35810db2… 261 ops 292,285
```

## 5. Persistence

* Generated chunks + manifests + the radar parquet are committed to git
  (`CA/harness/stages/`, `CA/data/opcode_features.parquet`) **and** mirrored to
  the private HuggingFace dataset `Mariano234/kontrol-campaign-data`
  (`radar/`, `stages/`, `controls/`) — 76 MB, no DB.
* The 23.6 GB DuckDB is **not** stored: it is reproducible from the public Zellic
  dataset + the parquet in ~8 min (`recover.sh`), so backing it up is wasteful.

## 6. Honest scope / blind spots

* **P_AUTH_WRITE checks slots 0..7 only** — unprotected writes to
  `mapping[attacker]` (at `keccak(attacker, slot)`) are invisible; this is a
  known miss (the old batch-1 caveat).
* **Only ETH is checked**, not ERC-20 balances (F8's 47 USDC would not trip it).
* **Single/two/three-call bounds** — deeper sequences are out of scope for the
  current templates.
* **Zeroed-slot 0..7 state model** is a heuristic for "fresh/uninitialized";
  FAILs are candidates filtered by live triage (`triage_live.py`), not findings.
* **`--max-depth 1000`** — PASSED means "no violation within depth" (loops may be
  incomplete); control contracts have no loops, so their PASS/FAIL is exact.
