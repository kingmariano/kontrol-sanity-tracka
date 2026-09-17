#!/usr/bin/env python3
"""Token-inclusive funds ranking for Track A targets.

ETH alone under-counts value, so for each target's sampled deployment addresses
this fetches ALL ERC-20 balances (`alchemy_getTokenBalances`), prices the union
of tokens via the Alchemy Prices API, and reports USD per target.

Usage: python3 scripts/funds_tokens.py [class ...]        (default: all)
Env:   TOP_TARGETS (default 100), ADDRS_PER_TARGET (default 25)
Output: data/stages/<class>_funds_tokens.json  (ranked by eth_usd + token_usd)
"""
import asyncio
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ENV = os.path.join(ROOT, ".env")
CLASSES = ["a1_init", "a2_upgrade", "a5_multicall", "a6_fee", "a7_unchecked",
           "a9_unauth_pull"]
TOP = int(os.environ.get("TOP_TARGETS", "100"))
ADDRS = int(os.environ.get("ADDRS_PER_TARGET", "25"))
PIPE = 150


def env(key):
    if os.environ.get(key):
        return os.environ[key]
    if os.path.exists(ENV):
        for line in open(ENV):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"').strip()
    return None


KEY = env("ALCHEMY_API_KEY")
WSS = env("BLOCKPI_WSS_RPC_URL")
HTTP = f"https://eth-mainnet.g.alchemy.com/v2/{KEY}"
PRICES = f"https://api.g.alchemy.com/prices/v1/{KEY}/tokens/by-address"


