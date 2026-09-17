#!/usr/bin/env python3
"""Scan one shard of Track A deployment addresses for funds via QuickNode WSS.

One `qn_getWalletTokenBalance` call per address returns the native balance AND
all ERC-20 balances, so this is ~1 call/address. Output JSONL:
  {"h": <bytecode_hash>, "a": <address>, "n": <native_wei>, "t": [[tok,sym,dec,raw],...]}

Usage: python3 scripts/funds_scan_shard.py --addresses P --shard I --shards N --out OUT.jsonl
"""
import argparse
import asyncio
import json
import os
import sys
from decimal import Decimal

import duckdb

PIPE = 120
RECONNECT_EVERY = 20000


def _raw(s, decimals):
    try:
        d = Decimal(str(s))
    except Exception:
        return 0
    return int(d * (10 ** decimals)) if "." in str(s) else int(d)


async def _recv_json(ws):
    buf = ""
    for _ in range(200):
        m = await ws.recv()
        if isinstance(m, (bytes, bytearray)):
            m = m.decode("utf-8", "ignore")
        buf += m
        try:
            return json.loads(buf)
        except Exception:
            if len(buf) > 8_000_000:
                return None
    return None


def _pack(r, addr):
    res = (r or {}).get("result") or {}
    native = _raw(res.get("nativeTokenBalance") or "0", 18)
    toks = []
    for t in (res.get("result") or []):
        try:
            dec = int(t.get("decimals") or 0)
            toks.append([t.get("address"), t.get("symbol") or "?", dec,
                         str(_raw(t.get("totalBalance") or "0", dec))])
        except Exception:
            continue
    return {"a": addr, "n": native, "t": toks}


async def scan(url, addrs, out_fh, offset=0):
    import websockets
    done = 0
    while offset < len(addrs):
        end = min(offset + RECONNECT_EVERY, len(addrs))
        async with websockets.connect(url, max_size=2 ** 26, ping_interval=20) as ws:
            idmap, inflight = {}, 0
            for i in range(offset, end):
                idmap[i] = addrs[i]
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": i, "method": "qn_getWalletTokenBalance",
                    "params": [{"wallet": addrs[i], "pageSize": 100}]}))
                inflight += 1
                if inflight >= PIPE:
                    for _ in range(inflight):
                        r = await _recv_json(ws)
                        if r and r.get("id") in idmap:
                            rec = _pack(r, idmap[r["id"]])
                            rec["h"] = hashes[r["id"]]
                            out_fh.write(json.dumps(rec) + "\n")
                    inflight = 0
            for _ in range(inflight):
                r = await _recv_json(ws)
                if r and r.get("id") in idmap:
                    rec = _pack(r, idmap[r["id"]])
                    rec["h"] = hashes[r["id"]]
                    out_fh.write(json.dumps(rec) + "\n")
        done += (end - offset)
        if done % 20000 < RECONNECT_EVERY:
            print(f"  scanned {done:,}/{len(addrs):,}", flush=True)
        offset = end


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--addresses", required=True)
    ap.add_argument("--shard", type=int, required=True)
    ap.add_argument("--shards", type=int, required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    url = os.environ.get("QUICKNODE_API_KEY_WSS")
    if not url:
        sys.exit("QUICKNODE_API_KEY_WSS not set")
    con = duckdb.connect()
    rows = con.execute(
        f"SELECT bytecode_hash, address FROM read_parquet('{args.addresses}')").fetchall()
    mine = [r for idx, r in enumerate(rows) if idx % args.shards == args.shard]
    addrs = [r[1] for r in mine]
    global hashes
    hashes = {i: mine[i][0] for i in range(len(mine))}
    print(f"[shard {args.shard}/{args.shards}] {len(addrs):,} addresses", flush=True)
    with open(args.out, "w") as fh:
        asyncio.run(scan(url, addrs, fh))
    print(f"[shard {args.shard}] wrote {args.out}", flush=True)
