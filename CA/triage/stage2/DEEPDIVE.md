# Deep dive — stage 2 live-reachable FAILs

All reads via Alchemy `eth_call`/`eth_getCode`/`eth_getStorageAt` (read-only; **no
transactions sent**).

## Finding A — `test_p3_c23_0` → sweeper/drainer infrastructure, NOT a victim bug

- **Target clone bytecode hash:** `0xaefdf0b549a4dfddb17ab79884222d73a82f71697b1a96128c0256e16d4ec984` (269,148 deployments)
- **Clone type:** EIP-1167 minimal proxy, 45 bytes
- **Implementation:** `0x39778bc77bd7a9456655b19fd4c5d0bf2071104e` (2,023 B runtime, **unverified**)
- **Interface (4byte):** `sweepEther()`, `sweeper()`, `executeCallWithData(address,bytes)`, `sweepERC20(address)`
- **`sweeper()` →** `0x5f65f7b609678448494de4c87521cdf6cef1e932`
- **`sweepEther()` from a random address →** **reverts `unauthorized`** on every sampled clone

Example clones (ETH held): `0x9625c958c6483395c0d3d298f1a1a7eeeadd2430` (0.008),
`0x9791ac77978cf166afa352a6355364911017c13b` (3.234),
`0xc8a6c35167a8fae56d4728d76d22bd22a7a93444` (2.000),
`0x90d8560d761d888eb381050fdbb2d3b468944296` (0.234),
`0xce9daa67c0154a4e0d70d67d17854576cc500adf` (0.202),
`0x68cd6de3bc885a09c029a22d916d2f0624802afa` (0.136),
`0x2f6b4ff4920dbc855c6babae2f627c64c912aa63` (0.100),
`0xc1eb075332be8e90d3bf50ffa4dbee197636cc43` (0.099),
`0x0b7519c800844e19b831cf7dd55e42187877be81` (0.091).

**Verdict:** access-controlled sweeper wallets (269k clones, small ETH balances +
scam/airdrop tokens). `sweepEther` is gated to the hardcoded `sweeper`, which the
ABI-agnostic harness cannot model → **proof false positive**. Not a victim
vulnerability; do not interact.

## Finding B — `test_p4_c11_1` → role-gated contract, NOT permissionless

- **Target hash:** `0xb6aa9c41d9ab516ee44e94fb5f27e3a51706cffb76659497a2f5d2077bcdf52f` (4 deployments)
- **Contract A:** `0xfa990ea3cc8f1ec066986477edf457ffbad6e39c` (394 B, unverified, 0.5 ETH)
- **Contract B:** `0xb02b12bf1f2337d2e45554aec474e4e25bdf8c76` (394 B, unverified, 1.5 ETH)
- **Interface:** `change(address)`, `setTarget(address)`, `transact(address,uint256,bytes)`
- **Storage:** slot0 = `0x6de30fcc2adae31335be2b06f7f466e5c7b0ff0d` (verified
  **`LeaderSelection`**, 10,940 B); slot1 = `0x6880f6fd960d1581c2730a451a22eed1081cfd72`
  (24,407 B) / `0x59bd11f8a5a833f26723d044cbb501a40c9c5e43` (24,121 B);
  Contract B slot0 = `0x0ea6b5edc8905c85514b3676703f1bfe6ec260ad` (EOA, 3.2 ETH)
- **`change` / `setTarget`** revert with custom error `0x04`; **`transact`** reverts
  `0x01` from random and from slot1, `0x02` from slot0 → **role-gated**

**Verdict:** all three entry points revert for every address tested (including the
configured slot0/slot1 roles), so it is not permissionlessly drainable. Matched the
stage-2 `sig_transient_caller` filter on a **single TLOAD** (no TSTORE) plus the
generic storage property → **proof false positive**.

## Bottom line
- stage 1: all FAILs DORMANT.
- stage 2: 15 DORMANT; 2 LIVE_REACHABLE both **guarded** (A: hardcoded sweeper,
  B: role-gated) → no confirmed live bug from stages 1–2 so far.