def _call_http(method, params_list, batch=25):
    """Batch Alchemy JSON-RPC with 429-aware backoff (re-queues rate-limited chunks)."""
    import time
    out = {}
    queue = list(range(0, len(params_list), batch))
    attempts = 0
    while queue and attempts < 10:
        nxt = []
        for i in queue:
            chunk = params_list[i:i + batch]
            payload = [{"jsonrpc": "2.0", "id": j, "method": method, "params": p}
                       for j, p in enumerate(chunk)]
            req = urllib.request.Request(HTTP, data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
            resp = None
            for _ in range(6):
                try:
                    resp = json.load(urllib.request.urlopen(req, timeout=60))
                    break
                except Exception:
                    time.sleep(2)
            if not resp:
                nxt.append(i)
                continue
            if isinstance(resp, dict):
                resp = [resp]
            limited = False
            for r in resp:
                if not isinstance(r, dict):
                    continue
                if "result" in r:
                    out[i + r["id"]] = r["result"]
                elif "error" in r:
                    msg = str(r["error"])
                    if "429" in msg or "compute units" in msg or "capacity" in msg:
                        limited = True
            if limited:
                nxt.append(i)
        queue = nxt
        if queue:
            attempts += 1
            time.sleep(2 * attempts)
    if queue:
        print(f"  [warn] {len(queue)} batches still rate-limited after retries", flush=True)
    return out


async def _call_wss(method, params_list, pipe=PIPE):
    """Pipeline arbitrary JSON-RPC calls over the websocket; returns id->result."""
    import websockets
    out = {}
    async with websockets.connect(WSS, max_size=2 ** 26, ping_interval=20) as ws:
        idmap, inflight = {}, 0
        for i, p in enumerate(params_list):
            idmap[i] = i
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": i, "method": method, "params": p}))
            inflight += 1
            if inflight == pipe:
                for _ in range(pipe):
                    r = json.loads(await ws.recv())
                    if isinstance(r, dict) and "result" in r:
                        out[r["id"]] = r["result"]
                inflight = 0
        for _ in range(inflight):
            r = json.loads(await ws.recv())
            if isinstance(r, dict) and "result" in r:
                out[r["id"]] = r["result"]
    return out


async def _recv_json(ws):
    """Tolerant receive: skip keepalive/non-JSON frames, reassemble split JSON."""
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
            continue
    return None


def qn_token_balances(addrs):
    """Fast token enumeration via QuickNode's Token API add-on over WSS.
    Returns {addr: (native_wei, [(token_address, symbol, decimals, raw_balance)])}."""
    import websockets
    QN = env("QUICKNODE_API_KEY_WSS")
    out = {}

    async def run():
        async with websockets.connect(QN, max_size=2 ** 26, ping_interval=20) as ws:
            idmap, inflight = {}, 0
            for i, a in enumerate(addrs):
                idmap[i] = a
                await ws.send(json.dumps({
                    "jsonrpc": "2.0", "id": i, "method": "qn_getWalletTokenBalance",
                    "params": [{"wallet": a, "pageSize": 100}]}))
                inflight += 1
                if inflight >= PIPE:
                    for _ in range(inflight):
                        _store(out, idmap, await _recv_json(ws))
                    inflight = 0
            for _ in range(inflight):
                _store(out, idmap, await _recv_json(ws))

    asyncio.run(run())
    for a in addrs:
        out.setdefault(a, (0, []))
    return out


def _raw(s, decimals):
    """QuickNode returns amounts as decimal strings; convert to raw integer units."""
    from decimal import Decimal
    try:
        d = Decimal(str(s))
    except Exception:
        return 0
    if "." in str(s):
        return int(d * (10 ** decimals))
    return int(d)


def _store(out, idmap, r):
    if not isinstance(r, dict) or "result" not in r:
        return
    res = r["result"] or {}
    a = idmap[r["id"]]
    native = _raw(res.get("nativeTokenBalance") or "0", 18)
    toks = []
    for t in (res.get("result") or []):
        try:
            dec = int(t.get("decimals") or 0)
            toks.append((t["address"], t.get("symbol") or "?", dec,
                         _raw(t.get("totalBalance") or t.get("total_balance") or "0", dec)))
        except Exception:
            continue
    out[a] = (native, toks)


def prices_gt(contracts, batch=30):
    """USD prices from GeckoTerminal tokens/multi (30/call, spam auto-dropped:
    unlisted tokens simply are not returned)."""
    import time
    out = {}
    addrs = list(contracts)
    queue = [addrs[i:i + batch] for i in range(0, len(addrs), batch)]
    attempts = 0
    while queue and attempts < 12:
        nxt = []
        for chunk in queue:
            url = ("https://api.geckoterminal.com/api/v2/networks/eth/tokens/multi/"
                   + ",".join(chunk))
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                d = json.load(urllib.request.urlopen(req, timeout=60))
            except Exception:
                nxt.append(chunk)
                continue
            if isinstance(d, dict) and d.get("errors"):
                nxt.append(chunk)
                continue
            for t in d.get("data", []):
                a = (t.get("attributes") or {})
                addr = (a.get("address") or "").lower()
                try:
                    if a.get("price_usd"):
                        out[addr] = float(a["price_usd"])
                except Exception:
                    pass
        queue = nxt
        if queue:
            attempts += 1
            time.sleep(2 * attempts)
    return out


def eth_price():
    try:
        d = json.load(urllib.request.urlopen(
            "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd",
            timeout=30))
        return float(d["ethereum"]["usd"])
    except Exception:
        return 0.0


def run(cls):
    funds = json.load(open(f"{ROOT}/data/stages/{cls}_funds.json"))
    tgt = json.load(open(f"{ROOT}/data/stages/{cls}_targets.json"))
    by_hash = {t["hash"]: t for t in tgt["targets"]}
    ranked = [r for r in funds["ranked"] if r["hash"] in by_hash][:TOP]

    addr_to_target, all_addrs = {}, []
    for r in ranked:
        for a in (by_hash[r["hash"]].get("addresses") or [])[:ADDRS]:
            addr_to_target[a] = r["hash"]
            all_addrs.append(a)

    tb = qn_token_balances(all_addrs)
    union = {}
    for a, (native, toks) in tb.items():
        for (c, sym, dec, bal) in toks:
            if bal > 0:
                union.setdefault(c.lower(), (sym, dec))
    contracts = list(union.keys())
    px = prices_gt(contracts)
    eth_px = eth_price()
    print(f"[{cls}] addrs={len(all_addrs)} tokens={len(union)} priced={len(px)} "
          f"eth_px={eth_px:.2f}", flush=True)

    per = {}
    for a, (native, toks) in tb.items():
        h = addr_to_target[a]
        acc = per.setdefault(h, {"token_usd": 0.0, "eth_wei": 0, "tok": []})
        acc["eth_wei"] += native
        for (c, sym, dec, bal) in toks:
            p = px.get(c.lower())
            if p is None or dec == 0:
                continue
            usd = (bal / (10 ** dec)) * p
            acc["token_usd"] += usd
            if usd > 1:
                acc["tok"].append((sym, round(usd, 2), round(bal / (10 ** dec), 4)))

    out = []
    for r in ranked:
        p = per.get(r["hash"], {"token_usd": 0.0, "eth_wei": 0, "tok": []})
        eth_usd = (p["eth_wei"] / 1e18) * eth_px
        out.append({**r, "token_usd": round(p["token_usd"], 2),
                    "eth_usd": round(eth_usd, 2),
                    "usd": round(p["token_usd"] + eth_usd, 2),
                    "tokens": sorted(p["tok"], key=lambda x: -x[1])[:8]})
    out.sort(key=lambda x: -x["usd"])
    dst = f"{ROOT}/data/stages/{cls}_funds_tokens.json"
    json.dump({"class": cls, "top": TOP, "addr_per_target": ADDRS, "ranked": out},
              open(dst, "w"), indent=1)
    top = out[0] if out else {}
    print(f"[{cls}] top value: ${top.get('usd',0):,.0f} "
          f"(tokens ${top.get('token_usd',0):,.0f} + eth ${top.get('eth_usd',0):,.0f}) "
          f"{top.get('hash','')[:14]}… {top.get('tokens')}", flush=True)


if __name__ == "__main__":
    for c in (sys.argv[1:] or CLASSES):
        if os.path.exists(f"{ROOT}/data/stages/{c}_funds.json"):
            run(c)
