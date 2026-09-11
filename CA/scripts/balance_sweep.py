#!/usr/bin/env python3
"""Full live-funds census for finding families: every deployed instance,
ETH balance (batched JSON-RPC) + ERC-20 holdings (alchemy_getTokenBalances)."""
import json, sys, time, csv, concurrent.futures as cf
import urllib.request

ALCHEMY_KEY = [l.split("=", 1)[1].strip() for l in open(
    "/workspaces/codespaces-blank/CA/.env") if l.startswith("ALCHEMY_API_KEY")][0]
URL = "https://eth-mainnet.g.alchemy.com/v2/" + ALCHEMY_KEY
DB = "/tmp/eth-contracts/eth_contracts.duckdb"

FAMILIES = {
    "F5_S2-6":  "0xa24e966a6a8d544de0580e9f47c0085de7430f9cce6dbc0f8b8bc9f009cada59",
    "F6_S2-10": "0x6f83343a067ba432f2f9f48b9d78148966a9647206bf932f67382fef4c534df0",
    "F7_S2-13": "0x3b7d6f59758a4aa6b2a0c9b55b0e19bd15a9bbcd0715299cecc974a05e904a06",
    "F8_S2-23": "0x1aba7e718e34dc9a2d223fc9b695a815b27a291fb2ea7446c8d9022f4307e3d9",
    "F4_c5_3":  "0x1cf5a0fe3bf24282cc81b8ffae2e5e3aa750f3f182a6665e22ba4ab24da3aaf3",
}

def rpc_batch(calls):
    req = urllib.request.Request(URL, data=json.dumps(calls).encode(),
                                 headers={"Content-Type": "application/json"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            time.sleep(2 * (attempt + 1))
    return [{"error": "failed"} for _ in calls]

def eth_balances(addrs):
    out = {}
    batches = [addrs[i:i + 50] for i in range(0, len(addrs), 50)]
    def run(chunk):
        calls = [{"jsonrpc": "2.0", "id": a, "method": "eth_getBalance",
                  "params": [a, "latest"]} for a in chunk]
        res = {}
        for r in rpc_batch(calls):
            if "result" in r:
                res[r["id"]] = int(r["result"], 16)
        return res
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for r in ex.map(run, batches):
            out.update(r)
    return out

def token_balances(addr):
    calls = [{"jsonrpc": "2.0", "id": 1, "method": "alchemy_getTokenBalances",
              "params": [addr, ["0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"]]}]
    res = rpc_batch(calls)
    try:
        for tb in res[0]["result"]["tokenBalances"]:
            b = int(tb["tokenBalance"], 16)
            if b > 0:
                return b
    except Exception:
        pass
    return 0

def main():
    import duckdb
    con = duckdb.connect(DB, read_only=True)
    for label, h in FAMILIES.items():
        addrs = [a for (a,) in con.execute(
            "SELECT address FROM contracts WHERE bytecode_hash = ?", [h]).fetchall()]
        print("%s: %d instances" % (label, len(addrs)), flush=True)
        bal = eth_balances(addrs)
        funded = [a for a in addrs if bal.get(a, 0) > 0]
        print("  ETH>0: %d" % len(funded), flush=True)
        # token check: all funded + every 5th unfunded (coverage vs cost)
        tok_targets = funded + [a for i, a in enumerate(addrs) if bal.get(a, 0) == 0 and i % 5 == 0]
        print("  token-scan targets: %d" % len(tok_targets), flush=True)
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            toks = dict(zip(tok_targets, ex.map(token_balances, tok_targets)))
        with open("/tmp/census_%s.csv" % label, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["address", "eth_wei", "usdc_raw"])
            for a in addrs:
                w.writerow([a, bal.get(a, 0), toks.get(a, 0) if a in toks else ""])
        nz = [a for a in addrs if bal.get(a, 0) > 0 or toks.get(a, 0)]
        print("  FUNDED: %d -> %s" % (len(nz), nz[:10]), flush=True)
    print("CENSUS_DONE", flush=True)

if __name__ == "__main__":
    main()