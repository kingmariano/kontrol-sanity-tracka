#!/usr/bin/env python3
"""USDC census via dRPC batched eth_call balanceOf — 100 calls per batch, parallel."""
import time, csv, json, concurrent.futures as cf
import urllib.request, urllib.parse

DK = [l.split("=", 1)[1].strip().strip('"') for l in open(
    "/workspaces/codespaces-blank/CA/.env") if l.startswith("DRPC_API_KEY")][0]
URL = "https://lb.drpc.org/ogrpc?network=ethereum&dkey=" + urllib.parse.quote(DK)
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
BALOF = "0x70a08231"  # balanceOf(address)

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
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1 + attempt)
    return [{"error": "failed"} for _ in calls]

def usdc_batch(chunk):
    """chunk: list of (idx, addr); per-address eth_call (dRPC blocks JSON-RPC batching)."""
    out = {}
    for i, a in chunk:
        calls = [{"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                  "params": [{"to": USDC, "data": BALOF + a[2:].lower().rjust(64, "0")}, "latest"]}]
        v = None
        for attempt in range(6):
            res = rpc_batch(calls)
            if "result" in res[0] and isinstance(res[0]["result"], str):
                try:
                    v = int(res[0]["result"], 16)
                    break
                except ValueError:
                    pass
            time.sleep(0.5 * (attempt + 1))
        out[i] = v
        time.sleep(0.03)
    return out

def main():
    import duckdb
    con = duckdb.connect("/tmp/eth-contracts/eth_contracts.duckdb", read_only=True)
    for label, h in FAMILIES.items():
        addrs = [a for (a,) in con.execute(
            "SELECT address FROM contracts WHERE bytecode_hash = ?", [h]).fetchall()]
        chunks = [list(enumerate(addrs))[i:i + 100] for i in range(0, len(addrs), 100)]
        bal, missing = {}, 0
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for r in ex.map(usdc_batch, chunks):
                for i, v in r.items():
                    if v is None:
                        missing += 1
                    else:
                        bal[addrs[i]] = v
        assert bal.get(addrs[0]) is not None or missing == len(addrs), "total failure"
        holders = [(a, v) for a, v in bal.items() if v > 0]
        holders.sort(key=lambda x: -x[1])
        print("%s: %d instances, USDC holders: %d, MISSING(failed): %d"
              % (label, len(addrs), len(holders), missing), flush=True)
        for a, v in holders[:15]:
            print("   %s  %s USDC (raw %d)" % (a, v / 1e6, v), flush=True)
        with open("/tmp/estok_%s.csv" % label, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["address", "usdc_raw"])
            for a in addrs:
                w.writerow([a, bal.get(a, 0)])
    print("USDC_SWEEP_DONE", flush=True)

if __name__ == "__main__":
    main()