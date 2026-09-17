#!/usr/bin/env python3
"""Merge scan shards, price tokens (Alchemy Prices with backoff), and keep only
targets holding >= MIN_USD of ETH + priced ERC-20 value. Unpriced tokens are
treated as spam/unlisted and dropped from the value (but counted).

Output: /tmp/funded_targets.parquet (bytecode_hash, usd, eth_usd, token_usd,
n_addrs, top_tokens)  + a printed stats report.
"""
import glob
import json
import os
import sys
import time
import urllib.request

MIN_USD = float(os.environ.get("MIN_USD", "10"))
SCAN_GLOB = os.environ.get("SCAN_GLOB", "/tmp/scans/*.jsonl")
OUT = os.environ.get("OUT", "/tmp/funded_targets.parquet")
KEY = os.environ.get("ALCHEMY_API_KEY")
PRICES = f"https://api.g.alchemy.com/prices/v1/{KEY}/tokens/by-address"


def price_tokens(contracts):
    out = {}
    queue = [contracts[i:i + 20] for i in range(0, len(contracts), 20)]
    attempts = 0
    while queue and attempts < 12:
        nxt = []
        for chunk in queue:
            body = {"addresses": [{"address": a, "network": "eth-mainnet"} for a in chunk]}
            req = urllib.request.Request(PRICES, data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json"})
            d = None
            for _ in range(5):
                try:
                    d = json.load(urllib.request.urlopen(req, timeout=60))
                    break
                except Exception:
                    time.sleep(2)
            if not d:
                nxt.append(chunk)
                continue
            for row in d.get("data", []):
                ps = row.get("prices") or []
                if ps:
                    try:
                        out[row["address"].lower()] = float(ps[0]["value"])
                    except Exception:
                        pass
        queue = nxt
        if queue:
            attempts += 1
            time.sleep(2 * attempts)
    return out


def eth_price():
    for url, key in ((f"https://api.g.alchemy.com/prices/v1/{KEY}/tokens/by-address", None),
                     ("https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd", None)):
        try:
            if "alchemy" in url:
                body = {"addresses": [{"address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                                       "network": "eth-mainnet"}]}
                req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                             headers={"Content-Type": "application/json"})
                d = json.load(urllib.request.urlopen(req, timeout=30))
                return float(d["data"][0]["prices"][0]["value"])
            d = json.load(urllib.request.urlopen(url, timeout=30))
            return float(d["ethereum"]["usd"])
        except Exception:
            continue
    return 0.0


def main():
    per = {}      # hash -> {"n": wei, "tokens": {tok: [sym,dec,raw]}, "addrs": int}
    n_records = 0
    for f in glob.glob(SCAN_GLOB):
        for line in open(f):
            try:
                r = json.loads(line)
            except Exception:
                continue
            h = r.get("h")
            if not h:
                continue
            n_records += 1
            acc = per.setdefault(h, {"n": 0, "tokens": {}, "addrs": 0})
            acc["n"] += int(r.get("n") or 0)
            acc["addrs"] += 1
            for t in r.get("t") or []:
                try:
                    tok, sym, dec, raw = t[0].lower(), t[1], int(t[2]), int(t[3])
                except Exception:
                    continue
                cur = acc["tokens"].get(tok)
                if cur:
                    cur[2] += raw
                else:
                    acc["tokens"][tok] = [sym, dec, raw]
    print(f"[finalize] records={n_records:,} targets={len(per):,}", flush=True)

    all_tokens = set()
    for a in per.values():
        all_tokens.update(a["tokens"].keys())
    px = price_tokens(sorted(all_tokens))
    eth = eth_price()
    print(f"[finalize] tokens={len(all_tokens):,} priced={len(px):,} eth=${eth:,.2f}",
          flush=True)

    rows = []
    for h, a in per.items():
        eth_usd = (a["n"] / 1e18) * eth
        tok_usd = 0.0
        top = []
        for tok, (sym, dec, raw) in a["tokens"].items():
            p = px.get(tok)
            if p is None or dec == 0:
                continue
            v = (raw / (10 ** dec)) * p
            tok_usd += v
            if v > 1:
                top.append([sym, round(v, 2)])
        usd = eth_usd + tok_usd
        if usd >= MIN_USD:
            top.sort(key=lambda x: -x[1])
            rows.append((h, round(usd, 2), round(eth_usd, 2), round(tok_usd, 2),
                         a["addrs"], json.dumps(top[:6])))
    import duckdb
    con = duckdb.connect()
    con.execute("CREATE TABLE f(bytecode_hash VARCHAR, usd DOUBLE, eth_usd DOUBLE, "
                "token_usd DOUBLE, n_addrs BIGINT, top_tokens VARCHAR)")
    con.executemany("INSERT INTO f VALUES (?,?,?,?,?,?)", rows)
    con.execute(f"COPY f TO '{OUT}' (FORMAT parquet)")
    print(f"[finalize] funded (>=$MIN_USD): {len(rows):,} targets -> {OUT}", flush=True)
    tot = sum(r[1] for r in rows)
    print(f"[finalize] total value held: ${tot:,.0f}", flush=True)
    for r in sorted(rows, key=lambda x: -x[1])[:10]:
        print(f"  ${r[1]:>14,.0f}  eth=${r[2]:>12,.0f} tok=${r[3]:>12,.0f}  "
              f"{r[4]:>4} addrs  {r[0][:18]}…", flush=True)


if __name__ == "__main__":
    main()
