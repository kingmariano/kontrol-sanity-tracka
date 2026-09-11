#!/usr/bin/env python3
"""USDC census over BlockPI WSS: one persistent socket, pipelined eth_calls."""
import json, time, csv, queue, threading
import websocket

WSS = [l.split("=", 1)[1].strip().strip('"') for l in open(
    "/workspaces/codespaces-blank/CA/.env") if l.startswith("BLOCKPI_WSS_RPC_URL")][0]
USDC = "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"
BALOF = "0x70a08231"

FAMILIES = {
    "F5_S2-6":  "0xa24e966a6a8d544de0580e9f47c0085de7430f9cce6dbc0f8b8bc9f009cada59",
    "F6_S2-10": "0x6f83343a067ba432f2f9f48b9d78148966a9647206bf932f67382fef4c534df0",
    "F7_S2-13": "0x3b7d6f59758a4aa6b2a0c9b55b0e19bd15a9bbcd0715299cecc974a05e904a06",
    "F8_S2-23": "0x1aba7e718e34dc9a2d223fc9b695a815b27a291fb2ea7446c8d9022f4307e3d9",
    "F4_c5_3":  "0x1cf5a0fe3bf24282cc81b8ffae2e5e3aa750f3f182a6665e22ba4ab24da3aaf3",
}

INFLIGHT = 20

def sweep_family(label, addrs, ws):
    """Queue-based: send up to INFLIGHT, on error/missing response requeue, pace ~40rps."""
    from collections import deque
    queue_ = deque(range(len(addrs)))
    results = {}          # idx -> raw int
    pending = {}          # rpc id -> idx
    rpc_id = 0
    t0 = time.time()
    last_prog = 0
    while queue_ or pending:
        # refill
        while queue_ and len(pending) < INFLIGHT:
            idx = queue_.popleft()
            a = addrs[idx]
            req = {"jsonrpc": "2.0", "id": rpc_id, "method": "eth_call",
                   "params": [{"to": USDC, "data": BALOF + a[2:].lower().rjust(64, "0")}, "latest"]}
            try:
                ws.send(json.dumps(req))
                pending[rpc_id] = idx
            except Exception:
                queue_.appendleft(idx)
                time.sleep(2)
                try:
                    ws.connect(WSS)
                except Exception:
                    pass
                continue
            rpc_id += 1
            time.sleep(0.02)  # ~50 rps send pace
        # drain one response
        try:
            ws.settimeout(15)
            msg = json.loads(ws.recv())
        except websocket.WebSocketTimeoutException:
            # timeouts -> everything pending is lost, requeue
            for idx in pending.values():
                queue_.append(idx)
            pending.clear()
            continue
        except Exception:
            for idx in pending.values():
                queue_.append(idx)
            pending.clear()
            time.sleep(2)
            try:
                ws = websocket.create_connection(WSS, timeout=30)
            except Exception:
                pass
            continue
        rid = msg.get("id")
        if rid in pending:
            idx = pending.pop(rid)
            r = msg.get("result")
            if isinstance(r, str):
                try:
                    results[idx] = int(r, 16)
                except ValueError:
                    queue_.append(idx)
            else:
                queue_.append(idx)  # error response -> retry later
        if len(results) >= last_prog + 500:
            last_prog = len(results)
            print("  %s progress: %d/%d (%.0fs)" % (label, len(results), len(addrs), time.time() - t0), flush=True)
    return results, 0

def main():
    import duckdb
    con = duckdb.connect("/tmp/eth-contracts/eth_contracts.duckdb", read_only=True)
    ws = websocket.create_connection(WSS, timeout=30)
    for label, h in FAMILIES.items():
        addrs = [a for (a,) in con.execute(
            "SELECT address FROM contracts WHERE bytecode_hash = ?", [h]).fetchall()]
        results, missing = sweep_family(label, addrs, ws)
        holders = sorted(((addrs[i], v) for i, v in results.items() if v > 0),
                         key=lambda x: -x[1])
        print("%s: %d instances, USDC holders: %d, MISSING: %d"
              % (label, len(addrs), len(holders), missing), flush=True)
        for a, v in holders[:15]:
            print("   %s  %s USDC" % (a, v / 1e6), flush=True)
        with open("/tmp/wss_usdc_%s.csv" % label, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["address", "usdc_raw"])
            for i, a in enumerate(addrs):
                w.writerow([a, results.get(i, "MISSING")])
    ws.close()
    print("WSS_USDC_DONE", flush=True)

if __name__ == "__main__":
    main()