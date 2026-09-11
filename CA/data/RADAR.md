# Opcode Radar — static scan of unique Ethereum bytecodes

- Unique bytecodes scanned: **1,539,858**
- Source: Zellic/all-ethereum-contracts snapshot, block 21,850,000 (Feb 15, 2025)
- Method: push-aware linear-sweep disassembly, **solc/vyper metadata trailer stripped** before scanning (PUSH operand data excluded)

## Signal prevalence (unique bytecodes)

| Signal | Bytecodes | % | Mainnet deployments |
|---|---:|---:|---:|
| `sig_sstore_no_caller` | 45,807 | 2.97% | 143,854 |
| `sig_transient` | 37,059 | 2.41% | 42,717 |
| `sig_transient_caller` | 24,441 | 1.59% | 28,267 |
| `sig_selfdestruct` | 81,299 | 5.28% | 25,967,798 |
| `sig_delegate` | 282,148 | 18.32% | 28,581,989 |
| `sig_proxy_like` | 35,611 | 2.31% | 20,461,068 |
| `sig_div_heavy` | 994,532 | 64.59% | 4,431,623 |

## Combos of interest

| Combo | Bytecodes | Deployments |
|---|---:|---:|
| transient+CALLER (SIR-like) | 24,441 | 28,267 |
| selfdestruct+DELEGATECALL | 15,704 | 23,354 |
| sstore-no-caller+DELEGATECALL | 18,347 | 59,700 |
| TSTORE and TLOAD both | 10,835 | 11,361 |

## Top redeployed templates per signal


**sig_sstore_no_caller**
- `0xf9e2d36819eab1d19e19372266a32e00cb30b02a96732fa6174ccdb560ba1907` — 19,130 deployments, 492 ops
- `0x13231e9b0960c101a85f3d7816fc19bff49cf15ab77a116366b4261c7a847e9c` — 15,622 deployments, 472 ops
- `0x038cfd30a54785c310890eb5dbca5667cb56f069e624efd7011271f8880ca497` — 10,029 deployments, 399 ops

**sig_transient**
- `0xb9ac986f311bfe9c1b8de76b0dd578681737fa47cf7b4eae5fde4fd3634c721c` — 259 deployments, 871 ops
- `0x9337f6c5f874b3cfce53cd3e726ca0f6023b4af053aaebd76facc1552b9c869e` — 181 deployments, 4763 ops
- `0x85fceb4a2c91b40d892546a8d0726a9d7777c96c55560ebb34b85ac27d1131a5` — 128 deployments, 665 ops

**sig_transient_caller**
- `0xb9ac986f311bfe9c1b8de76b0dd578681737fa47cf7b4eae5fde4fd3634c721c` — 259 deployments, 871 ops
- `0x9337f6c5f874b3cfce53cd3e726ca0f6023b4af053aaebd76facc1552b9c869e` — 181 deployments, 4763 ops
- `0x97444bcdc38d38c65397348900e1dd9475d6914f464e87618c0e81e885791d6a` — 116 deployments, 6157 ops

**sig_selfdestruct**
- `0x1d93f60f105899172f7255c030301c3af4564edd4a48577dbdc448aec7ddb0ac` — 10,346,314 deployments, 7 ops
- `0xd80cd839dd3957d572b90780ada202a13936fa2875daea94216263371e9ef1d2` — 6,607,048 deployments, 7 ops
- `0x8f789d24f75f80df63f1d69c18963fb4c2dea81ade3b780fd0c886e4d1fabc4a` — 1,647,068 deployments, 7 ops

**sig_delegate**
- `0x562d59a51820d47f520c975e0b2bcffac644a509749a3161f481f57b6e826d21` — 4,700,956 deployments, 24 ops
- `0x1b460c826a854d61dca82f718e088b8b4c4082ffeb93752d7691bc62c51dc028` — 4,106,154 deployments, 24 ops
- `0xce33220d5c7f0d09d75ceff76c05863c5e7d6e801c70dfe7d5d45d4c44e80654` — 1,595,657 deployments, 287 ops

**sig_proxy_like**
- `0x562d59a51820d47f520c975e0b2bcffac644a509749a3161f481f57b6e826d21` — 4,700,956 deployments, 24 ops
- `0x1b460c826a854d61dca82f718e088b8b4c4082ffeb93752d7691bc62c51dc028` — 4,106,154 deployments, 24 ops
- `0xf1b574431f3838d9cdff6e701afd5a058652dab5ae5523288a83d5fad7696139` — 1,189,974 deployments, 24 ops

**sig_div_heavy**
- `0x5b83bdbcc56b2e630f2807bbadd2b0c21619108066b92a58de081261089e9ce5` — 404,300 deployments, 5361 ops
- `0x07be01e7e7206fe31ecee91ad75dada65ad6ba433ae647a1b9330469f7c6677c` — 401,549 deployments, 498 ops
- `0x35810db24ceb31609b83309d8f8a58a0dedd934a2a43dd02e3c44809a901e627` — 292,285 deployments, 261 ops
