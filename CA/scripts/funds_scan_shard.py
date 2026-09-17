#!/usr/bin/env python3
"""Scan one shard of Track A deployment addresses for funds.

Uses QuickNode JSON-RPC over HTTP (their plan caps WSS at 2 connections, which
breaks parallel shards). One `qn_getWalletTokenBalance` call per address returns
the native balance AND all ERC-20 balances. On repeated failure of that method
the address falls back to Alchemy (eth_getBalance + alchemy_getTokenBalances).

Output JSONL: {"h": <bytecode_hash>, "a": <address>, "n": <native_wei>,
               "t": [[tok,sym,dec,raw],...]}

Usage: python3 scripts/funds_scan_shard.py --addresses P --shard I --shards N --out OUT.jsonl
"""
import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal

import aiohttp
import duckdb

CONC = int(os.environ.get("SCAN_CONC", "30"))
RETRIES = 4


def _raw(s, decimals):
    try:
        d = Decimal(str(s))
    except Exception:
        return 0
    return int(d * (10 ** decimals)) if "." in str(s) else int(d)


def _pack(res):
    res = res or {}
    native = _raw(res.get("nativeTokenBalance") or "0", 18)
    toks = []
    for t in (res.get("result") or []):
        try:
            dec = int(t.get("decimals") or 0)
            toks.append([t.get("address"), t.get("symbol") or "?", dec,
                         str(_raw(t.get("totalBalance") or "0", dec))])
        except Exception:
            continue
    return native, toks


async def rpc(session, url, method, params, tries=RETRIES):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    delay = 0.5
    for att in range(tries):
        try:
            async with session.post(url, json=body, timeout=aiohttp.ClientTimeout(total=45)) as r:
                if r.status == 429:
                    await asyncio.sleep(delay * (2 ** att))
                    continue
                d = await r.json(content_type=None)
                if isinstance(d, dict) and d.get("error"):
                    msg = str(d["error"].get("message", ""))[:120]
                    if "limit" in msg.lower() or "rate" in msg.lower():
                        await asyncio.sleep(delay * (2 ** att))
                        continue
                    return None, msg
                return d.get("result"), None
        except Exception as e:
            await asyncio.sleep(delay * (2 ** att))
    return None, "exhausted"


async def one(session, qn, alchemy, sem, addr, out_fh, h, stats):
    async with sem:
        res, err = await rpc(session, qn, "qn_getWalletTokenBalance",
                             [{"wallet": addr, "pageSize": 100}])
        native, toks = None, []
        if res is not None:
            native, toks = _pack(res)
        elif alchemy:
            stats["qn_fail"] += 1
            nat, _e = await rpc(session, alchemy, "eth_getBalance", [addr, "latest"])
            if nat is not None:
                native = int(nat, 16) if isinstance(nat, str) else 0
            tb, _e2 = await rpc(session, alchemy, "alchemy_getTokenBalances", [addr, "erc20"])
            if isinstance(tb, dict):
                for t in (tb.get("tokenBalances") or []):
                    try:
                        dec = int(t.get("decimals") or 0) if t.get("decimals") is not None else 0
                        raw = int(t.get("tokenBalance") or "0x0", 16)
                        if raw and dec == 0:
                            md, _ = await rpc(session, alchemy, "eth_call",
                                              [{"to": t["contractAddress"],
                                                "data": "0x313ce567"}, "latest"])
                            if isinstance(md, str):
                                dec = int(md, 16)
                        toks.append([t["contractAddress"], "?", dec, str(raw)])
                    except Exception:
                        continue
        else:
            stats["unscanned"] += 1
            return
        out_fh.write(json.dumps({"h": h, "a": addr, "n": native or 0, "t": toks}) + "\n")
        stats["done"] += 1
        if stats["done"] % 10000 == 0:
            print(f"  scanned {stats['done']:,}  (qn_fail={stats['qn_fail']:,})", flush=True)


async def run(urls, rows, out_path):
    qn, alchemy = urls
    sem = asyncio.Semaphore(CONC)
    conn = aiohttp.TCPConnector(limit=CONC + 10)
    stats = {"done": 0, "qn_fail": 0, "unscanned": 0}
    with open(out_path, "w") as fh:
        async with aiohttp.ClientSession(connector=conn) as session:
            tasks = [asyncio.create_task(one(session, qn, alchemy, sem, a, fh, h, stats))
                     for h, a in rows]
            await asyncio.gather(*tasks)
    return stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--addresses", required=True)
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--shards", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    wss = os.environ.get("QUICKNODE_API_KEY_WSS") or ""
    if not wss:
        sys.exit("QUICKNODE_API_KEY_WSS not set")
    qn = wss.replace("wss://", "https://").replace("ws://", "http://").rstrip("/")
    if not qn.endswith("/"):
        qn += "/"
    al = os.environ.get("ALCHEMY_API_KEY")
    alchemy = f"https://eth-mainnet.g.alchemy.com/v2/{al}" if al else None

    con = duckdb.connect()
    rows = con.execute(
        f"SELECT bytecode_hash, address FROM read_parquet('{args.addresses}')").fetchall()
    mine = [r for idx, r in enumerate(rows) if idx % args.shards == args.shard]
    print(f"[shard {args.shard}/{args.shards}] {len(mine):,} addresses "
          f"(conc={CONC}, http={'qn+alchemy' if alchemy else 'qn'})", flush=True)
    stats = asyncio.run(run((qn, alchemy), mine, args.out))
    print(f"[shard {args.shard}] done={stats['done']:,} qn_fail={stats['qn_fail']:,} "
          f"unscanned={stats['unscanned']:,} -> {args.out}", flush=True)
