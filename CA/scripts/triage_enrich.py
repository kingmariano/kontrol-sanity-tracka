#!/usr/bin/env python3
"""Enrich LIVE_REACHABLE triage rows with real ETH + ERC-20 balances.

Given a triage report.json (from triage_live.py), for each live-reachable target
re-read the deployment addresses, take the funded + code-bearing instances, and
fetch:
  * exact ETH balance
  * ERC-20 holdings (Alchemy alchemy_getTokenBalances + token metadata)
  * storage slots 0..15
Writes <out>.md and <out>.json.
"""
import argparse
import json
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, ".env")


def env(key, default=None):
    if os.path.exists(ENV):
        for line in open(ENV):
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip('"')
    return default


def _post(url, payload, tries=5, timeout=40):
    data = json.dumps(payload).encode()
    for k in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(0.5 * (k + 1))
    return {}


def rpc(method, params):
    key = env("ALCHEMY_API_KEY") or ""
    return _post("https://eth-mainnet.g.alchemy.com/v2/" + key,
                 {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).get("result")


def etherscan_balances(addrs, key, cap=2000):
    out = {}
    for i in range(0, min(len(addrs), cap), 20):
        q = {"module": "account", "action": "balancemulti", "address": ",".join(addrs[i:i + 20]),
             "tag": "latest", "apikey": key}
        try:
            with urllib.request.urlopen("https://api.etherscan.io/v2/api?chainid=1&" + urllib.parse.urlencode(q), timeout=30) as r:
                for row in json.loads(r.read()).get("result", []):
                    out[row["account"].lower()] = int(row["balance"])
        except Exception:
            pass
        time.sleep(0.22)
    return out


def token_holdings(addr):
    res = rpc("alchemy_getTokenBalances", [addr, "erc20"]) or {}
    out = []
    for tb in res.get("tokenBalances", []):
        raw = tb.get("tokenBalance") or "0x0"
        try:
            v = int(raw, 16)
        except Exception:
            v = 0
        if v > 0:
            md = rpc("alchemy_getTokenMetadata", [tb["contractAddress"]]) or {}
            out.append({"token": tb["contractAddress"], "symbol": md.get("symbol"),
                        "decimals": md.get("decimals"), "raw": str(v), "name": md.get("name")})
    return out


def load_test2target(stage):
    man = json.load(open(os.path.join(ROOT, "harness", "stages", f"stage{stage}", "manifest.json")))
    m = {}
    for ch in man["chunks"]:
        for tname, tgt in zip(ch["tests"], ch["targets"]):
            m[tname] = tgt
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True)
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()
    rows = json.load(open(a.report))
    t2t = load_test2target(a.stage)
    es = env("ETHERSCANV2_API_KEY")
    enriched = []
    for row in rows:
        if row.get("classification") != "LIVE_REACHABLE":
            continue
        tgt = t2t.get(row["test"], {})
        addrs = tgt.get("addresses") or []
        bal = etherscan_balances(addrs, es) if es else {}
        funded = sorted([x for x in addrs if bal.get(x.lower(), 0) > 0],
                        key=lambda x: -bal.get(x.lower(), 0))
        inst = []
        for addr in funded[:a.top]:
            code = rpc("eth_getCode", [addr, "latest"])
            slots = [rpc("eth_getStorageAt", [addr, hex(i), "latest"]) for i in range(16)]
            inst.append({"address": addr, "eth_wei": bal.get(addr.lower(), 0),
                         "eth": bal.get(addr.lower(), 0) / 1e18,
                         "code_size": (len(code) - 2) // 2 if code else 0,
                         "slots_0_15": slots, "tokens": token_holdings(addr)})
        enriched.append({"test": row["test"], "hash": row["hash"],
                         "deployments": row["deployments"], "funded_instances": inst})
    out = {"stage": a.stage, "results": enriched}
    json.dump(out, open(a.out + ".json" if not a.out.endswith(".json") else a.out, "w"), indent=1)
    md = [f"# Live instance enrichment — stage {a.stage}", ""]
    for r in enriched:
        md.append(f"## {r['test']}  (`{r['hash'][:14]}…`, {r['deployments']:,} deploys)")
        for i in r["funded_instances"]:
            md.append(f"- `{i['address']}`  ETH={i['eth']:.6f}  code={i['code_size']}B")
            for t in i["tokens"]:
                md.append(f"    - {t['symbol']} ({t['token']}) raw={t['raw']}")
            nz = {k: v for k, v in enumerate(i["slots_0_15"]) if v and int(v, 16) != 0}
            md.append(f"    slots(nonzero)={nz}")
        md.append("")
    open(a.out.replace(".json", ".md"), "w").write("\n".join(md) + "\n")
    print(f"enriched {len(enriched)} live-reachable targets -> {a.out.replace('.json','.md')}")


if __name__ == "__main__":
    main()
