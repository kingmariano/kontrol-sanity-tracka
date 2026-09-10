# Opcode Radar — static scan of unique Ethereum bytecodes

- Unique bytecodes scanned: **1,539,858**
- Source: Zellic/all-ethereum-contracts snapshot, block 21,850,000 (Feb 15, 2025)
- Method: push-aware linear-sweep disassembly (PUSH operand data excluded)

## Signal prevalence (unique bytecodes)

| Signal | Bytecodes | % | Mainnet deployments |
|---|---:|---:|---:|
| `sig_sstore_no_caller` | 37,368 | 2.43% | 353,297 |
| `sig_transient` | 157,396 | 10.22% | 1,132,654 |
| `sig_transient_caller` | 136,092 | 8.84% | 967,798 |
| `sig_selfdestruct` | 143,916 | 9.35% | 26,230,087 |
| `sig_delegate` | 338,176 | 21.96% | 28,788,256 |
| `sig_proxy_like` | 35,841 | 2.33% | 20,373,947 |
| `sig_div_heavy` | 1,000,732 | 64.99% | 7,584,948 |

## Combos of interest

| Combo | Bytecodes | Deployments |
|---|---:|---:|
| transient+CALLER (SIR-like) | 136,092 | 967,798 |
| selfdestruct+DELEGATECALL | 28,184 | 128,591 |
| sstore-no-caller+DELEGATECALL | 19,670 | 296,796 |
| TSTORE and TLOAD both | 15,252 | 21,332 |

## Top redeployed templates per signal


**sig_sstore_no_caller**
- `0xcc51f2662e47ac26308e1d5858fca3f7a28fc3f6dce017d2e9019f76927ed74e` — 193,532 deployments, 514 ops
- `0xf9e2d36819eab1d19e19372266a32e00cb30b02a96732fa6174ccdb560ba1907` — 19,130 deployments, 509 ops
- `0xe25d4f154acb2394ee6c18d64fb5635959ba063d57f83091ec9cf34be16224d7` — 19,074 deployments, 266 ops

**sig_transient**
- `0x07be01e7e7206fe31ecee91ad75dada65ad6ba433ae647a1b9330469f7c6677c` — 401,549 deployments, 524 ops
- `0xaffe208456e818f69a73122832d6db3a7b93175f3bf83dd7f080d11743c81ea9` — 224,600 deployments, 342 ops
- `0xdcf182706ef7caf1dfa3ff3529136ec4e3be7dcc63bc11da5930a45aa2e59b05` — 58,182 deployments, 83 ops

**sig_transient_caller**
- `0x07be01e7e7206fe31ecee91ad75dada65ad6ba433ae647a1b9330469f7c6677c` — 401,549 deployments, 524 ops
- `0xaffe208456e818f69a73122832d6db3a7b93175f3bf83dd7f080d11743c81ea9` — 224,600 deployments, 342 ops
- `0x2bee4af349ccc652c737b5d4106e4e3e8f555a79b0295d6dc48be38b239f2180` — 39,505 deployments, 87 ops

**sig_selfdestruct**
- `0x1d93f60f105899172f7255c030301c3af4564edd4a48577dbdc448aec7ddb0ac` — 10,346,314 deployments, 7 ops
- `0xd80cd839dd3957d572b90780ada202a13936fa2875daea94216263371e9ef1d2` — 6,607,048 deployments, 7 ops
- `0x8f789d24f75f80df63f1d69c18963fb4c2dea81ade3b780fd0c886e4d1fabc4a` — 1,647,068 deployments, 7 ops

**sig_delegate**
- `0x562d59a51820d47f520c975e0b2bcffac644a509749a3161f481f57b6e826d21` — 4,700,956 deployments, 24 ops
- `0x1b460c826a854d61dca82f718e088b8b4c4082ffeb93752d7691bc62c51dc028` — 4,106,154 deployments, 24 ops
- `0xce33220d5c7f0d09d75ceff76c05863c5e7d6e801c70dfe7d5d45d4c44e80654` — 1,595,657 deployments, 313 ops

**sig_proxy_like**
- `0x562d59a51820d47f520c975e0b2bcffac644a509749a3161f481f57b6e826d21` — 4,700,956 deployments, 24 ops
- `0x1b460c826a854d61dca82f718e088b8b4c4082ffeb93752d7691bc62c51dc028` — 4,106,154 deployments, 24 ops
- `0xf1b574431f3838d9cdff6e701afd5a058652dab5ae5523288a83d5fad7696139` — 1,189,974 deployments, 24 ops

**sig_div_heavy**
- `0xce33220d5c7f0d09d75ceff76c05863c5e7d6e801c70dfe7d5d45d4c44e80654` — 1,595,657 deployments, 313 ops
- `0x99c99f1a6d65a9097e0f8ca61683878ed26099e347359f5cdc600bd194dbe908` — 1,546,285 deployments, 692 ops
- `0x5b83bdbcc56b2e630f2807bbadd2b0c21619108066b92a58de081261089e9ce5` — 404,300 deployments, 5372 ops
