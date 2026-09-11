#!/usr/bin/env python3
"""Fast ETH sweep for all finding families via Etherscan V2 balancemulti (20 addr/call)."""
import time, csv, json, urllib.request, urllib.parse

EK = [l.split("=", 1)[1].strip().strip('"') for l in open(
    "/workspaces/codespaces-blank/CA/.env") if l.startswith("ETHERSCANV2_API_KEY")][0]

FAMILIES = {
    "F5_S2-6":  "0xa24e966a6a8d544de0580e9f47c0085de7430f9cce6dbc0f8b8bc9f009cada59",
    "F6_S2-10": "0x6f83343a067ba432f2f9f48b9d78148966a9647206bf932f67382fef4c534df0",
    "F7_S2-13": "0x3b7d6f59758a4aa6b2a0c9b55b0e19bd15a9bbcd0715299cecc974a05e904a06",
    "F8_S2-23": "0x1aba7e718e34dc9a2d223fc9b695a815b27a291fb2ea7446c8d9022f4307e3d9",
    "F4_c5_3":  "0x1cf5a0fe3bf24282cc81b8ffae2e5e3aa750f3f182a6665e22ba4ab24da3aaf3",
}

def es(params):
    params["apikey"] = EK
    url = "https://api.etherscan.io/v2/api?chainid=1&" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return {"status": "0", "result": []}

def main():
    import duckdb
    con = duckdb.connect("/tmp/eth-contracts/eth_contracts.duckdb", read_only=True)
    for label, h in FAMILIES.items():
        addrs = [a for (a,) in con.execute(
            "SELECT address FROM contracts WHERE bytecode_hash = ?", [h]).fetchall()]
        bal = {}
        for i in range(0, len(addrs), 20):
            chunk = addrs[i:i + 20]
            res = es({"module": "account", "action": "balancemulti",
                      "address": ",".join(chunk), "tag": "latest"})
            for row in res.get("result", []):
                bal[row["account"]] = int(row["balance"])
            time.sleep(0.22)  # ~5 rps
        funded = [(a, bal.get(a, 0)) for a in addrs if bal.get(a, 0) > 0]
        print("%s: %d instances, ETH-funded: %d" % (label, len(addrs), len(funded)), flush=True)
        for a, b in funded[:20]:
            print("   %s  %.6f ETH" % (a, b / 1e18), flush=True)
        with open("/tmp/eseth_%s.csv" % label, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["address", "eth_wei"])
            for a in addrs:
                w.writerow([a, bal.get(a, 0)])
    print("ETH_SWEEP_DONE", flush=True)

if __name__ == "__main__":
    main()