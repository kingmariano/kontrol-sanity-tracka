#!/usr/bin/env python3
"""Rank Track A targets by live ETH held by their sampled deployments.

Deployment count is a poor value proxy for the diffuse classes (A5/A6/A9), so
this samples real balances: for each target in the scanner's `_targets.json`
sample it takes up to ADDRS_PER_TARGET deployment addresses and sums their ETH
via batched `eth_getBalance` (Alchemy). Output: `data/stages/<class>_funds.json`
ranked by ETH held, with a `wave1_covered` flag (top-150 by deploys).

Usage: ALCHEMY_API_KEY=... python3 scripts/funds_rank.py [class ...]
"""
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENV = os.path.join(ROOT, ".env")
CLASSES = ["a1_init", "a2_upgrade", "a5_multicall", "a6_fee", "a7_unchecked",
           "a9_unauth_pull"]
BATCH = 50
ADDRS_PER_TARGET = int(os.environ.get("ADDRS_PER_TARGET", "25"))
WAVE1_N = 150  # wave1s took the top-150 per class by deployments


def env(key):
    if os.environ.get(key):
        return os.environ[key]
    if os.path.exists(ENV):
        for line in open(ENV):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip()
    return None


KEY = env("ALCHEMY_API_KEY")
URL = f"https://eth-mainnet.g.alchemy.com/v2/{KEY}"
WSS = env("BLOCKPI_WSS_RPC_URL")
PIPE = 200  # in-flight requests over the websocket


def balances_wss(addrs):
    """Pipeline eth_getBalance over a websocket (BlockPI) — far faster than the
    HTTP endpoint. Sends PIPE requests before draining replies."""
    import asyncio
    import websockets
    out = {}

    async def run():
        async with websockets.connect(WSS, max_size=2 ** 24, ping_interval=20) as ws:
            idmap = {}
            inflight = 0
            for i, a in enumerate(addrs):
                idmap[i] = a
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": i,
                                          "method": "eth_getBalance",
                                          "params": [a, "latest"]}))
                inflight += 1
                if inflight == PIPE:
                    for _ in range(PIPE):
                        r = json.loads(await ws.recv())
                        if isinstance(r, dict) and "result" in r:
                            out[idmap[r["id"]]] = int(r["result"], 16)
                    inflight = 0
            for _ in range(inflight):
                r = json.loads(await ws.recv())
                if isinstance(r, dict) and "result" in r:
                    out[idmap[r["id"]]] = int(r["result"], 16)

    asyncio.run(run())
    return out


def balances(addrs):
    if WSS:
        try:
            return balances_wss(addrs)
        except Exception as e:
            print("  [wss failed, falling back to http]", str(e)[:80], flush=True)
    out = {}
    for i in range(0, len(addrs), BATCH):
        chunk = addrs[i:i + BATCH]
        payload = [{"jsonrpc": "2.0", "id": j, "method": "eth_getBalance",
                    "params": [a, "latest"]} for j, a in enumerate(chunk)]
        req = urllib.request.Request(
            URL, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        resp = None
        for _ in range(3):
            try:
                resp = json.load(urllib.request.urlopen(req, timeout=60))
                break
            except Exception:
                time.sleep(2)
        if not resp:
            continue
        for r in resp:
            if isinstance(r, dict) and "result" in r:
                out[chunk[r["id"]]] = int(r["result"], 16)
    return out


def rank(cls, jpath):
    man = json.load(open(jpath))
    targets = man.get("targets", [])
    ranked = []
    for rank_i, t in enumerate(targets):
        addrs = (t.get("addresses") or [])[:ADDRS_PER_TARGET]
        eth = 0
        if addrs:
            b = balances(addrs)
            eth = sum(b.values())
        ranked.append({
            "hash": t["hash"], "deploys": t.get("deploys", 0),
            "n_ops": t.get("n_ops", 0), "disp_sel": t.get("disp_sel", ""),
            "addr_sampled": len(addrs), "eth_wei": str(eth),
            "eth": eth / 1e18, "wave1_covered": rank_i < WAVE1_N,
        })
    ranked.sort(key=lambda x: -int(x["eth_wei"]))
    out = os.path.join(ROOT, "data", "stages", f"{cls}_funds.json")
    json.dump({"class": cls, "addr_per_target": ADDRS_PER_TARGET,
               "wave1_n": WAVE1_N, "ranked": ranked}, open(out, "w"), indent=1)
    funded = [r for r in ranked if int(r["eth_wei"]) > 0]
    print(f"[{cls}] targets={len(ranked)} with_eth={len(funded)} "
          f"top_eth={ranked[0]['eth']:.4f} -> {out}", flush=True)


if __name__ == "__main__":
    args = sys.argv[1:] or CLASSES
    for c in args:
        p = os.path.join(ROOT, "data", "stages", f"{c}_targets.json")
        if not os.path.exists(p):
            print("missing", p, flush=True)
            continue
        rank(c, p)
